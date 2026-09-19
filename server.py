#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看视频学俄语 —— 本地启动脚本

作用（三件事）：
  1. 把 index.html 作为网页跑在 http://localhost:8000
     （这样浏览器语音识别「跟读」才能用，file:// 打不开麦克风）
  2. /api/subs   帮你抓 YouTube 俄语字幕（需要 yt-dlp）
  3. /api/dict   /api/ai   转发翻译与 AI 请求，绕开浏览器跨域限制

首次使用：
  pip install yt-dlp        # 自动抓 YouTube 字幕
  pip install razdel        # 俄语无标点字幕断句（可选，未装则降级到本地规则）
  python server.py
然后浏览器打开 http://localhost:8000
"""

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 读取本地 .env 文件（本地开发时配置 DATABASE_URL 等）
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v



# 连词成句判题引擎
from answer_engine import AnswerEngine

PORT = int(os.environ.get("PORT", "8000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")

# AI 中转配置：支持多种环境变量名，按优先级 fallback（密钥/地址从环境变量读取，前端不再持有密钥）
AI_BASE_URL = os.environ.get("AI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com"
AI_API_KEY = os.environ.get("AI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
AI_MODEL = os.environ.get("AI_MODEL") or os.environ.get("DEEPSEEK_MODEL") or os.environ.get("OPENAI_MODEL") or "deepseek-chat"
# 智谱 AI Key：用于高精度语音识别（GLM-ASR-2512）与俄语规范化修正，在 https://bigmodel.cn 申请
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY") or ""
# Groq Key：Whisper-large-v3 语音识别（快、准，俄语最优），在 https://console.groq.com 免费申请
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or ""
# Cloudflare Workers AI：免费 Whisper 识别（需 Account ID + API Token，在 dash.cloudflare.com 创建）
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN") or ""

# 学习广场管理员密钥：上传/删除素材需携带 adminKey == ADMIN_KEY
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

# ---- CORS 白名单（拆分部署：前端在 Netlify，后端在 Render）----
# 逗号分隔多个允许的前端域名（如 https://xxx.netlify.app,https://xxx.com）。
# 留空则沿用旧的 "*" 通配，不改变任何已有行为。
_ALLOWED_ORIGINS_RAW = os.environ.get("ALLOWED_ORIGIN", "").strip()
_ALLOWED_ORIGINS = [o.strip() for o in _ALLOWED_ORIGINS_RAW.split(",") if o.strip()]
# 只有在显式设置了 ALLOWED_ORIGIN 时，才额外放行 localhost 便于本地开发
if _ALLOWED_ORIGINS:
    for _dev in ("http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5173", "http://127.0.0.1:5173"):
        if _dev not in _ALLOWED_ORIGINS:
            _ALLOWED_ORIGINS.append(_dev)


def _allowed_origin(origin):
    """返回本次请求应该回写的 Access-Control-Allow-Origin 值，空字符串表示不放行。"""
    if not _ALLOWED_ORIGINS:
        return "*"
    if not origin:
        return _ALLOWED_ORIGINS[0]
    if origin in _ALLOWED_ORIGINS:
        return origin
    return ""


# ---- 视频上传相关（只需配置对象存储）----
try:
    from minio import Minio
    _MINIO_OK = True
except Exception:
    _MINIO_OK = False

_minio_client = None
def _get_minio_client():
    global _minio_client
    if _MINIO_OK:
        if _minio_client is None:
            endpoint = os.environ.get("MINIO_ENDPOINT")
            access_key = os.environ.get("MINIO_ACCESS_KEY")
            secret_key = os.environ.get("MINIO_SECRET_KEY")
            if endpoint and access_key and secret_key:
                _minio_client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=True)
    return _minio_client
# ---- Backblaze B2（S3 兼容）对象存储：浏览器预签名直传，文件不经过本服务 ----
# 采用私有桶（免信用卡、10GB 免费）+ 预签名 URL：
#   上传：前端拿 presigned PUT 直传 B2；播放：读取时把 b2://key 换成 presigned GET。
try:
    import boto3
    from botocore.config import Config as _BotoConfig
    _B2_OK = True
except Exception:
    _B2_OK = False

_B2_BUCKET = os.environ.get("B2_BUCKET", "")
_B2_REGION = os.environ.get("B2_REGION", "")
_B2_ENDPOINT = os.environ.get("B2_ENDPOINT", "")
_B2_KEYID = os.environ.get("B2_KEYID", "")
_B2_APPKEY = os.environ.get("B2_APPLICATION_KEY", "")
_B2_PREFIX = "b2://"

_b2_client = None
def _get_b2():
    global _b2_client
    if not _B2_OK:
        return None
    if _b2_client is None:
        if not (_B2_BUCKET and _B2_ENDPOINT and _B2_KEYID and _B2_APPKEY):
            return None
        endpoint = _B2_ENDPOINT if _B2_ENDPOINT.startswith("http") else "https://" + _B2_ENDPOINT
        _b2_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=_B2_KEYID,
            aws_secret_access_key=_B2_APPKEY,
            region_name=(_B2_REGION or None),
            config=_BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3},
            ),
        )
    return _b2_client


def _b2_configured():
    return _get_b2() is not None


def _b2_safe_ext(filename, default=".mp4"):
    m = re.search(r"\.([A-Za-z0-9]{1,5})$", filename or "")
    ext = ("." + m.group(1).lower()) if m else default
    if ext not in (".mp4", ".webm", ".mov", ".m4v", ".mkv",
                   ".jpg", ".jpeg", ".png", ".webp"):
        return default
    return ext


def _b2_content_type(ext, default="video/mp4"):
    table = {
        ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
        ".mov": "video/quicktime", ".mkv": "video/x-matroska",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }
    return table.get(ext, default)


def _b2_presign_put(key, content_type, expires=600):
    client = _get_b2()
    if not client:
        return None
    params = {"Bucket": _B2_BUCKET, "Key": key}
    if content_type:
        params["ContentType"] = content_type
    return client.generate_presigned_url("put_object", Params=params, ExpiresIn=expires)


def _b2_presign_get(key, expires=604800):
    client = _get_b2()
    if not client:
        return None
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": _B2_BUCKET, "Key": key}, ExpiresIn=expires
    )


def _b2_resolve(url):
    """把 b2://key 换成预签名播放链接；http(s) 外链原样返回；失败返回空串。"""
    if not url:
        return ""
    if url.startswith(_B2_PREFIX):
        key = url[len(_B2_PREFIX):]
        try:
            return _b2_presign_get(key) or ""
        except Exception as e:
            print("[b2] sign failed:", e)
            return ""
    return url


def _normalize_db_url(url):
    """修正 Render 注入的 DATABASE_URL 的两个问题。

    Render 的 fromDatabase.property=connectionString 返回的是「私有网络」连接串，
    主机名是内部短名 dpg-xxx-a（无域名后缀）。免费 Web 服务不在私有网络内时，
    libpq 对裸 hostname 做 DNS 解析会报：
        could not translate host name "dpg-xxx-a" to address
    同时该连接串还常缺 :5432 端口。这里：
      1. 给内部短名补外部域名后缀 .<region>-postgres.render.com（默认 oregon，
         可用环境变量 PG_REGION 覆盖）；
      2. 缺端口补 5432；
      3. 用 quote 转义 password 里的特殊字符。
    """
    if not url:
        return url
    # 只处理 postgres:// / postgresql:// 前缀
    if not url.startswith(("postgres://", "postgresql://", "psql://")):
        return url
    # 用 urllib.parse 解析，避免正则误伤 password 中的特殊字符
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return url

    host = parsed.hostname or ""
    port = parsed.port or 5432

    # 内部短主机名（dpg-xxx-a，无点）补外部域名，否则 DNS 解析失败
    if host.startswith("dpg-") and "." not in host:
        region = (os.environ.get("PG_REGION") or "oregon").strip()
        host = "%s.%s-postgres.render.com" % (host, region)

    userinfo = ""
    if parsed.username:
        userinfo = "%s:%s@" % (parsed.username,
                              urllib.parse.quote(parsed.password or "", safe=""))
    netloc = "%s%s:%d" % (userinfo, host, port)
    path = parsed.path or ""
    query = ("?" + parsed.query) if parsed.query else ""
    return "%s://%s%s%s" % (parsed.scheme, netloc, path, query)


# 数据库（学习广场投稿持久化，Render Postgres 提供 DATABASE_URL）
# 读取后立即规范化：内部短名补外部域名 + 补端口 5432（见 _normalize_db_url）。
DATABASE_URL = _normalize_db_url(os.environ.get("DATABASE_URL", ""))
try:
    import pymysql
    import pymysql.cursors
    _PYMYSQL_OK = True
except Exception:
    _PYMYSQL_OK = False


def http_call(method, url, payload=None, headers=None, timeout=40):
    """返回 (status_code, body_str)。网络异常时返回 (0, 错误信息)。"""
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:  # 网络不通 / 超时 / DNS 等
        return 0, str(e)


_YT_COOKIES_TMP = None


def _yt_cookies_file():
    """返回 yt-dlp 用的 cookies 文件路径；未配置则返回 None。

    YouTube/B 站等对数据中心 IP 反爬，未登录抓字幕/取流常报
    「Sign in to confirm you're not a bot」或「HTTP Error 412」，
    需要提供浏览器导出的 cookies（该文件按域名匹配，可同时含 YouTube 与 B 站）。
    优先读 YT_COOKIES_FILE（指向 cookies.txt 文件路径）；其次读 YT_COOKIES
    （Netscape 格式 cookies 的完整内容，会写入临时文件缓存复用）。
    """
    path = os.environ.get("YT_COOKIES_FILE", "").strip()
    if path and os.path.isfile(path):
        return path
    content = os.environ.get("YT_COOKIES", "").strip()
    if not content:
        return None
    global _YT_COOKIES_TMP
    if _YT_COOKIES_TMP and os.path.isfile(_YT_COOKIES_TMP):
        return _YT_COOKIES_TMP
    try:
        fd, tmp = tempfile.mkstemp(prefix="yt_cookies_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        _YT_COOKIES_TMP = tmp
        return tmp
    except Exception:
        return None


BILI_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _bili_headers(url):
    """B 站反爬（412 Precondition Failed）：需要 Origin/Referer + 浏览器 UA。
    仅对 B 站链接返回这些请求头，避免影响 YouTube 等其它站点。"""
    if "bilibili.com" in url or "b23.tv" in url:
        return {
            "Origin": "https://www.bilibili.com",
            "Referer": "https://www.bilibili.com",
            "User-Agent": BILI_UA,
        }
    return {}


def fetch_subs(url):
    """用 yt-dlp 抓取俄语字幕（含自动生成字幕）。返回 (字幕文本, 错误信息或 None)。"""
    tmp = tempfile.mkdtemp(prefix="ru_subs_")
    try:
        out_tmpl = os.path.join(tmp, "%(id)s.%(ext)s")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--skip-download", "--no-playlist", "--no-warnings",
            "--retries", "3", "--sleep-requests", "1", "--sleep-subtitles", "1",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "ru",
            "--sub-format", "srt/vtt/best",
        ]
        cookies = _yt_cookies_file()
        if cookies:
            cmd += ["--cookies", cookies]
        for k, v in _bili_headers(url).items():
            cmd += ["--add-header", "%s:%s" % (k, v)]
        cmd += ["-o", out_tmpl, url]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if proc.returncode != 0:
            detail = (proc.stdout + "\n" + proc.stderr).strip()
            if "No module named" in detail:
                return None, "未安装 yt-dlp。请运行：python -m pip install yt-dlp"
            if "Sign in to confirm" in detail:
                return None, "YouTube 要求登录验证（反爬）：请在 Render 环境变量里配置 YT_COOKIES（浏览器导出的 cookies）"
            return None, "抓取失败：" + detail[-1200:]
        files = [f for f in os.listdir(tmp) if f.endswith((".srt", ".vtt"))]
        if not files:
            return None, "没有找到俄语字幕（该视频可能没有俄语字幕）。"
        # 优先选含 ru 的 .srt，其次 .vtt
        files.sort(key=lambda p: (".ru" not in p, ".srt" not in p, len(p)))
        with open(os.path.join(tmp, files[0]), "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(), None
    except FileNotFoundError:
        return None, "未安装 yt-dlp。请运行：python -m pip install yt-dlp"
    except subprocess.TimeoutExpired:
        return None, "抓取字幕超时，请检查网络后重试"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download_audio(url):
    """用 yt-dlp 下载视频的音频流（bestaudio，无需 ffmpeg 转码）。
    返回 (音频文件路径, 错误或 None)。"""
    tmp = tempfile.mkdtemp(prefix="ru_trans_")
    out_tmpl = os.path.join(tmp, "audio.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio/best",
        "--no-playlist", "--no-warnings",
        "--retries", "3",
    ]
    cookies = _yt_cookies_file()
    if cookies:
        cmd += ["--cookies", cookies]
    for k, v in _bili_headers(url).items():
        cmd += ["--add-header", "%s:%s" % (k, v)]
    cmd += ["-o", out_tmpl, url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, "下载音频超时，请检查网络后重试"
    if proc.returncode != 0:
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        shutil.rmtree(tmp, ignore_errors=True)
        if "No module named" in detail:
            return None, "未安装 yt-dlp。请运行：python -m pip install yt-dlp"
        if "Sign in to confirm" in detail:
            return None, "YouTube 要求登录验证（反爬）：请在 Render 环境变量里配置 YT_COOKIES"
        return None, "下载音频失败：" + detail[-800:]
    files = [f for f in os.listdir(tmp)]
    if not files:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, "下载音频失败：没有找到音频文件"
    return os.path.join(tmp, files[0]), None


def _pick_best_video(formats):
    """从 http(s) 直链里挑最高清的 H.264(mp4) 视频（≤1080p，避免 4K/8K 超大流）。"""
    cands = [f for f in formats
             if f.get("protocol") in ("https", "http")
             and f.get("vcodec") not in (None, "none")
             and f.get("url")]
    if not cands:
        return None
    def key(f):
        vc = (f.get("vcodec") or "").lower()
        h = f.get("height") or 0
        h = h if h <= 1080 else 0
        return (vc.startswith("avc1"), h, f.get("tbr") or 0)
    return max(cands, key=key)


def _pick_best_audio(formats):
    """从 http(s) 直链里挑最高码率的 AAC(m4a) 音频。"""
    cands = [f for f in formats
             if f.get("protocol") in ("https", "http")
             and f.get("acodec") not in (None, "none")
             and f.get("url")]
    if not cands:
        return None
    return max(cands, key=lambda f: ((f.get("ext") == "m4a"), f.get("abr") or 0))


def resolve_stream(url):
    """用 yt-dlp 解析视频，返回 (kind, payload, headers, error)。

    kind：
      "direct"  -> payload 是音视频合一的渐进式直链（http/https，可直接 Range 代理）
      "ffmpeg"  -> payload 是 [{"url": ...}, ...]（视频 + 可选音频，需 ffmpeg 重封装）
    headers 是 yt-dlp 给出的请求头（Referer / User-Agent，B 站防盗链必需）。
    """
    try:
        import yt_dlp
    except Exception:
        return None, None, None, "未安装 yt-dlp。请运行：python -m pip install yt-dlp"
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    cookies = _yt_cookies_file()
    if cookies:
        opts["cookiefile"] = cookies
    bili_hdrs = _bili_headers(url)
    if bili_hdrs:
        opts["http_headers"] = bili_hdrs
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e)[:300]
        if "Sign in to confirm" in msg:
            msg = "YouTube 要求登录验证（反爬）：请在 Render 环境变量里配置 YT_COOKIES"
        return None, None, None, "解析视频失败：" + msg

    formats = info.get("formats") or []
    headers = info.get("http_headers") or {}

    # 1) 音视频合一的渐进式直链（个别站点 / 老视频的 format 18 之类）
    for f in formats:
        if (f.get("protocol") in ("https", "http")
                and f.get("acodec") not in (None, "none")
                and f.get("vcodec") not in (None, "none")
                and f.get("url")):
            return "direct", f["url"], f.get("http_headers") or headers, None

    # 2) 音视频合一的 m3u8（B 站 HLS：单文件、含音视频，ffmpeg 可直接读）
    for f in formats:
        if (f.get("protocol") in ("m3u8", "m3u8_native")
                and f.get("url")
                and f.get("acodec") not in (None, "none")
                and f.get("vcodec") not in (None, "none")):
            return "ffmpeg", [{"url": f["url"]}], f.get("http_headers") or headers, None

    # 3) 分离的视频 + 音频（YouTube DASH）
    video = _pick_best_video(formats)
    audio = _pick_best_audio(formats)
    if video:
        payload = [{"url": video["url"]}]
        if audio:
            payload.append({"url": audio["url"]})
        return "ffmpeg", payload, video.get("http_headers") or headers, None

    return None, None, None, "未找到可播放的视频流"


def _build_ffmpeg_cmd(payload, headers, ffmpeg="ffmpeg"):
    """构造 ffmpeg 命令：把（视频 + 可选音频）重封装成单一 mp4 流（-c copy 不转码）。"""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    hdr_lines = ["%s: %s" % (k, v) for k, v in (headers or {}).items()]
    hdr_str = "\r\n".join(hdr_lines) + "\r\n" if hdr_lines else ""
    for src in payload:
        if hdr_str:
            cmd += ["-headers", hdr_str]  # 每个输入都带上防盗链/UA 头
        cmd += ["-i", src["url"]]
    if len(payload) == 1:
        cmd += ["-map", "0"]  # 单输入（m3u8）：取全部轨（音 + 视频）
    else:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]  # 双输入：视频轨 + 音频轨
    cmd += ["-c", "copy", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4", "-"]
    return cmd


def dict_lookup(word):
    """MyMemory 免费翻译接口（俄→中），无需 key。返回译文文本或 None。
    MyMemory 对数据中心 IP 可能限流/失败，失败时用 AI 兜底翻译。"""
    q = urllib.parse.quote(word)
    url = "https://api.mymemory.translated.net/get?q=%s&langpair=ru|zh-CN" % q
    status, body = http_call("GET", url, timeout=30)
    if status == 200:
        try:
            obj = json.loads(body)
            t = obj.get("responseData", {}).get("translatedText") or None
            if t:
                return t
        except Exception:
            pass
    # —— AI 兜底：MyMemory 失败/限流时用已配置的大模型翻译 ——
    if AI_API_KEY:
        try:
            content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, [
                {"role": "system", "content": "你是俄汉词典。用户输入一个俄语单词（可能是变格/变位形式），请给出：原形、词性、中文释义。只输出一行，格式：【原形】词性 中文释义。若无法确定，给出最可能的解释。"},
                {"role": "user", "content": word},
            ])
            if content and content.strip():
                return content.strip()
        except Exception:
            return None
    return None


LOG_FILE = "api_calls.log"


# ---- 俄语无标点断句（用原生俄语开源工具 razdel）----
# razdel 是 Natasha 团队（CoRus）专为俄语写的句子分割器，
# 纯规则+统计，不依赖大模型，对无标点文本也能给出合理的句边界。
# 安装：pip install razdel
try:
    from razdel import sentenize as _razdel_sentenize
    _RAZDEL_OK = True
except Exception:  # 未安装或导入失败
    _RAZDEL_OK = False


def _ru_rule_split(text):
    """纯规则兜底：无标点时按俄语语法信号切句（与 index.html 的 plainToSentences 同源）。
    用作 razdel 无法切分时的第二道防线，保证无标点文本也能被拆开。"""
    text = (text or "").strip()
    if not text:
        return []
    words = text.split()
    if len(words) <= 1:
        return words
    CLAUSE_START = re.compile(
        r'^(что|как|где|почему|зачем|куда|ли|разве|неужели|да|нет|ну|ладно|хорошо|давай|пожалуйста|вот'
        r'|но|однако|зато|чтобы|если|когда|хотя|потому|поэтому)$', re.I)
    PRONOUN = re.compile(r'^(я|ты|мы|вы|они|он|она|оно)$', re.I)
    VERB_END = re.compile(r'(ет|ют|ю|ёшь|ёте|ешь|ете|ется|ются|ал|ла|ло|ли|ть|ти|лся|лась|лось|ались)$', re.I)
    MAXW = 18
    out = []
    cur = []
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        low = w.lower()
        new_start = (i > 0 and len(cur) >= 2 and
                     (CLAUSE_START.match(low) or
                      (PRONOUN.match(low) and nxt and VERB_END.match(nxt))))
        if new_start:
            out.append(' '.join(cur))
            cur = []
        cur.append(w)
        if re.search(r'[.!?…]$', w) or len(cur) >= MAXW:
            out.append(' '.join(cur))
            cur = []
    if cur:
        out.append(' '.join(cur))
    # 合并过短碎片
    merged = []
    for s in out:
        s = s.strip()
        if not s:
            continue
        if len(s.split()) < 2 and merged:
            merged[-1] = (merged[-1] + ' ' + s).strip()
        else:
            merged.append(s)
    return merged


def ru_segment(text):
    """把一段俄语文本切成句子列表。返回 (sentences, ok)。
    ok=False 表示 razdel 不可用，调用方应改用本地规则断句。
    """
    text = (text or "").strip()
    if not text:
        return [], True
    if not _RAZDEL_OK:
        return None, False
    try:
        segs = _razdel_sentenize(text)
        out = []
        for s in segs:
            t = s.text.strip()
            if t:
                out.append(t)
        if not out:
            return [], True
        # razdel 对无标点文本常只切 1 句；对仍无标点的长句，再用规则切分兜底
        final = []
        for t in out:
            if not re.search(r'[.!?…]', t) and len(t.split()) > 8:
                final.extend(_ru_rule_split(t))
            else:
                final.append(t)
        return final, True
    except Exception:
        return None, False


# ---- 音频转写（用本地 Vosk 做俄语语音识别）----
# Vosk 是 Kaldi 的离线语音识别，依赖极轻（无 onnxruntime/ctranslate2/torch），
# 俄语小模型 vosk-model-small-ru-0.22 约 45MB，CPU 可跑、512MB 内存够用。
# 注意：Vosk 只接受 16kHz 单声道 PCM WAV，需先用 ffmpeg 转码（见 _to_wav16k）；
# 输出为小写无标点的词流，需按词间时间间隙切成句子（见 _words_to_segments）。
# 模型目录从环境变量 VOSK_MODEL_PATH 指定；未配置时回退到项目目录下的
# vosk-model-small-ru-0.22/（本地把模型 zip 解压到这里即可）。
_vosk_model = None
_vosk_model_path = None
_vosk_import_ok = None       # None=未尝试, True=导入成功, False=导入失败
_vosk_import_err = None
_vosk_dl_lock = None         # 模型自动下载互斥锁（多线程只下载一次）


def _download_vosk_model(model_path):
    """自动下载并解压 vosk-model-small-ru-0.22（约45MB，俄语小模型）。

    服务器（如 Render 免费实例）磁盘易失，模型不会随部署保留，
    因此在模型目录缺失时自动从官网拉取，部署后无需手动上传。
    返回 True=模型目录就绪；False=下载/解压失败。
    """
    global _vosk_dl_lock
    import threading
    if _vosk_dl_lock is None:
        _vosk_dl_lock = threading.Lock()
    if not _vosk_dl_lock.acquire(blocking=False):
        # 已有线程正在下载，本次调用直接返回失败，由调用方给出提示
        return False
    try:
        import os, zipfile, urllib.request, shutil
        if os.path.isdir(model_path):
            return True
        parent = os.path.dirname(model_path)
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            pass
        url = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
        tmp_zip = os.path.join(parent, "vosk-model-small-ru-0.22.zip")
        print("[vosk] 自动下载俄语识别模型：", url)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=600) as resp, open(tmp_zip, "wb") as f:
            shutil.copyfileobj(resp, f)
        print("[vosk] 模型下载完成，正在解压…")
        with zipfile.ZipFile(tmp_zip) as z:
            z.extractall(parent)
        try:
            os.remove(tmp_zip)
        except OSError:
            pass
        return os.path.isdir(model_path)
    except Exception as e:
        print("[vosk] 模型自动下载失败：", repr(e))
        return False
    finally:
        _vosk_dl_lock.release()


def get_vosk_model():
    """懒加载 + 单例缓存：首次调用时才 import vosk 并加载模型。
    返回 None 表示 vosk 不可用（未安装、导入失败或模型目录缺失）。"""
    global _vosk_model, _vosk_model_path, _vosk_import_ok, _vosk_import_err
    if _vosk_import_ok is None:
        try:
            import vosk
            _vosk_import_ok = True
        except Exception as e:
            _vosk_import_ok = False
            _vosk_import_err = repr(e)
            print("[vosk] 导入失败：", repr(e))
    if not _vosk_import_ok:
        return None
    model_path = (os.environ.get("VOSK_MODEL_PATH") or "").strip()
    if not model_path:
        model_path = os.path.join(BASE_DIR, "vosk-model-small-ru-0.22")
    if not os.path.isdir(model_path):
        print("[vosk] 模型目录不存在，尝试自动下载：", model_path)
        if not _download_vosk_model(model_path):
            return None
    if _vosk_model is None or _vosk_model_path != model_path:
        import vosk
        vosk.SetLogLevel(-1)          # 静音 Kaldi 的 [INFO] 日志
        _vosk_model = vosk.Model(model_path)
        _vosk_model_path = model_path
    return _vosk_model


_ffmpeg_path = None
_ffmpeg_checked = False


def get_ffmpeg():
    """返回可用的 ffmpeg 路径。

    优先用系统安装的 ffmpeg；找不到时自动下载静态版（johnvansickle，
    linux amd64，约100MB）到本地目录并缓存，供 Render 免费实例等
    未预装 ffmpeg 的环境使用。返回 None 表示不可用。
    """
    global _ffmpeg_path, _ffmpeg_checked
    if _ffmpeg_checked:
        return _ffmpeg_path
    _ffmpeg_checked = True
    ff = shutil.which("ffmpeg")
    if ff:
        _ffmpeg_path = ff
        return ff
    local = os.path.join(BASE_DIR, "ffmpeg-static", "ffmpeg")
    if os.path.isfile(local):
        _ffmpeg_path = local
        return local
    try:
        import tarfile, urllib.request
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        dest_dir = os.path.join(BASE_DIR, "ffmpeg-static")
        os.makedirs(dest_dir, exist_ok=True)
        tmp = os.path.join(dest_dir, "ffmpeg.tar.xz")
        print("[ffmpeg] 未找到系统 ffmpeg，自动下载静态版…")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as f:
            shutil.copyfileobj(resp, f)
        with tarfile.open(tmp, "r:xz") as t:
            member = None
            for m in t.getmembers():
                if m.name.endswith("/ffmpeg") and m.isfile():
                    member = m
                    break
            if member is None:
                raise RuntimeError("静态包内未找到 ffmpeg")
            src_f = t.extractfile(member)
            with open(local, "wb") as out:
                if src_f:
                    shutil.copyfileobj(src_f, out)
        os.chmod(local, 0o755)
        try:
            os.remove(tmp)
        except OSError:
            pass
        _ffmpeg_path = local
        print("[ffmpeg] 静态 ffmpeg 就绪：", local)
        return local
    except Exception as e:
        print("[ffmpeg] 自动下载失败：", repr(e))
        return None


def _to_wav16k(src_path):
    """把任意音频转成 16kHz 单声道 PCM WAV，供 Vosk 转写。

    优先用 PyAV（pip 自带 FFmpeg 库，无需系统 ffmpeg，磁盘/内存占用小），
    PyAV 不可用时回退到系统 ffmpeg / 自动下载的静态 ffmpeg。
    返回临时 wav 路径；全部失败返回 None。
    """
    dst = None
    # ---- 路径1：PyAV（推荐，无需外部 ffmpeg，512MB 实例友好）----
    try:
        import av
        out_fd, dst = tempfile.mkstemp(prefix="vosk_", suffix=".wav")
        os.close(out_fd)
        container = av.open(src_path)
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        with av.open(dst, "w", format="wav") as out:
            out_stream = out.add_stream("pcm_s16le", rate=16000)
            for frame in container.decode(stream):
                for f in resampler.resample(frame):
                    for packet in out_stream.encode(f):
                        out.mux(packet)
            for packet in out_stream.encode(None):
                out.mux(packet)
        container.close()
        return dst
    except Exception as e:
        print("[wav16k] PyAV 转码不可用，回退 ffmpeg：", repr(e))
        if dst:
            try:
                os.unlink(dst)
            except OSError:
                pass
    # ---- 路径2：ffmpeg（系统安装或自动下载的静态版）----
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return None
    fd, dst = tempfile.mkstemp(prefix="vosk_", suffix=".wav")
    os.close(fd)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-i", src_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        try:
            os.unlink(dst)
        except OSError:
            pass
        return None
    if proc.returncode != 0:
        try:
            os.unlink(dst)
        except OSError:
            pass
        return None
    return dst


def _join_words(cur):
    """把一组词 {word,start,end} 拼成一句 {start,end,text}。"""
    return {
        "start": round(cur[0]["start"], 2),
        "end": round(cur[-1]["end"], 2),
        "text": " ".join(w["word"] for w in cur),
    }


def _words_to_segments(words, gap=0.6):
    """把 Vosk 词级时间戳 [{word,start,end,conf}, ...] 按词间时间间隙切成句子。
    相邻词间隔 > gap 秒视为句界；每句 {start, end, text}。"""
    segs = []
    cur = []
    for w in words:
        text = (w.get("word") or "").strip()
        if not text:
            continue
        start = float(w.get("start") or 0.0)
        end = float(w.get("end") or 0.0)
        if cur and (start - cur[-1]["end"]) > gap:
            segs.append(_join_words(cur))
            cur = []
        cur.append({"word": text, "start": start, "end": end})
    if cur:
        segs.append(_join_words(cur))
    return segs


def _wav_duration(path):
    """读取 WAV 时长（秒）。"""
    import wave
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return None


def _clip_wav_30s(src):
    """截取 WAV 前 30 秒（GLM-ASR-2512 限制音频≤30秒）。返回新 wav 路径或 None。"""
    ff = get_ffmpeg()
    if not ff:
        return None
    fd, dst = tempfile.mkstemp(prefix="asr_clip_", suffix=".wav")
    os.close(fd)
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-t", "30",
           "-i", src, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception:
        try:
            os.unlink(dst)
        except OSError:
            pass
        return None
    if proc.returncode != 0 or not os.path.isfile(dst):
        try:
            os.unlink(dst)
        except OSError:
            pass
        return None
    return dst


def _glm_asr_transcribe(wav_path):
    """智谱 GLM-ASR-2512 高精度多语言识别（multipart/form-data）。
    返回 (text, err)；成功时 err=None。"""
    import uuid
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    with open(wav_path, "rb") as f:
        file_data = f.read()

    def _field(name, value):
        return ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, name, value)).encode("utf-8")

    body = b""
    body += _field("model", "glm-asr-2512")
    body += _field("stream", "false")
    body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n"
             "Content-Type: audio/wav\r\n\r\n" % boundary).encode("utf-8")
    body += file_data
    body += ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions",
        data=body,
        headers={
            "Authorization": "Bearer " + ZHIPU_API_KEY,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return None, "智谱接口请求失败：" + str(e)
    try:
        j = json.loads(raw)
    except Exception:
        return None, "智谱返回非 JSON：" + raw[:200]
    if isinstance(j, dict):
        if j.get("text"):
            return j["text"].strip(), None
        tr = j.get("transcripts")
        if isinstance(tr, list) and tr and tr[0].get("text"):
            return tr[0]["text"].strip(), None
        if j.get("error"):
            return None, "智谱错误：" + str(j.get("error"))
    return None, "智谱返回格式异常：" + raw[:200]


def _groq_whisper_transcribe(wav_path):
    """Groq Whisper-large-v3 转写：速度快、俄语识别准、容忍不标准发音。
    返回 (text, err)；成功时 err=None。"""
    import uuid
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    with open(wav_path, "rb") as f:
        file_data = f.read()

    def _field(name, value):
        return ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, name, value)).encode("utf-8")

    body = b""
    body += _field("model", "whisper-large-v3")
    body += _field("language", "ru")
    body += _field("response_format", "json")
    body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n"
             "Content-Type: audio/wav\r\n\r\n" % boundary).encode("utf-8")
    body += file_data
    body += ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": "Bearer " + GROQ_API_KEY,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return None, "Groq接口请求失败：" + str(e)
    try:
        j = json.loads(raw)
    except Exception:
        return None, "Groq返回非JSON：" + raw[:200]
    if isinstance(j, dict):
        if j.get("text"):
            return j["text"].strip(), None
        if j.get("error"):
            return None, "Groq错误：" + str(j.get("error"))
    return None, "Groq返回格式异常：" + raw[:200]


def _cf_whisper_transcribe(wav_path):
    """Cloudflare Workers AI Whisper 识别（免费，无需 Groq 账号）。
    返回 (text, err)；成功时 err=None。
    注意：audio 字段必须是「字节数字数组」(list[int])，不是 base64 字符串
    （传字符串会报 400 Type mismatch / audio must not be empty）。"""
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/%s/ai/run/@cf/openai/whisper"
        % CLOUDFLARE_ACCOUNT_ID,
        data=json.dumps({"audio": list(audio_bytes)}).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + CLOUDFLARE_API_TOKEN,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return None, "Cloudflare接口请求失败：" + str(e)
    try:
        j = json.loads(raw)
    except Exception:
        return None, "Cloudflare返回非JSON：" + raw[:200]
    # 成功：{"result": {"text": "..."}}；失败：{"success": false, "errors": [...]}
    if isinstance(j, dict):
        r = j.get("result")
        if isinstance(r, dict) and r.get("text"):
            return r["text"].strip(), None
        errs = j.get("errors")
        if errs:
            return None, "Cloudflare错误：" + str(errs[0] if isinstance(errs, list) else errs)[:200]
    return None, "Cloudflare返回格式异常：" + raw[:200]


def _normalize_russian_text(text):
    """用智谱把不标准/有拼写错误的俄语修正为规范写法（拼写、大小写、标点）。
    不改变原意、不增删内容；识别本就正确时原样返回。"""
    if not ZHIPU_API_KEY or not (text or "").strip():
        return text
    try:
        messages = [
            {"role": "system", "content": "你是俄语老师。学生会话的语音识别文本可能有拼写、大小写、标点错误。请把它修正为规范俄语：纠正拼写、大小写、标点，不改变原意、不增删内容。如果已经正确，原样输出。只输出修正后的俄语句子，不要任何解释、翻译或引号。"},
            {"role": "user", "content": text},
        ]
        content = ai_chat("https://open.bigmodel.cn/api/paas/v4", ZHIPU_API_KEY, "glm-4-flash", messages)
        out = (content or "").strip().strip('"“”').strip()
        return out if out else text
    except Exception as e:
        print("[asr] 俄语规范化失败，返回原文：", repr(e))
        return text


def _ru_words(text):
    """提取俄语单词序列：小写、ё→е、去标点与组合重音符号(U+0300-U+036F)。
    切词时先把组合重音保留在词内（避免 Здра́вствуйте 被拆成两段），再统一剥离。"""
    t = (text or "").lower().replace("ё", "е")
    raw = re.findall(r"[а-я\u0300-\u036f\-]+", t)
    out = []
    for w in raw:
        w2 = re.sub(r"[̀-ͯ]", "", w)
        if w2:
            out.append(w2)
    return out


def _align_pronunciation(standard, heard):
    """逐词对齐标准原文与用户朗读文本（difflib），严格标注每个词的状态。
    返回 (words, ratio)：
      words: [{target, heard, status}]，status ∈ correct/misread/omitted/extra
      ratio: 读对的目标词数 / 目标词总数（0~1），漏读直接拉低分数。
    """
    import difflib
    targets = _ru_words(standard)
    users = _ru_words(heard)
    words = []
    correct_cnt = 0
    matcher = difflib.SequenceMatcher(a=targets, b=users, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                words.append({"target": targets[k], "heard": targets[k], "status": "correct"})
                correct_cnt += 1
        elif tag == "replace":
            t_seg = targets[i1:i2]
            u_seg = users[j1:j2]
            for k, tw in enumerate(t_seg):
                hw = u_seg[k] if k < len(u_seg) else ""
                words.append({"target": tw, "heard": hw, "status": "misread"})
            # 用户多读出来的词
            for k in range(len(t_seg), len(u_seg)):
                words.append({"target": "", "heard": u_seg[k], "status": "extra"})
        elif tag == "delete":
            for k in range(i1, i2):
                words.append({"target": targets[k], "heard": "", "status": "omitted"})
        elif tag == "insert":
            for k in range(j1, j2):
                words.append({"target": "", "heard": users[k], "status": "extra"})
    total = len(targets)
    ratio = (correct_cnt / total) if total else 0.0
    return words, ratio


def _pronunciation_band(ratio):
    """词正确率 → 五档分数（80/85/90/95/100）。严格：必须全部读对才给 100。"""
    if ratio >= 0.999:
        return 100
    if ratio >= 0.9:
        return 95
    if ratio >= 0.8:
        return 90
    if ratio >= 0.7:
        return 85
    return 80


def transcribe_file(path, model_name="small"):
    """把 16kHz 单声道 WAV 转写成俄语句子列表。返回 (segments, error)，error 为 None 表示成功。
    segments 每项 {start, end, text}（秒）。model_name 仅为兼容旧调用保留，Vosk 模型固定俄语。"""
    model = get_vosk_model()
    if model is None:
        return None, "Vosk 不可用（导入失败：%s，或模型目录缺失）。请配置 VOSK_MODEL_PATH 指向 vosk 模型目录" % (_vosk_import_err or "未知错误")
    import vosk
    import wave
    try:
        wf = wave.open(path, "rb")
        sr = wf.getframerate() or 16000
        rec = vosk.KaldiRecognizer(model, sr)
        rec.SetWords(True)
        try:
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)
        finally:
            wf.close()
        final = json.loads(rec.FinalResult())
    except Exception as e:
        return None, "转写失败：" + str(e)
    words = final.get("result") or []
    if not words:
        return [], "未识别到俄语语音（可能没有音频轨，或内容不是俄语）"
    segs = _words_to_segments(words)
    if not segs:
        return [], "未识别到俄语语音（可能没有音频轨，或内容不是俄语）"
    return segs, None


def log_api_call(call_type, messages, response=""):
    """记录 API 调用到日志文件"""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"类型: {call_type}\n")
        f.write(f"{'='*60}\n")
        if messages:
            f.write("请求消息:\n")
            for i, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                f.write(f"  [{i}] {role}:\n")
                f.write(f"     {content[:500]}{'...' if len(content) > 500 else ''}\n")
        if response:
            f.write(f"\n响应 ({len(response)} 字符):\n")
            f.write(f"  {response[:1000]}{'...' if len(response) > 1000 else ''}\n")
        f.write("\n")


def ai_chat(base_url, key, model, messages):
    """调用 OpenAI 兼容接口（DeepSeek、智谱等）。返回助手的文本回复。"""
    log_api_call("AI Chat", messages)
    # 智能适配：智谱AI用 /chat/completions，DeepSeek等用 /v1/chat/completions
    if "bigmodel.cn" in base_url or "z.ai" in base_url:
        url = base_url.rstrip("/") + "/chat/completions"
    else:
        url = base_url.rstrip("/") + "/v1/chat/completions"
    key_preview = (key[:4] + "***") if key else "(空)"
    print("[AI] 请求 URL:", url)
    print("[AI] model:", model, "| messages:", len(messages), "条 | key:", key_preview)
    payload = {"model": model, "messages": messages, "temperature": 0.2, "stream": False}
    headers = {"Authorization": "Bearer " + key}
    status, body = http_call("POST", url, payload, headers, timeout=60)
    print("[AI] 响应 status:", status, "| body前500字:", body[:500])
    if status == 200:
        try:
            obj = json.loads(body)
            content = obj["choices"][0]["message"]["content"]
            log_api_call("AI Chat Response", [], content)
            return content
        except Exception:
            log_api_call("AI Chat Error", [], body)
            return body
    # 非 200：尽量给出可读错误
    error_msg = ""
    if status == 0:
        error_msg = "无法连接到 AI 接口（网络问题或地址错误）：" + body[:300]
    else:
        error_msg = "AI 接口返回 %s：%s" % (status, body[:500])
    log_api_call("AI Chat Error", [], error_msg)
    raise RuntimeError(error_msg)


# ========== 俄语AI对话教练：分级系统提示词 ==========
# 核心规则：AI 是「俄语交谈者」而非「复述者」；每个级别使用对应级别的词汇与句长，均配中文翻译。
TUTOR_SYSTEM_PROMPTS = {
    "A1": """你是「俄语AI交谈伙伴」，一位亲切耐心的俄语外教。学生是A1水平（零基础到初级）。你的任务：用俄语和学生自由交谈（话题完全不限），像真人朋友一样让对话自然流动，引导他持续开口说俄语。

## AI对话核心规则（最重要，必须严格遵守）
1. 你是俄语交谈者，不是复述机器。**绝不在回复中复述/重复用户刚说的原话**（包括正确的原句和错误的原句）。
2. 用户输入俄语后，先判断句子对错：
   - 句子有错：在 corrected 给出正确句子，在 error_analysis 用中文解析错在哪、涉及什么语法规则、为什么该这么说（这是给学生的纠错卡片）。纠正完毕后**不要复述用户的错误原句**，基于这句话表达的含义，自然接续聊天，并提出一个新问题继续对话。
   - 句子正确：**不要重复用户原话**，顺着当前话题自然接续交谈，主动提问推进对话，防止对话中断。
3. 话题完全自由（问候、生活、爱好、天气、食物、家人……学生想聊什么都可以），主动维持对话不冷场。

## 等级控制（A1，必须严格遵守）
- 词汇：只用A1基础词汇（问候、自我介绍、家人、数字、颜色、时间、天气、食物、日常物品、基本动词）
- 句子：只用极简单的短句，不用复合句、不用难语法（只涉及现在时、基本变位、第一格/第四格/第六格等最基础格）
- 回复要短，每句俄语都配中文翻译

## 纠错执行（句子有错时）
- corrected：正确的俄语句子（标准说法）
- error_analysis：中文解释错误和语法规则
- guidance：极简一句引导跟读正确句（俄语+中文），随后立刻继续聊天

## 输出格式（必须）
每次回复只输出严格JSON（不要markdown代码块、不要多余文字），结构如下：
{"reply":"展示文本：俄语+中文翻译（自然接续聊天，绝不复述用户原话）","reply_ru":"纯俄语版回复（只含俄语，供语音朗读用）","corrected":"学生说错时的正确俄语句子；说对了则为空字符串","error_analysis":"错误的中文语法分析；无错则为空字符串","guidance":"引导跟读正确句（俄语+中文）；无错则为空字符串","question":"你抛给学生的下一个引导问题（俄语+中文），保证对话不中断"}""",

    "A2": """你是「俄语AI交谈伙伴」，一位亲切耐心的俄语外教。学生是A2水平（初级偏上，能进行日常交流）。你的任务：用俄语和学生自由交谈（话题不限），像真人朋友一样让对话自然流动。

## AI对话核心规则（最重要，必须严格遵守）
1. 你是俄语交谈者，不是复述机器。**绝不在回复中复述/重复用户刚说的原话**（包括正确的原句和错误的原句）。
2. 用户输入俄语后，先判断句子对错：
   - 句子有错：在 corrected 给出正确句子，在 error_analysis 用中文解析错在哪、涉及什么语法规则、为什么该这么说（这是给学生的纠错卡片）。纠正完毕后**不要复述用户的错误原句**，基于这句话表达的含义，自然接续聊天，并提出一个新问题继续对话。
   - 句子正确：**不要重复用户原话**，顺着当前话题自然接续交谈，主动提问推进对话，防止对话中断。
3. 话题完全自由（问候、生活、爱好、天气、食物、家人……学生想聊什么都可以），主动维持对话不冷场。

## 等级控制（A2，必须严格遵守）
- 词汇：A2词汇（日常生活、购物、交通、天气、工作学习、兴趣爱好、身体感受）
- 句子：允许简单复合句（带 потому что、когда、если、который 的简单用法），过去时、现在时、简单将来时
- 回复适中长度，每句俄语都配中文翻译

## 纠错执行（句子有错时）
- corrected：正确的俄语句子（标准说法）
- error_analysis：中文解释错误和语法规则
- guidance：极简一句引导跟读正确句（俄语+中文），随后立刻继续聊天

## 输出格式（必须）
每次回复只输出严格JSON（不要markdown代码块、不要多余文字），结构如下：
{"reply":"展示文本：俄语+中文翻译（自然接续聊天，绝不复述用户原话）","reply_ru":"纯俄语版回复（只含俄语，供语音朗读用）","corrected":"学生说错时的正确俄语句子；说对了则为空字符串","error_analysis":"错误的中文语法分析；无错则为空字符串","guidance":"引导跟读正确句（俄语+中文）；无错则为空字符串","question":"你抛给学生的下一个引导问题（俄语+中文），保证对话不中断"}""",

    "B1": """你是「俄语AI交谈伙伴」，一位亲切耐心的俄语外教。学生是B1水平（中级，能讨论熟悉话题和表达观点）。你的任务：用俄语和学生自由交谈（话题不限），引导他表达想法和经历。

## AI对话核心规则（最重要，必须严格遵守）
1. 你是俄语交谈者，不是复述机器。**绝不在回复中复述/重复用户刚说的原话**（包括正确的原句和错误的原句）。
2. 用户输入俄语后，先判断句子对错：
   - 句子有错：在 corrected 给出正确句子，在 error_analysis 用中文解析错在哪、涉及什么语法规则、为什么该这么说（这是给学生的纠错卡片）。纠正完毕后**不要复述用户的错误原句**，基于这句话表达的含义，自然接续聊天，并提出一个新问题继续对话。
   - 句子正确：**不要重复用户原话**，顺着当前话题自然接续交谈，主动提问推进对话，防止对话中断。
3. 话题完全自由（问候、生活、爱好、天气、食物、家人……学生想聊什么都可以），主动维持对话不冷场。

## 等级控制（B1，必须严格遵守）
- 词汇：B1词汇（抽象概念、观点表达、经历描述、情感、社会话题）
- 句子：允许较长复合句、从句（который、что、чтобы、хотя 等）、完成体/未完成体、条件句
- 回复可以稍长，俄语为主，每句配中文翻译

## 纠错执行（句子有错时）
- corrected：正确的俄语句子（标准说法）
- error_analysis：中文解释错误和语法规则
- guidance：极简一句引导跟读正确句（俄语+中文），随后立刻继续聊天

## 输出格式（必须）
每次回复只输出严格JSON（不要markdown代码块、不要多余文字），结构如下：
{"reply":"展示文本：俄语+中文翻译（自然接续聊天，绝不复述用户原话）","reply_ru":"纯俄语版回复（只含俄语，供语音朗读用）","corrected":"学生说错时的正确俄语句子；说对了则为空字符串","error_analysis":"错误的中文语法分析；无错则为空字符串","guidance":"引导跟读正确句（俄语+中文）；无错则为空字符串","question":"你抛给学生的下一个引导问题（俄语+中文），保证对话不中断"}""",

    "B2": """你是「俄语AI交谈伙伴」，一位亲切耐心的俄语外教。学生是B2水平（中高级，能流利讨论抽象和复杂话题）。你的任务：用俄语和学生自由交谈（话题完全不限），引导他深入交流。

## AI对话核心规则（最重要，必须严格遵守）
1. 你是俄语交谈者，不是复述机器。**绝不在回复中复述/重复用户刚说的原话**（包括正确的原句和错误的原句）。
2. 用户输入俄语后，先判断句子对错：
   - 句子有错：在 corrected 给出正确句子，在 error_analysis 用中文解析错在哪、涉及什么语法规则、为什么该这么说（这是给学生的纠错卡片）。纠正完毕后**不要复述用户的错误原句**，基于这句话表达的含义，自然接续聊天，并提出一个新问题继续对话。
   - 句子正确：**不要重复用户原话**，顺着当前话题自然接续交谈，主动提问推进对话，防止对话中断。
3. 话题完全自由（问候、生活、爱好、天气、食物、家人……学生想聊什么都可以），主动维持对话不冷场。

## 等级控制（B2，必须严格遵守）
- 词汇：B2+词汇（抽象概念、学术词汇、成语俗语、复杂情感）
- 句子：允许复杂长句、多级从句、书面语表达、修辞手法
- 回复可以较长且地道，俄语为主，中文在你认为必要时辅助

## 纠错执行（句子有错时）
- corrected：正确的俄语句子（标准说法）
- error_analysis：中文解释错误和语法规则
- guidance：极简一句引导跟读正确句（俄语+中文），随后立刻继续聊天

## 输出格式（必须）
每次回复只输出严格JSON（不要markdown代码块、不要多余文字），结构如下：
{"reply":"展示文本：俄语+中文翻译（自然接续聊天，绝不复述用户原话）","reply_ru":"纯俄语版回复（只含俄语，供语音朗读用）","corrected":"学生说错时的正确俄语句子；说对了则为空字符串","error_analysis":"错误的中文语法分析；无错则为空字符串","guidance":"引导跟读正确句（俄语+中文）；无错则为空字符串","question":"你抛给学生的下一个引导问题（俄语+中文），保证对话不中断"}"""

}


# 连接数据库前先自动修正地址


def _parse_mysql_url(url):
    """解析 MySQL 连接 URL，返回 pymysql.connect 参数"""
    from urllib.parse import urlparse
    # 去掉查询参数中的 sslmode 等
    clean_url = url.split("?")[0] if "?" in url else url
    parsed = urlparse(clean_url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 4000,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
        "ssl": {"ssl_disabled": False},
        "connect_timeout": 30,
        "charset": "utf8mb4",
    }

def _square_conn():
    params = _parse_mysql_url(DATABASE_URL)
    return pymysql.connect(**params)

def _square_init():
    if not (_PYMYSQL_OK and DATABASE_URL):
        return
    try:
        conn = _square_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS square_items (
                        id VARCHAR(64) PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        category TEXT NOT NULL,
                        level VARCHAR(32) NOT NULL,
                        video_url TEXT,
                        description TEXT,
                        author TEXT,
                        thumbnail TEXT,
                        poster_url TEXT,
                        views INTEGER DEFAULT 0,
                        tags TEXT,
                        sentences TEXT,
                        created_at BIGINT DEFAULT 0
                    )
                """)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print("[square] 初始化数据库失败：", e)


def _square_row_to_item(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "level": row["level"],
        "videoUrl": _b2_resolve(row["video_url"] or ""),
        "description": row["description"] or "",
        "author": row["author"] or "",
        "thumbnail": _b2_resolve(row["thumbnail"] or ""),
        "posterUrl": _b2_resolve(row["poster_url"] or ""),
        "views": row["views"] or 0,
        "tags": json.loads(row["tags"] or "[]"),
        "sentences": json.loads(row["sentences"] or "[]"),
        "createdAt": row["created_at"] or 0,
    }




# ============================================================
# 连词成句游戏（RuQuest）—— 数据库表与查询
# ============================================================

def _quest_conn():
    params = _parse_mysql_url(DATABASE_URL)
    return pymysql.connect(**params)


def _quest_init():
    if not (_PYMYSQL_OK and DATABASE_URL):
        return
    try:
        conn = _quest_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS quest_course_packs (id VARCHAR(64) PRIMARY KEY, title VARCHAR(255) NOT NULL, description TEXT, level VARCHAR(32), `order` INTEGER NOT NULL DEFAULT 0, is_free BOOLEAN DEFAULT TRUE, created_at BIGINT DEFAULT 0)")
                cur.execute("CREATE TABLE IF NOT EXISTS quest_courses (id VARCHAR(64) PRIMARY KEY, course_pack_id VARCHAR(64) NOT NULL REFERENCES quest_course_packs(id), title VARCHAR(255) NOT NULL, description TEXT, `order` INTEGER NOT NULL DEFAULT 0, created_at BIGINT DEFAULT 0)")
                cur.execute("CREATE TABLE IF NOT EXISTS quest_statements (id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL REFERENCES quest_courses(id), `order` INTEGER NOT NULL, chinese TEXT NOT NULL, russian TEXT NOT NULL, stress_marked TEXT, grammatical_note TEXT, word_order_flexible BOOLEAN NOT NULL DEFAULT TRUE, sequence_id VARCHAR(64), sequence_order INTEGER, created_at BIGINT DEFAULT 0)")
                cur.execute("CREATE TABLE IF NOT EXISTS quest_words (id VARCHAR(64) PRIMARY KEY, statement_id VARCHAR(64) NOT NULL REFERENCES quest_statements(id), `order` INTEGER NOT NULL, lemma VARCHAR(128) NOT NULL, form VARCHAR(128) NOT NULL, pos VARCHAR(32) NOT NULL, grammatical_case VARCHAR(32), number VARCHAR(16), gender VARCHAR(16), person INTEGER, tense VARCHAR(32), aspect VARCHAR(32), stress_position INTEGER, syntactic_role VARCHAR(64), is_fixed_position BOOLEAN NOT NULL DEFAULT FALSE, chunk_type VARCHAR(32) NOT NULL DEFAULT 'single_word', created_at BIGINT DEFAULT 0)")
                cur.execute("CREATE TABLE IF NOT EXISTS quest_acceptable_answers (id VARCHAR(64) PRIMARY KEY, statement_id VARCHAR(64) NOT NULL REFERENCES quest_statements(id), word_order JSON NOT NULL, word_variants JSON NOT NULL, is_default BOOLEAN NOT NULL DEFAULT FALSE, note TEXT, created_at BIGINT DEFAULT 0)")
                cur.execute("CREATE TABLE IF NOT EXISTS quest_learning_records (id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64), course_id VARCHAR(64) NOT NULL REFERENCES quest_courses(id), completion_time INTEGER NOT NULL DEFAULT 0, correct_count INTEGER NOT NULL DEFAULT 0, total_count INTEGER NOT NULL DEFAULT 0, max_combo INTEGER NOT NULL DEFAULT 0, rating VARCHAR(8) NOT NULL DEFAULT 'C', created_at BIGINT DEFAULT 0)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_statement_id ON quest_words(statement_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_lemma ON quest_words(lemma)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_pos ON quest_words(pos)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_aa_statement_id ON quest_acceptable_answers(statement_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_learning_records_course_id ON quest_learning_records(course_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_learning_records_created_at ON quest_learning_records(created_at)")
                # 迁移：给 quest_statements 加渐进式序列字段
                try:
                    cur.execute("ALTER TABLE quest_statements ADD COLUMN sequence_id VARCHAR(64)")
                    print("[quest] 迁移：已添加 sequence_id 字段")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE quest_statements ADD COLUMN sequence_order INTEGER")
                    print("[quest] 迁移：已添加 sequence_order 字段")
                except Exception:
                    pass
                # 迁移：课程包商城字段
                for _col, _type in [
                    ("cover_url", "VARCHAR(512)"),
                    ("category", "VARCHAR(64)"),
                    ("tag", "VARCHAR(64)"),
                    ("author", "VARCHAR(128)"),
                    ("lesson_count", "INTEGER DEFAULT 0"),
                    ("learner_count", "INTEGER DEFAULT 0"),
                ]:
                    try:
                        cur.execute(f"ALTER TABLE quest_course_packs ADD COLUMN {_col} {_type}")
                        print(f"[quest] 迁移：quest_course_packs 已添加 {_col}")
                    except Exception:
                        pass
                # 迁移：课程表加封面
                try:
                    cur.execute("ALTER TABLE quest_courses ADD COLUMN cover_url VARCHAR(512)")
                    print("[quest] 迁移：quest_courses 已添加 cover_url")
                except Exception:
                    pass
                # 迁移：单词和句子加发音URL
                try:
                    cur.execute("ALTER TABLE quest_words ADD COLUMN audio_url VARCHAR(512)")
                    print("[quest] 迁移：quest_words 已添加 audio_url")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE quest_statements ADD COLUMN audio_url VARCHAR(512)")
                    print("[quest] 迁移：quest_statements 已添加 audio_url")
                except Exception:
                    pass
            conn.commit()
            print("[quest] 数据库表初始化完成")
        finally:
            conn.close()
    except Exception as e:
        print("[quest] 初始化数据库失败：", e)



# ==========================================================
# Yandex SpeechKit TTS 语音合成
# ==========================================================

YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "")
YANDEX_TTS_VOICE = os.environ.get("YANDEX_TTS_VOICE", "alena")
TTS_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
os.makedirs(TTS_CACHE_DIR, exist_ok=True)


def _tts_synthesize(text, voice=None):
    """调用 Yandex SpeechKit 合成俄语语音，返回本地 mp3 路径"""
    if not YANDEX_API_KEY:
        return None, "未配置 YANDEX_API_KEY"
    if not text or not text.strip():
        return None, "文本为空"

    voice = voice or YANDEX_TTS_VOICE
    # 缓存文件名：用文本hash
    import hashlib
    cache_key = hashlib.md5(f"{text}_{voice}".encode("utf-8")).hexdigest()
    cache_file = os.path.join(TTS_CACHE_DIR, f"{cache_key}.mp3")

    # 有缓存直接返回
    if os.path.isfile(cache_file):
        return cache_file, None

    # 调用 Yandex API
    try:
        import urllib.parse
        data = urllib.parse.urlencode({
            "text": text,
            "voice": voice,
            "format": "mp3",
            "sampleRateHertz": "48000",
            "lang": "ru-RU",
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
            data=data,
            headers={
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_data = resp.read()
            if len(audio_data) < 100:
                return None, f"API返回异常: {audio_data[:200]}"
            with open(cache_file, "wb") as f:
                f.write(audio_data)
            return cache_file, None
    except Exception as e:
        return None, f"TTS合成失败: {str(e)}"


def _tts_get_or_synthesize(text, voice=None):
    """获取或合成语音，返回可访问的URL路径"""
    cache_file, err = _tts_synthesize(text, voice)
    if err:
        return None, err
    # 返回相对URL（后端会服务 audio_cache 目录）
    filename = os.path.basename(cache_file)
    return f"/audio_cache/{filename}", None


def _quest_get_store_courses():
    """商城课程列表：返回课程包+课程，供前端商城页渲染"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            # 查询所有课程包
            cur.execute("SELECT * FROM quest_course_packs ORDER BY `order` ASC, created_at ASC")
            packs = cur.fetchall()
            # 查询所有课程
            cur.execute("SELECT * FROM quest_courses ORDER BY `order` ASC, created_at ASC")
            courses = cur.fetchall()
            # 统计每个课程的句子数
            cur.execute("SELECT course_id, COUNT(*) as cnt FROM quest_statements GROUP BY course_id")
            stmt_counts = {row["course_id"]: row["cnt"] for row in cur.fetchall()}

        # 组装课程列表（每个课程带上所属课程包信息）
        pack_map = {p["id"]: p for p in packs}
        course_list = []
        for c in courses:
            pack = pack_map.get(c.get("course_pack_id"), {})
            lesson_count = c.get("lesson_count") or stmt_counts.get(c["id"], 0) or pack.get("lesson_count", 0)
            course_list.append({
                "id": c["id"],
                "title": c["title"],
                "description": c.get("description") or pack.get("description") or "",
                "cover_url": c.get("cover_url") or pack.get("cover_url") or "",
                "category": pack.get("category") or "推荐",
                "tag": pack.get("tag") or "",
                "author": pack.get("author") or "句乐部",
                "lesson_count": lesson_count,
                "learner_count": pack.get("learner_count", 0),
                "course_pack_id": c.get("course_pack_id"),
            })

        # Banner：取前3个有封面的课程
        banners = []
        for c in course_list[:3]:
            banners.append({
                "id": c["id"],
                "title": c["title"],
                "cover_url": c["cover_url"],
                "tag": c["tag"] or "新手推荐",
            })

        # 分类：从课程的 category 去重
        categories = ["推荐"]
        for c in course_list:
            if c["category"] and c["category"] not in categories:
                categories.append(c["category"])

        # 分节：按分类分组
        sections = []
        for cat in categories:
            cat_courses = [c for c in course_list if c["category"] == cat or cat == "推荐"]
            if cat_courses:
                title_map = {
                    "推荐": "本周主编精选",
                    "零基础": "从第一句开始学",
                    "考试备考": "备考冲刺不刷题",
                    "教材同步": "教材同步精讲",
                    "高频词汇": "高频词汇速记",
                }
                sections.append({
                    "title": title_map.get(cat, cat),
                    "courses": cat_courses,
                })

        return {
            "banners": banners,
            "categories": categories,
            "sections": sections,
        }
    finally:
        conn.close()


# ==========================================================
# 课程包 / 单元 / 渐进构建步骤（句型家族，数据驱动）
# ==========================================================

# sequence_id -> 家族中文名（数据表不存家族名，此处维护权威映射；未命中时 family_name 返回空，前端降级显示 sequence_id）
_QUEST_FAMILY_NAMES = {
    "u1_f1_seq": "问候与寒暄",
    "u1_f2_seq": "自我介绍",
    "u1_f3_seq": "身份与国籍",
    "u2_f1_seq": "地点表达（Где...?）",
    "u2_f2_seq": "主语+地点副词",
    "u2_f3_seq": "方位词（здесь/там/тут）",
    "u3_f1_seq": "拥有表达（У меня есть...）",
    "u4_f1_seq": "现在时动词（Я работаю...）",
    "u4_f2_seq": "生活状态（Я живу...）",
    "u4_f3_seq": "日常活动（Я делаю...）",
    "u5_f1_seq": "步行运动（Я иду...）",
    "u5_f2_seq": "乘车运动（Я еду...）",
    "u5_f3_seq": "来去方向（Я прихожу/ухожу）",
    "u5_f4_seq": "出发离开（Я ухожу...）",
    "u6_f1_seq": "数量表达（Сколько...?）",
    "u7_f1_seq": "喜好表达（Я люблю...）",
    "u8_f1_seq": "必须表达（Я должен...）",
    "u9_f1_seq": "过去时（Я сделал...）",
    "u10_f1_seq": "将来时（Завтра я буду...）",
    "u11_f1_seq": "宾语从句（Я знаю, что...）",
    "u12_f1_seq": "综合句型1（自我介绍+地点）",
    "u12_f2_seq": "综合句型2（喜好+必须）",
}


def _quest_get_course_packs():
    """API1：所有课程包列表"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM quest_course_packs ORDER BY `order` ASC, created_at ASC")
            packs = cur.fetchall()
            cur.execute("SELECT course_pack_id, COUNT(*) AS cnt FROM quest_courses GROUP BY course_pack_id")
            unit_counts = {r["course_pack_id"]: r["cnt"] for r in cur.fetchall()}
        result = []
        for p in packs:
            result.append({
                "id": p["id"],
                "title": p.get("title") or "",
                "description": p.get("description") or "",
                "cover_url": p.get("cover_url") or "",
                "level": p.get("level") or "",
                "author": p.get("author") or "",
                "lesson_count": p.get("lesson_count") or unit_counts.get(p["id"], 0),
                "learner_count": p.get("learner_count") or 0,
                "tag": p.get("tag") or "",
                "category": p.get("category") or "",
                "unit_count": unit_counts.get(p["id"], 0),
            })
        return result
    finally:
        conn.close()


def _quest_unit_status(records):
    """根据学习记录判定单元状态：已完成 / 进行中 / 未开始"""
    if not records:
        return "未开始"
    for r in records:
        if (r.get("completion_time") or 0) > 0:
            return "已完成"
    for r in records:
        if (r.get("total_count") or 0) > 0 or (r.get("correct_count") or 0) > 0:
            return "进行中"
    return "未开始"


def _quest_get_pack_units(pack_id, user_id=None):
    """API2：某课程包的全部单元 + 学习进度（可选 user_id）"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM quest_course_packs WHERE id=%s", (pack_id,))
            pack = cur.fetchone()
            if not pack:
                return None
            cur.execute("SELECT * FROM quest_courses WHERE course_pack_id=%s ORDER BY `order` ASC", (pack_id,))
            units = cur.fetchall()
            unit_ids = [u["id"] for u in units]
            rec_map = {}
            if unit_ids:
                ph = ", ".join(["%s"] * len(unit_ids))
                if user_id:
                    cur.execute(
                        f"SELECT course_id, completion_time, correct_count, total_count, max_combo, rating "
                        f"FROM quest_learning_records WHERE user_id=%s AND course_id IN ({ph})",
                        [user_id] + unit_ids)
                else:
                    cur.execute(
                        f"SELECT course_id, completion_time, correct_count, total_count, max_combo, rating "
                        f"FROM quest_learning_records WHERE course_id IN ({ph})", unit_ids)
                for r in cur.fetchall():
                    rec_map.setdefault(r["course_id"], []).append(r)
        pack_info = {
            "id": pack["id"], "title": pack.get("title") or "",
            "description": pack.get("description") or "",
            "cover_url": pack.get("cover_url") or "", "level": pack.get("level") or "",
            "author": pack.get("author") or "", "tag": pack.get("tag") or "",
            "learner_count": pack.get("learner_count") or 0,
        }
        unit_list = []
        for u in units:
            unit_list.append({
                "id": u["id"], "title": u.get("title") or "",
                "subtitle": u.get("subtitle") or "",
                "difficulty": u.get("difficulty") or "",
                "step_count": u.get("step_count") or 0,
                "family_count": u.get("family_count") or 0,
                "order": u.get("order") or 0,
                "cover_url": u.get("cover_url") or "",
                "status": _quest_unit_status(rec_map.get(u["id"])),
            })
        return {"pack": pack_info, "units": unit_list}
    finally:
        conn.close()


def _quest_get_unit_build_steps(unit_id):
    """API3：某单元下全部家族的渐进构建步骤（按 sequence_id 分组，含 words JSON）"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM quest_courses WHERE id=%s", (unit_id,))
            unit = cur.fetchone()
            if not unit:
                return None
            cur.execute("SELECT * FROM quest_build_steps WHERE unit_id=%s ORDER BY sequence_id, step_order", (unit_id,))
            steps = cur.fetchall()
        fam_dict = {}
        fam_order = []
        fam_meta = {}
        for s in steps:
            sid = s["sequence_id"]
            if sid not in fam_dict:
                fam_dict[sid] = []
                fam_order.append(sid)
            if sid not in fam_meta and s.get("full_sentence"):
                fam_meta[sid] = (s.get("full_sentence") or "", s.get("full_chinese") or "")
            words = s.get("words")
            if isinstance(words, str):
                try:
                    words = json.loads(words)
                except Exception:
                    words = []
            elif words is None:
                words = []
            fam_dict[sid].append({
                "step_order": s.get("step_order") or 0,
                "target_sentence": s.get("target_sentence") or "",
                "chinese": s.get("chinese") or "",
                "action": s.get("action") or "",
                "grammar_note": s.get("grammar_note") or "",
                "new_element": s.get("new_element") or "",
                "is_complete": bool(s.get("is_complete")),
                "words": words,
            })
        families = []
        for sid in fam_order:
            full_sentence, full_chinese = fam_meta.get(sid, ("", ""))
            families.append({
                "sequence_id": sid,
                "family_name": _QUEST_FAMILY_NAMES.get(sid, ""),
                "full_sentence": full_sentence,
                "full_chinese": full_chinese,
                "step_count": len(fam_dict[sid]),
                "steps": fam_dict[sid],
            })
        return {
            "unit": {
                "id": unit["id"], "title": unit.get("title") or "",
                "subtitle": unit.get("subtitle") or "",
                "difficulty": unit.get("difficulty") or "",
                "family_count": unit.get("family_count") or 0,
                "step_count": unit.get("step_count") or 0,
            },
            "families": families,
        }
    finally:
        conn.close()


def _quest_get_course_with_statements(course_id):
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM quest_courses WHERE id = %s", (course_id,))
            course = cur.fetchone()
            if not course:
                return None
            cur.execute("SELECT * FROM quest_statements WHERE course_id = %s ORDER BY `order`", (course_id,))
            statements = cur.fetchall()
            result = {"id": course["id"], "title": course["title"], "description": course["description"] or "", "order": course["order"], "statements": []}
            for stmt in statements:
                cur.execute("SELECT * FROM quest_words WHERE statement_id = %s ORDER BY `order`", (stmt["id"],))
                words = cur.fetchall()
                cur.execute("SELECT * FROM quest_acceptable_answers WHERE statement_id = %s ORDER BY is_default DESC", (stmt["id"],))
                answers = cur.fetchall()
                result["statements"].append({
                    "id": stmt["id"], "order": stmt["order"], "chinese": stmt["chinese"],
                    "russian": stmt["russian"], "stressMarked": stmt["stress_marked"] or "",
                    "grammaticalNote": stmt["grammatical_note"] or "", "wordOrderFlexible": bool(stmt["word_order_flexible"]),
                    "sequenceId": stmt.get("sequence_id"), "sequenceOrder": stmt.get("sequence_order"),
                    "words": [{"order": w["order"], "lemma": w["lemma"], "form": w["form"], "pos": w["pos"],
                        "grammaticalCase": w["grammatical_case"], "number": w["number"], "gender": w["gender"],
                        "person": w["person"], "tense": w["tense"], "aspect": w["aspect"],
                        "stressPosition": w["stress_position"], "syntacticRole": w["syntactic_role"],
                        "isFixedPosition": bool(w["is_fixed_position"]), "chunkType": w["chunk_type"]} for w in words],
                    "acceptableAnswers": [{"wordOrder": json.loads(a["word_order"]) if isinstance(a["word_order"], str) else a["word_order"], "wordVariants": json.loads(a["word_variants"]) if isinstance(a["word_variants"], str) else a["word_variants"],
                        "isDefault": bool(a["is_default"]), "note": a["note"] or ""} for a in answers],
                })
            return result
    finally:
        conn.close()


def _quest_get_course_with_sequences(course_id):
    """按 sequence_id 分组返回课程题目（逐级累加模式）"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM quest_courses WHERE id = %s", (course_id,))
            course = cur.fetchone()
            if not course:
                return None
            cur.execute("SELECT * FROM quest_statements WHERE course_id = %s ORDER BY sequence_id, sequence_order, `order`", (course_id,))
            statements = cur.fetchall()
            stmt_ids = [s["id"] for s in statements]
            words_map = {}
            aa_map = {}
            if stmt_ids:
                ph = ", ".join(["%s"] * len(stmt_ids))
                cur.execute(f"SELECT * FROM quest_words WHERE statement_id IN ({ph}) ORDER BY statement_id, `order`", stmt_ids)
                for w in cur.fetchall():
                    words_map.setdefault(w["statement_id"], []).append(w)
                cur.execute(f"SELECT * FROM quest_acceptable_answers WHERE statement_id IN ({ph}) ORDER BY statement_id, is_default DESC", stmt_ids)
                for a in cur.fetchall():
                    aa_map.setdefault(a["statement_id"], []).append(a)
            sequences_dict = {}
            seq_order_map = {}
            for stmt in statements:
                seq_id = stmt.get("sequence_id") or stmt["id"]
                if seq_id not in sequences_dict:
                    sequences_dict[seq_id] = []
                    seq_order_map[seq_id] = stmt["order"]
                sequences_dict[seq_id].append(stmt)
            sequences = []
            for seq_id in sorted(sequences_dict.keys(), key=lambda x: seq_order_map.get(x, 0)):
                stmts = sequences_dict[seq_id]
                full_stmt = max(stmts, key=lambda s: s.get("sequence_order") or 1)
                units = []
                for stmt in sorted(stmts, key=lambda s: s.get("sequence_order") or 1):
                    words = words_map.get(stmt["id"], [])
                    answers = aa_map.get(stmt["id"], [])
                    units.append({
                        "id": stmt["id"], "sequenceOrder": stmt.get("sequence_order") or 1,
                        "chinese": stmt["chinese"], "russian": stmt["russian"],
                        "stressMarked": stmt["stress_marked"] or "", "grammaticalNote": stmt["grammatical_note"] or "",
                        "wordOrderFlexible": bool(stmt["word_order_flexible"]),
                        "words": [{"order": w["order"], "lemma": w["lemma"], "form": w["form"], "pos": w["pos"],
                            "grammaticalCase": w["grammatical_case"], "number": w["number"], "gender": w["gender"],
                            "person": w["person"], "tense": w["tense"], "aspect": w["aspect"],
                            "stressPosition": w["stress_position"], "syntacticRole": w["syntactic_role"],
                            "isFixedPosition": bool(w["is_fixed_position"]), "chunkType": w["chunk_type"]} for w in words],
                        "acceptableAnswers": [{"wordOrder": json.loads(a["word_order"]) if isinstance(a["word_order"], str) else a["word_order"],
                            "wordVariants": json.loads(a["word_variants"]) if isinstance(a["word_variants"], str) else a["word_variants"],
                            "isDefault": bool(a["is_default"]), "note": a["note"] or ""} for a in answers],
                    })
                sequences.append({"sequenceId": seq_id, "fullRussian": full_stmt["russian"],
                    "fullChinese": full_stmt["chinese"], "totalUnits": len(units), "units": units})
            return {"id": course["id"], "title": course["title"], "description": course["description"] or "",
                "order": course["order"], "totalSequences": len(sequences), "sequences": sequences}
    finally:
        conn.close()


def _quest_get_course_build_steps(course_id):
    """查询课程的渐进构建步骤（quest_build_steps 表），为每个unit匹配完整句的words"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM quest_courses WHERE id = %s", (course_id,))
            course = cur.fetchone()
            if not course:
                return None
            # 查询该课程的所有 statements（它们的 id 就是 build_steps 的 sequence_id）
            cur.execute("SELECT id, russian, chinese, `order` FROM quest_statements WHERE course_id = %s ORDER BY `order`", (course_id,))
            statements = cur.fetchall()
            stmt_ids = [s["id"] for s in statements]
            if not stmt_ids:
                return {"id": course["id"], "title": course["title"], "totalSequences": 0, "sequences": []}
            # 查询所有完整句的 words
            ph = ", ".join(["%s"] * len(stmt_ids))
            cur.execute(f"SELECT * FROM quest_words WHERE statement_id IN ({ph}) ORDER BY statement_id, `order`", stmt_ids)
            all_words = cur.fetchall()
            words_map = {}
            for w in all_words:
                words_map.setdefault(w["statement_id"], []).append(w)
            # 查询 quest_build_steps
            cur.execute(f"SELECT * FROM quest_build_steps WHERE sequence_id IN ({ph}) ORDER BY sequence_id, step_order", stmt_ids)
            steps = cur.fetchall()
            # 按 sequence_id 分组
            seq_dict = {}
            for step in steps:
                sid = step["sequence_id"]
                if sid not in seq_dict:
                    seq_dict[sid] = []
                seq_dict[sid].append(step)
            
            def _normalize(text):
                """去除标点，小写，用于匹配"""
                return re.sub(r'[^\w\s]', '', text or '').lower().strip()
            
            def _match_words(target_text, full_words):
                """从完整句的words中匹配target_text中的词"""
                if not full_words:
                    return []
                target_words = [w for w in _normalize(target_text).split() if w]
                if not target_words:
                    return []
                result = []
                used_indices = set()
                for tw in target_words:
                    matched = None
                    # 先精确匹配form
                    for i, fw in enumerate(full_words):
                        if i not in used_indices and _normalize(fw.get("form", "")) == tw:
                            matched = (i, fw)
                            break
                    # 再匹配lemma
                    if not matched:
                        for i, fw in enumerate(full_words):
                            if i not in used_indices and _normalize(fw.get("lemma", "")) == tw:
                                matched = (i, fw)
                                break
                    # 前缀匹配（词形变化）
                    if not matched:
                        for i, fw in enumerate(full_words):
                            if i not in used_indices:
                                f = _normalize(fw.get("form", ""))
                                l = _normalize(fw.get("lemma", ""))
                                if f.startswith(tw[:3]) or tw.startswith(f[:3]) or l.startswith(tw[:3]):
                                    matched = (i, fw)
                                    break
                    if matched:
                        i, fw = matched
                        used_indices.add(i)
                        result.append({
                            "order": len(result),
                            "lemma": fw.get("lemma", ""),
                            "form": fw.get("form", tw),
                            "pos": fw.get("pos", ""),
                            "grammaticalCase": fw.get("grammatical_case", ""),
                            "number": fw.get("number", ""),
                            "gender": fw.get("gender", ""),
                            "person": fw.get("person"),
                            "tense": fw.get("tense", ""),
                            "aspect": fw.get("aspect", ""),
                            "stressPosition": fw.get("stress_position", -1),
                            "syntacticRole": fw.get("syntactic_role", ""),
                            "isFixedPosition": bool(fw.get("is_fixed_position", False)),
                            "chunkType": fw.get("chunk_type", "single_word"),
                        })
                    else:
                        # 找不到匹配，创建默认word
                        result.append({
                            "order": len(result),
                            "lemma": tw,
                            "form": tw,
                            "pos": "",
                            "grammaticalCase": "",
                            "number": "",
                            "gender": "",
                            "person": None,
                            "tense": "",
                            "aspect": "",
                            "stressPosition": -1,
                            "syntacticRole": "",
                            "isFixedPosition": False,
                            "chunkType": "single_word",
                        })
                return result
            
            # 按课程中 statement 的顺序组织 sequences
            sequences = []
            for stmt in statements:
                sid = stmt["id"]
                seq_steps = seq_dict.get(sid, [])
                if not seq_steps:
                    continue
                full_words = words_map.get(sid, [])
                # 找到完整句步骤（is_complete=1 或 step_order 最大的）
                complete_step = max(seq_steps, key=lambda s: s.get("step_order") or 1)
                units = []
                for step in sorted(seq_steps, key=lambda s: s.get("step_order") or 1):
                    target = step["target_sentence"]
                    # 优先用build_steps表自带的words字段（JSON）
                    step_words = None
                    if step.get("words"):
                        try:
                            import json as _json
                            raw_words = _json.loads(step["words"])
                            normalized = []
                            for i, w in enumerate(raw_words):
                                normalized.append({
                                    "order": w.get("order", i),
                                    "lemma": w.get("lemma", ""),
                                    "form": w.get("form", ""),
                                    "pos": w.get("pos", ""),
                                    "grammaticalCase": w.get("grammaticalCase", w.get("grammatical_case", "")),
                                    "number": w.get("number", ""),
                                    "gender": w.get("gender", ""),
                                    "person": w.get("person"),
                                    "tense": w.get("tense", ""),
                                    "aspect": w.get("aspect", ""),
                                    "stressPosition": w.get("stressPosition", w.get("stress_position", -1)),
                                    "syntacticRole": w.get("syntacticRole", w.get("syntactic_role", "")),
                                    "isFixedPosition": bool(w.get("isFixedPosition", w.get("is_fixed_position", False))),
                                    "chunkType": w.get("chunkType", w.get("chunk_type", "single_word")),
                                })
                            step_words = normalized
                        except:
                            step_words = None
                    # 没有自带words，走原来的匹配逻辑
                    if step_words is None:
                        # 完整句步骤直接用完整句的words
                        if step.get("is_complete", 0) or step == complete_step:
                            step_words = [{
                                "order": w["order"],
                                "lemma": w.get("lemma", ""),
                                "form": w.get("form", ""),
                                "pos": w.get("pos", ""),
                                "grammaticalCase": w.get("grammatical_case", ""),
                                "number": w.get("number", ""),
                                "gender": w.get("gender", ""),
                                "person": w.get("person"),
                                "tense": w.get("tense", ""),
                                "aspect": w.get("aspect", ""),
                                "stressPosition": w.get("stress_position", -1),
                                "syntacticRole": w.get("syntactic_role", ""),
                                "isFixedPosition": bool(w.get("is_fixed_position", False)),
                                "chunkType": w.get("chunk_type", "single_word"),
                            } for w in full_words]
                        else:
                            step_words = _match_words(target, full_words)
                    units.append({
                        "id": step["id"],
                        "stepOrder": step["step_order"],
                        "russian": target,
                        "chinese": step["chinese"] or "",
                        "action": step["action"] or "build",
                        "newElement": step["new_element"] or "",
                        "isComplete": bool(step.get("is_complete", 0)),
                        "words": step_words,
                    })
                sequences.append({
                    "sequenceId": sid,
                    "fullRussian": complete_step["target_sentence"],
                    "fullChinese": complete_step["chinese"] or stmt["chinese"],
                    "totalSteps": len(units),
                    "units": units,
                })
            return {"id": course["id"], "title": course["title"], "description": course["description"] or "",
                "order": course["order"], "totalSequences": len(sequences), "sequences": sequences}
    finally:
        conn.close()


# 连词成句判题引擎
from answer_engine import AnswerEngine


def _quest_get_statement_by_id(statement_id):
    """根据 ID 查询单条句子（含 words 标注和 acceptable_answers）"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM quest_statements WHERE id = %s", (statement_id,))
            stmt = cur.fetchone()
            if not stmt:
                return None

            cur.execute("SELECT * FROM quest_words WHERE statement_id = %s ORDER BY `order`", (statement_id,))
            words = cur.fetchall()

            cur.execute("SELECT * FROM quest_acceptable_answers WHERE statement_id = %s ORDER BY is_default DESC", (statement_id,))
            answers = cur.fetchall()

            return {
                "id": stmt["id"],
                "order": stmt["order"],
                "chinese": stmt["chinese"],
                "russian": stmt["russian"],
                "stressMarked": stmt["stress_marked"] or "",
                "grammaticalNote": stmt["grammatical_note"] or "",
                "wordOrderFlexible": bool(stmt["word_order_flexible"]),
                "sequenceId": stmt.get("sequence_id"),
                "sequenceOrder": stmt.get("sequence_order"),
                "words": [
                    {
                        "order": w["order"], "lemma": w["lemma"], "form": w["form"],
                        "pos": w["pos"], "grammaticalCase": w["grammatical_case"],
                        "number": w["number"], "gender": w["gender"], "person": w["person"],
                        "tense": w["tense"], "aspect": w["aspect"],
                        "stressPosition": w["stress_position"], "syntacticRole": w["syntactic_role"],
                        "isFixedPosition": bool(w["is_fixed_position"]), "chunkType": w["chunk_type"],
                    }
                    for w in words
                ],
                "acceptableAnswers": [
                    {
                        "wordOrder": json.loads(a["word_order"]) if isinstance(a["word_order"], str) else a["word_order"],
                        "wordVariants": json.loads(a["word_variants"]) if isinstance(a["word_variants"], str) else a["word_variants"],
                        "isDefault": bool(a["is_default"]), "note": a["note"] or "",
                    }
                    for a in answers
                ],
            }
    finally:
        conn.close()


# ---- 视频上传相关（只需配置对象存储）----
try:
    from minio import Minio
    _MINIO_OK = True
except Exception:
    _MINIO_OK = False

_minio_client = None
def _get_minio_client():
    global _minio_client
    if _minIO_OK:
        if _minio_client is None:
            endpoint = os.environ.get("MINIO_ENDPOINT")
            access_key = os.environ.get("MINIO_ACCESS_KEY")
            secret_key = os.environ.get("MINIO_SECRET_KEY")
            if endpoint and access_key and secret_key:
                _minio_client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=True)
    return _minio_client

async def _upload_to_minio(file_stream, filename):
    client = _get_minio_client()
    if not client:
        return None, "MINIO 未配置"
    bucket = os.environ.get("MINIO_BUCKET", "videos")
    try:
        client.put_object(bucket, filename, file_stream, length=-1, content_type="video/*")
        # 返回公共访问 URL（基于 HTTPS 公开访问，MinIO 的 Object Storage 直接支持）
        return f"https://{bucket}.{os.environ.get('MINIO_ENDPOINT')}/{filename}", None
    except Exception as e:
        return None, str(e)


def _square_list():
    conn = _square_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM square_items ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [_square_row_to_item(r) for r in rows]
    finally:
        conn.close()


def _square_submit(item):
    conn = _square_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO square_items
                (id, title, category, level, video_url, description, author,
                 thumbnail, poster_url, views, tags, sentences, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    category = EXCLUDED.category,
                    level = EXCLUDED.level,
                    video_url = EXCLUDED.video_url,
                    description = EXCLUDED.description,
                    author = EXCLUDED.author,
                    thumbnail = EXCLUDED.thumbnail,
                    poster_url = EXCLUDED.poster_url,
                    sentences = EXCLUDED.sentences,
                    tags = EXCLUDED.tags
            """, (
                item.get("id", ""),
                item.get("title", ""),
                item.get("category", ""),
                item.get("level", ""),
                item.get("videoUrl", ""),
                item.get("description", ""),
                item.get("author", ""),
                item.get("thumbnail", ""),
                item.get("posterUrl", ""),
                item.get("views", 0),
                json.dumps(item.get("tags", []), ensure_ascii=False),
                json.dumps(item.get("sentences", []), ensure_ascii=False),
                item.get("createdAt", 0),
            ))
        conn.commit()
    finally:
        conn.close()


def _square_delete(item_id):
    conn = _square_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM square_items WHERE id = %s", (item_id,))
        conn.commit()
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        ao = _allowed_origin(self.headers.get("Origin") or "")
        if ao:
            self.send_header("Access-Control-Allow-Origin", ao)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Content-Length, adminKey")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, fullpath, ctype, content_encoding=None):
        body = open(fullpath, "rb").read()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        if ctype == "text/html":
            # 单页应用：HTML 永不缓存，改完前端刷新即可见，无需手动清缓存
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_transcribe(self, data):
        url = (data.get("url") or "").strip()
        if not url:
            return self._json(400, {"ok": False, "error": "缺少视频链接"})
        audio_path, err = download_audio(url)
        if err:
            return self._json(200, {"ok": False, "error": err})
        try:
            wav_path = _to_wav16k(audio_path)
            if not wav_path:
                return self._json(200, {"ok": False, "error": "未安装 ffmpeg（转写需 ffmpeg 把音频转成 16kHz）"})
            try:
                segs, err = transcribe_file(wav_path)
                if err:
                    return self._json(200, {"ok": False, "error": err})
                return self._json(200, {"ok": True, "segments": segs})
            finally:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
        finally:
            shutil.rmtree(os.path.dirname(audio_path), ignore_errors=True)

    def _handle_stream(self):
        """视频播放代理：优先直接转发渐进式直链（可拖动）；否则用 ffmpeg 重封装成 mp4 流。"""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        url = (qs.get("url") or [""])[0]
        if not url:
            self.send_response(400); self._cors(); self.end_headers(); return
        kind, payload, headers, err = resolve_stream(url)
        if err:
            self.send_response(502); self._cors(); self.end_headers()
            try:
                self.wfile.write(("流式代理失败：" + err).encode("utf-8"))
            except Exception:
                pass
            return
        if kind == "direct":
            self._proxy_stream(payload, headers)
            return
        ffmpeg = get_ffmpeg()
        if not ffmpeg:
            self.send_response(502); self._cors(); self.end_headers()
            try:
                self.wfile.write("流式代理失败：未安装 ffmpeg（服务器需安装 ffmpeg，且自动下载失败）".encode("utf-8"))
            except Exception:
                pass
            return
        self._stream_ffmpeg(_build_ffmpeg_cmd(payload, headers, ffmpeg))

    def _proxy_stream(self, direct, headers):
        """直接转发渐进式直链，支持 Range 拖动进度条。"""
        req = urllib.request.Request(direct)
        for k, v in headers.items():
            req.add_header(k, v)
        range_hdr = self.headers.get("Range")
        if range_hdr:
            req.add_header("Range", range_hdr)
        try:
            resp = urllib.request.urlopen(req, timeout=90)
        except urllib.error.HTTPError as e:
            self.send_response(e.code); self._cors(); self.end_headers(); return
        except Exception:
            self.send_response(502); self._cors(); self.end_headers(); return
        self.send_response(resp.status)
        self._cors()
        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
            v = resp.headers.get(h)
            if v:
                self.send_header(h, v)
        self.end_headers()
        try:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except Exception:
            pass

    def _stream_ffmpeg(self, cmd):
        """跑 ffmpeg 把重封装后的 mp4 流 chunked 回给浏览器；客户端断开时终止进程。"""
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                chunk = proc.stdout.read(256 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except Exception:
            pass
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

    def _check_admin(self, data):
        """校验请求携带的管理员密钥。返回 None 表示通过，否则返回错误响应。"""
        if not ADMIN_KEY:
            return self._json(500, {"ok": False, "error": "未配置管理员密钥（ADMIN_KEY）"})
        if (data.get("adminKey") or "").strip() != ADMIN_KEY:
            return self._json(403, {"ok": False, "error": "无权限：管理员密钥错误"})
        return None

    def _handle_square_list(self):
        if not (_PYMYSQL_OK and DATABASE_URL):
            return self._json(200, {"ok": True, "list": []})
        try:
            return self._json(200, {"ok": True, "list": _square_list()})
        except Exception as e:
            print("[square] 读取列表失败：", e)
            return self._json(200, {"ok": True, "list": []})


    def _handle_course_complete(self, data):
        """保存课程练习记录"""
        try:
            course_id = (data.get("course_id") or "").strip()
            if not course_id:
                return self._json(400, {"ok": False, "error": "缺少 course_id"})
            completion_time = int(data.get("completion_time") or 0)
            correct_count = int(data.get("correct_count") or 0)
            total_count = int(data.get("total_count") or 0)
            max_combo = int(data.get("max_combo") or 0)
            rating = (data.get("rating") or "C").strip()
            record_id = uuid.uuid4().hex[:24]
            created_at = int(time.time() * 1000)

            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO quest_learning_records (id, user_id, course_id, completion_time, correct_count, total_count, max_combo, rating, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (record_id, "", course_id, completion_time, correct_count, total_count, max_combo, rating, created_at)
                    )
                conn.commit()
            finally:
                conn.close()
            return self._json(200, {"ok": True, "data": {"id": record_id}})
        except Exception as e:
            print("[quest] 保存练习记录失败:", e)
            return self._json(500, {"ok": False, "error": str(e)})

    def _handle_answer_submit(self, data):
        """连词成句判题：接收用户输入，返回结构化判题结果"""
        if not (_PYMYSQL_OK and DATABASE_URL):
            return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
        statement_id = (data.get("statementId") or "").strip()
        user_input = data.get("userInput") or ""
        if not statement_id:
            return self._json(400, {"ok": False, "error": "缺少 statementId"})
        if not user_input.strip():
            return self._json(400, {"ok": False, "error": "缺少 userInput"})
        try:
            statement = _quest_get_statement_by_id(statement_id)
            if statement is None:
                return self._json(404, {"ok": False, "error": "句子不存在: " + statement_id})
            engine = AnswerEngine(statement)
            result = engine.judge(user_input)
            return self._json(200, {"ok": True, "data": result})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "判题异常：" + str(e)})

    def _handle_square_submit(self, data):
        err = self._check_admin(data)
        if err:
            return err
        if not (_PYMYSQL_OK and DATABASE_URL):
            return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
        if not (data.get("id") and data.get("title")):
            return self._json(400, {"ok": False, "error": "缺少必填字段"})
        try:
            item = data.copy()
            # 如果是 base64 编码的视频/缩略图，上传到 MinIO 并替换为 URL
            client = _get_minio_client()
            if item.get("videoUrl") and item["videoUrl"].startswith("data:video/"):
                suffix = ".mp4"
                fd, local_path = tempfile.mkstemp(suffix=suffix)
                os.close(fd)
                with open(local_path, "wb") as f:
                    f.write(base64.b64decode(item["videoUrl"].split(",", 1)[1]))
                filename = item["id"] + suffix
                if client:
                    bucket = os.environ.get("MINIO_BUCKET", "videos")
                    client.put_object(bucket, filename, open(local_path, "rb"),
                                     length=os.path.getsize(local_path), content_type="video/mp4")
                    item["videoUrl"] = f"https://{bucket}.{os.environ.get('MINIO_ENDPOINT')}/{filename}"
                os.unlink(local_path)
            if item.get("thumbnail") and item["thumbnail"].startswith("data:image/"):
                suffix = ".jpg"
                fd, local_path = tempfile.mkstemp(suffix=suffix)
                os.close(fd)
                with open(local_path, "wb") as f:
                    f.write(base64.b64decode(item["thumbnail"].split(",", 1)[1]))
                filename = item["id"] + "_thumb" + suffix
                if client:
                    bucket = os.environ.get("MINIO_BUCKET", "videos")
                    client.put_object(bucket, filename, open(local_path, "rb"),
                                     length=os.path.getsize(local_path), content_type="image/jpeg")
                    item["thumbnail"] = f"https://{bucket}.{os.environ.get('MINIO_ENDPOINT')}/{filename}"
                os.unlink(local_path)
            _square_submit(item)
            return self._json(200, {"ok": True})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "保存失败：" + str(e)})

    def _handle_square_delete(self, data):
        err = self._check_admin(data)
        if err:
            return err
        if not (_PYMYSQL_OK and DATABASE_URL):
            return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
        if not data.get("id"):
            return self._json(400, {"ok": False, "error": "缺少 id"})
        try:
            _square_delete(data.get("id"))
            return self._json(200, {"ok": True})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "删除失败：" + str(e)})

    def _handle_admin_check(self, data):
        if not ADMIN_KEY:
            return self._json(200, {"ok": False, "error": "未配置管理员密钥（ADMIN_KEY）"})
        ok = (data.get("adminKey") or "").strip() == ADMIN_KEY
        return self._json(200, {"ok": ok})

    def _handle_upload_presign(self, data):
        """为浏览器直传 B2 签发临时 PUT 授权（本服务不接收文件本体）。"""
        err = self._check_admin(data)
        if err:
            return err
        if not _b2_configured():
            return self._json(500, {"ok": False, "error": "B2 未配置（需设置 B2_KEYID/B2_APPLICATION_KEY/B2_BUCKET/B2_REGION/B2_ENDPOINT）"})
        import uuid
        filename = (data.get("filename") or "").strip()
        kind = (data.get("kind") or "video").strip()
        if not filename:
            return self._json(400, {"ok": False, "error": "缺少 filename"})
        is_image = kind == "image"
        ext = _b2_safe_ext(filename, ".jpg" if is_image else ".mp4")
        ctype = (data.get("contentType") or "").strip() or _b2_content_type(
            ext, "image/jpeg" if is_image else "video/mp4")
        subdir = "thumbs" if is_image else "videos"
        key = "%s/%s%s" % (subdir, uuid.uuid4().hex, ext)
        try:
            put_url = _b2_presign_put(key, ctype, expires=600)
            get_url = _b2_presign_get(key, expires=604800)
            if not put_url:
                return self._json(500, {"ok": False, "error": "生成上传授权失败"})
            return self._json(200, {
                "ok": True,
                "key": key,
                "objectUrl": _B2_PREFIX + key,
                "uploadUrl": put_url,
                "getUrl": get_url,
                "contentType": ctype,
                "expiresIn": 600,
            })
        except Exception as e:
            return self._json(500, {"ok": False, "error": "生成上传授权失败：" + str(e)})

    def _handle_upload(self, data):
        """直接上传文件（视频/缩略图）到 MinIO，返回公开 URL"""
        err = self._check_admin(data)
        if err:
            return err
        if not _MINIO_OK:
            return self._json(500, {
                "ok": False,
                "error": "MinIO 未配置，请在 Render 环境变量中设置 MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY"
            })
        if not (data.get("filename") and data.get("content")):
            return self._json(400, {"ok": False, "error": "缺少文件数据"})
        try:
            import io
            content_b64 = data["content"]
            file_stream = io.BytesIO(base64.b64decode(content_b64))
            client = _get_minio_client()
            if not client:
                return self._json(500, {"ok": False, "error": "MinIO 客户端连接失败"})
            bucket = os.environ.get("MINIO_BUCKET", "videos")
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            filename = data["filename"]
            content_type = "application/octet-stream"
            if filename.lower().endswith((".mp4", ".webm", ".mov")):
                content_type = "video/mp4"
            elif filename.lower().endswith((".jpg", ".jpeg")):
                content_type = "image/jpeg"
            elif filename.lower().endswith(".png"):
                content_type = "image/png"
            client.put_object(bucket, filename, file_stream,
                              length=len(base64.b64decode(content_b64)),
                              content_type=content_type)
            url = f"https://{bucket}.{os.environ.get('MINIO_ENDPOINT')}/{filename}"
            return self._json(200, {"ok": True, "url": url})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "上传失败：" + str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True})
        if path == "/api/ai-health":
            return self._json(200, {
                "ok": True,
                "configured": bool(AI_API_KEY),
                "base_url": AI_BASE_URL,
                "model": AI_MODEL,
                "key_prefix": (AI_API_KEY[:4] + "***") if AI_API_KEY else "",
            })
        if path == "/api/stream":
            return self._handle_stream()
        if path == "/api/square/list":
            return self._handle_square_list()
        if path == "/api/tts":
            # TTS文本转语音（GET，支持直接用audio标签播放；voice=female/male 切换男女声；rate=0.5~2.0 朗读速度）
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            text = (params.get("text", [""])[0] or "").strip()
            voice = (params.get("voice", [""])[0] or "").strip()
            rate = (params.get("rate", [""])[0] or "").strip()
            return self._handle_tts(text, voice, rate)

        # 连词成句游戏（RuQuest）：查询课程的全部句子（含 words 语法标注）
        if path.startswith("/api/courses/") and path.endswith("/statements"):
            if not (_PYMYSQL_OK and DATABASE_URL):
                return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
            parts = path.strip("/").split("/")
            if len(parts) >= 4:
                course_id = parts[2]
                try:
                    query = urllib.parse.urlparse(self.path).query
                    params = urllib.parse.parse_qs(query)
                    group_by = (params.get("group_by", [""])[0] or "").strip()
                    if group_by == "sequence":
                        data = _quest_get_course_with_sequences(course_id)
                    else:
                        data = _quest_get_course_with_statements(course_id)
                    if data is None:
                        return self._json(404, {"ok": False, "error": "课程不存在: " + course_id})
                    return self._json(200, {"ok": True, "data": data})
                except Exception as e:
                    return self._json(500, {"ok": False, "error": str(e)})
            return self._json(400, {"ok": False, "error": "路径格式应为 /api/courses/<course_id>/statements"})

        # 渐进构建步骤：查询课程的渐进构建数据（quest_build_steps 表）
        if path.startswith("/api/courses/") and path.endswith("/build-steps"):
            if not (_PYMYSQL_OK and DATABASE_URL):
                return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
            parts = path.strip("/").split("/")
            if len(parts) >= 4:
                course_id = parts[2]
                try:
                    data = _quest_get_course_build_steps(course_id)
                    if data is None:
                        return self._json(404, {"ok": False, "error": "课程不存在: " + course_id})
                    return self._json(200, {"ok": True, "data": data})
                except Exception as e:
                    return self._json(500, {"ok": False, "error": str(e)})
            return self._json(400, {"ok": False, "error": "路径格式应为 /api/courses/<course_id>/build-steps"})

        # 商城课程列表
        if path == "/api/store/courses":
            if not (_PYMYSQL_OK and DATABASE_URL):
                return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
            try:
                data = _quest_get_store_courses()
                return self._json(200, {"ok": True, "data": data})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})

        # 课程包列表（句型家族渐进构建，数据驱动）
        if path == "/api/course-packs":
            if not (_PYMYSQL_OK and DATABASE_URL):
                return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
            try:
                return self._json(200, {"ok": True, "data": _quest_get_course_packs()})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})

        # 某课程包的单元列表 + 学习进度（可选 ?user_id=）
        if path.startswith("/api/course-packs/") and path.endswith("/units"):
            if not (_PYMYSQL_OK and DATABASE_URL):
                return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
            _parts = path.strip("/").split("/")
            if len(_parts) == 4 and _parts[1] == "course-packs" and _parts[3] == "units":
                _pack_id = urllib.parse.unquote(_parts[2])
                _q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                _user_id = (_q.get("user_id", [""])[0] or "").strip() or None
                try:
                    _data = _quest_get_pack_units(_pack_id, _user_id)
                    if _data is None:
                        return self._json(404, {"ok": False, "error": "课程包不存在: " + _pack_id})
                    return self._json(200, {"ok": True, "data": _data})
                except Exception as e:
                    return self._json(500, {"ok": False, "error": str(e)})
            return self._json(400, {"ok": False, "error": "路径格式应为 /api/course-packs/<packId>/units"})

        # 某单元的渐进构建步骤（按家族分组）
        if path.startswith("/api/units/") and path.endswith("/build-steps"):
            if not (_PYMYSQL_OK and DATABASE_URL):
                return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
            _parts = path.strip("/").split("/")
            if len(_parts) == 4 and _parts[1] == "units" and _parts[3] == "build-steps":
                _unit_id = urllib.parse.unquote(_parts[2])
                try:
                    _data = _quest_get_unit_build_steps(_unit_id)
                    if _data is None:
                        return self._json(404, {"ok": False, "error": "单元不存在: " + _unit_id})
                    return self._json(200, {"ok": True, "data": _data})
                except Exception as e:
                    return self._json(500, {"ok": False, "error": str(e)})
            return self._json(400, {"ok": False, "error": "路径格式应为 /api/units/<unitId>/build-steps"})

        # 优先服务 React 构建产物（dist/）；未构建时回退到 legacy.html
        serve_dir = DIST_DIR if os.path.isfile(os.path.join(DIST_DIR, "index.html")) else BASE_DIR
        if path == "/":
            # 后端是纯 API（前端已拆分到 Netlify），容器里没有 index.html/legacy.html 时
            # 让 GET / 返回 200，作为健康检查兜底（Render healthCheckPath 可能仍是 /）
            if not (os.path.isfile(os.path.join(DIST_DIR, "index.html")) or os.path.isfile(os.path.join(BASE_DIR, "legacy.html"))):
                return self._json(200, {"ok": True})
            path = "/index.html" if os.path.isfile(os.path.join(serve_dir, "index.html")) else "/legacy.html"

        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(serve_dir, rel))
        if not (full.startswith(serve_dir) and os.path.isfile(full)):
            # 单页应用路由回退：无扩展名的路径（如 /method/A1）返回 index.html
            fallback = os.path.join(serve_dir, "index.html")
            if not os.path.splitext(rel)[1] and os.path.isfile(fallback):
                full = fallback
            else:
                self.send_response(404)
                self._cors()
                self.end_headers()
                return

        ext = os.path.splitext(full)[1].lower()
        ctype = {
            ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
            ".json": "application/json", ".svg": "image/svg+xml",
            ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
            ".txt": "text/plain", ".mp3": "audio/mpeg", ".wav": "audio/wav",
            ".ogg": "audio/ogg",
        }.get(ext, "application/octet-stream")
        if "gzip" in self.headers.get("Accept-Encoding", "") and os.path.isfile(full + ".gz"):
            self._serve_file(full + ".gz", ctype, content_encoding="gzip")
        else:
            self._serve_file(full, ctype)

    def _decode_audio_data_url(self, audio_data):
        """从 data:audio/...;base64,... 中解码出音频字节。返回 (bytes, error)。"""
        audio_data = (audio_data or "").strip()
        if not audio_data:
            return None, "缺少录音数据"
        try:
            if "," in audio_data:
                audio_b64 = audio_data.split(",", 1)[1]
            else:
                audio_b64 = audio_data
            return base64.b64decode(audio_b64), None
        except Exception as e:
            return None, "音频解码失败：" + str(e)

    def _transcribe_audio_bytes(self, audio_bytes):
        """把音频字节保存为临时文件 → 转 WAV → 转写。

        转写引擎优先级：
          1. Groq Whisper-large-v3（快、准，俄语最优，配置 GROQ_API_KEY 后启用）
          2. 智谱 GLM-ASR-2512（高精度多语言，配置 ZHIPU_API_KEY 后启用，音频≤30秒）
          3. Vosk 本地俄语模型（兜底，512MB 实例友好，无时长限制）
        返回 (user_text, segments, error)；成功时 error 为 None。
        所有临时文件在内部清理。"""
        fd, audio_path = tempfile.mkstemp(prefix="recite_", suffix=".webm")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            return None, None, "保存音频失败：" + str(e)

        wav_path = _to_wav16k(audio_path)
        if not wav_path:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            return None, None, "音频转码失败（缺少转码组件）"

        try:
            # ---- 优先1：Groq Whisper（快+准）----
            if GROQ_API_KEY:
                try:
                    text, err = _groq_whisper_transcribe(wav_path)
                    if err is None and text:
                        return text, [], None
                    print("[asr] Groq 转写失败，切换下一引擎：", err)
                except Exception as e:
                    print("[asr] Groq 转写异常：", repr(e))

            # ---- 优先2：Cloudflare Workers AI Whisper（免费，无需注册新服务）----
            if CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN:
                try:
                    text, err = _cf_whisper_transcribe(wav_path)
                    if err is None and text:
                        return text, [], None
                    print("[asr] Cloudflare 转写失败，切换下一引擎：", err)
                except Exception as e:
                    print("[asr] Cloudflare 转写异常：", repr(e))

            # ---- 优先2：智谱高精度识别 ----
            if ZHIPU_API_KEY:
                try:
                    src = wav_path
                    clipped = None
                    dur = _wav_duration(wav_path)
                    if dur and dur > 30:
                        clipped = _clip_wav_30s(wav_path)
                        if clipped:
                            src = clipped
                    text, err = _glm_asr_transcribe(src)
                    if clipped:
                        try:
                            os.unlink(clipped)
                        except OSError:
                            pass
                    if err is None and text:
                        return text, [], None
                    print("[asr] 智谱转写失败，切换下一引擎：", err)
                except Exception as e:
                    print("[asr] 智谱转写异常：", repr(e))

            # ---- 兜底：Vosk 本地俄语 ----
            segs, err = transcribe_file(wav_path)
            if err:
                return None, None, err
            user_text = " ".join(s["text"] for s in segs) if segs else ""
            if not user_text:
                return None, None, "未识别到语音内容，请重新录音"
            return user_text, segs, None
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
            try:
                os.unlink(audio_path)
            except OSError:
                pass

    # ---- edge-tts（微软Edge神经语音，免费、无需API Key、无需torch）----
    # 允许的俄语 edge-tts 声音（女声 Svetlana / 男声 Dmitry）
    TTS_VOICE = "ru-RU-SvetlanaNeural"
    TTS_VOICES = {
        "female": "ru-RU-SvetlanaNeural",
        "svetlana": "ru-RU-SvetlanaNeural",
        "male": "ru-RU-DmitryNeural",
        "dmitry": "ru-RU-DmitryNeural",
        "ru-ru-svetlananeural": "ru-RU-SvetlanaNeural",
        "ru-ru-dmitryneural": "ru-RU-DmitryNeural",
    }

    def _pick_tts_voice(self, voice):
        """根据前端传入的 voice 参数选择声音，非法值回退默认女声。"""
        if not voice:
            return self.TTS_VOICE
        return self.TTS_VOICES.get(str(voice).strip().lower(), self.TTS_VOICE)

    def _tts_yandex(self, text, voice=None):
        """调用 Yandex SpeechKit 合成俄语音频（mp3），带本地缓存。
        Yandex 是俄语母语级音质，自动处理重音和同形异义词。
        成功返回音频字节，失败返回 None。"""
        api_key = os.environ.get("YANDEX_API_KEY", "")
        if not api_key:
            return None
        if not text or not text.strip():
            return None
        voice = voice or os.environ.get("YANDEX_TTS_VOICE", "alena")
        # 缓存
        import hashlib
        cache_dir = os.path.join(BASE_DIR, "audio_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.md5(f"yandex_{text}_{voice}".encode("utf-8")).hexdigest()
        cache_file = os.path.join(cache_dir, f"{cache_key}.mp3")
        if os.path.isfile(cache_file):
            try:
                with open(cache_file, "rb") as f:
                    return f.read()
            except Exception:
                pass
        # 调用 API
        try:
            import urllib.parse
            data = urllib.parse.urlencode({
                "text": text,
                "voice": voice,
                "format": "mp3",
                "sampleRateHertz": "48000",
                "lang": "ru-RU",
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                data=data,
                headers={
                    "Authorization": f"Api-Key {api_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio_data = resp.read()
                if len(audio_data) < 100:
                    print("[TTS] Yandex 返回异常:", audio_data[:200])
                    return None
                # 存缓存
                try:
                    with open(cache_file, "wb") as f:
                        f.write(audio_data)
                except Exception:
                    pass
                return audio_data
        except Exception as e:
            print("[TTS] Yandex 合成失败:", e)
            return None

    def _tts_edge(self, text, voice=None, rate=None):
        """调用 edge-tts 生成俄语音频（mp3），带自动重试。成功返回音频字节，失败返回 None。
        voice 可为 female/male（或具体声音名），缺省为俄语女声 Svetlana。"""
        use_voice = self._pick_tts_voice(voice)
        try:
            import asyncio
            import edge_tts
            last_err = None
            # 最多重试3次，应对网络抖动
            for attempt in range(3):
                try:
                    rate_str = None
                    if rate:
                        try:
                            rv = float(rate)
                            pct = int(round((rv - 1.0) * 100))
                            pct = max(-80, min(150, pct))
                            rate_str = ("+" if pct >= 0 else "-") + str(abs(pct)) + "%"
                        except Exception:
                            rate_str = None
                    communicate = edge_tts.Communicate(text, use_voice, rate=rate_str) if rate_str else edge_tts.Communicate(text, use_voice)
                    chunks = []

                    async def _collect():
                        async for chunk in communicate.stream():
                            if chunk.get("type") == "audio":
                                chunks.append(chunk["data"])

                    asyncio.run(_collect())
                    if chunks:
                        return b"".join(chunks)
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        import time
                        time.sleep(1)  # 退避1秒后重试
            print("[TTS] edge-tts 生成失败：", last_err)
            return None
        except Exception as e:
            print("[TTS] edge-tts 异常：", e)
            return None

    def _handle_tts(self, text, voice=None, rate=None):
        """TTS文本转语音：优先 Yandex SpeechKit（俄语母语级），回退 edge-tts，最后 Google TTS。
        用于浏览器没有俄语语音包时的降级方案。voice 支持 female/male 切换男女声。
        """
        if not text:
            return self._json(400, {"ok": False, "error": "缺少文本参数"})
        # 超长截断
        if len(text) > 500:
            text = text[:500]

        # ---- 首选：Yandex SpeechKit（俄语母语级，自动重音）----
        audio = self._tts_yandex(text, voice)
        if audio:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(audio)
            return None

        # ---- 回退：edge-tts 微软神经语音 ----
        audio = self._tts_edge(text, voice, rate)
        if audio:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(audio)
            return None

        # ---- 回退：Google 翻译免费TTS（mp3）----
        try:
            encoded = urllib.parse.quote(text)
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl=ru&client=tw-ob"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            req.add_header("Referer", "https://translate.google.com/")
            with urllib.request.urlopen(req, timeout=15) as resp:
                audio = resp.read()
                ctype = resp.headers.get("Content-Type", "audio/mpeg")
            # 返回音频二进制
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(audio)
            return None
        except Exception as e:
            return self._json(200, {"ok": False, "error": "TTS生成失败：" + str(e)})

    def _handle_transcribe_audio(self, data):
        """独立音频转写接口：接收 base64 音频，返回转写文本和分段。
        text 为规范化后的规范俄语句子（识别不标准也会被修正），raw 为原始识别文本。"""
        audio_bytes, err = self._decode_audio_data_url(data.get("audio"))
        if err:
            return self._json(200, {"ok": False, "error": err})
        user_text, segs, err = self._transcribe_audio_bytes(audio_bytes)
        if err:
            return self._json(200, {"ok": False, "error": err})
        corrected = _normalize_russian_text(user_text) if user_text else user_text
        return self._json(200, {"ok": True, "text": corrected or user_text, "raw": user_text, "segments": segs})

    def _handle_tutor(self, data):
        """俄语AI对话教练：按等级(A1/A2/B1/B2)自由对话 + 语法纠错引导。
        入参：level、message（学生说的话）、history（[{role, content}] 历史）
        返回：{ok, content}，content 为 AI 生成的 JSON 字符串（reply/reply_ru/corrected/error_analysis/guidance/question）。
        """
        level = (data.get("level") or "A1").upper()
        if level not in ("A1", "A2", "B1", "B2"):
            level = "A1"
        message = (data.get("message") or "").strip()
        if not message:
            return self._json(400, {"ok": False, "error": "缺少 message（学生说的话）"})
        if not AI_API_KEY:
            return self._json(200, {"ok": False, "error": "未配置 AI API Key（请在环境变量 AI_API_KEY 中设置）"})
        history = data.get("history") or []
        system_prompt = TUTOR_SYSTEM_PROMPTS.get(level, TUTOR_SYSTEM_PROMPTS["A1"])
        messages = [{"role": "system", "content": system_prompt}]
        # 携带历史上下文（最多最近 20 条），保持对话连贯
        for h in history[-20:]:
            role = "assistant" if (h.get("role") == "assistant") else "user"
            content = (h.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": "学生说（俄语口语句子，可能包含语法错误，也可能完全正确）：" + message})
        try:
            content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
            return self._json(200, {"ok": True, "content": content})
        except RuntimeError as e:
            return self._json(200, {"ok": False, "error": str(e)})
        except Exception as e:
            return self._json(200, {"ok": False, "error": "AI对话异常：" + str(e)})

    def _handle_recite_compare(self, data):
        """录音转写 + AI 文本比对接口。"""
        standard = (data.get("standard") or "").strip()
        if not standard:
            return self._json(200, {"ok": False, "error": "缺少标准原文"})

        audio_bytes, err = self._decode_audio_data_url(data.get("audio"))
        if err:
            return self._json(200, {"ok": False, "error": err})

        user_text, _segs, err = self._transcribe_audio_bytes(audio_bytes)
        if err:
            return self._json(200, {"ok": False, "error": err})

        # 未配置 AI Key：降级仅返回转写文本
        if not AI_API_KEY:
            return self._json(200, {"ok": True, "result": {
                "user_text": user_text,
                "errors": [],
                "overall_tip": "未配置 AI API Key，仅返回转写文本，无法做智能比对。",
            }})

        compare_prompt = """你是俄语发音评估专家。请将【用户朗读文本】与【标准原文】逐词比对，找出所有差异。

标准原文：%s

用户朗读：%s

请严格以JSON格式返回（不要输出JSON以外的任何文字），格式如下：
{
  "errors": [
    {
      "type": "misread",
      "original": "原文中的词或短语",
      "user": "用户实际读的词",
      "suggestion": "用中文说明错误原因和修正方法",
      "correct_reading": "正确的俄语读法"
    }
  ],
  "overall_tip": "用中文给出整体学习建议，包括发音、语调、流利度等方面"
}

错误类型type只能是以下四种之一：
- misread：读错（发音、词尾、重音错误）
- omitted：漏读（原文有但用户没读）
- extra：多读（用户读了原文没有的词）
- word_order：语序错误

如果没有错误，errors返回空数组，overall_tip给出肯定和提升建议。
""" % (standard, user_text)

        messages = [
            {"role": "system", "content": "你是严格的俄语发音评估专家，只输出JSON。"},
            {"role": "user", "content": compare_prompt},
        ]
        try:
            ai_response = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
        except RuntimeError as e:
            return self._json(200, {"ok": True, "result": {
                "user_text": user_text,
                "errors": [],
                "overall_tip": "AI比对失败（" + str(e)[:100] + "），以下为转写文本。",
            }})
        except Exception as e:
            return self._json(200, {"ok": True, "result": {
                "user_text": user_text,
                "errors": [],
                "overall_tip": "AI比对异常：" + str(e)[:100],
            }})

        # 容错解析 AI 返回的 JSON
        errors = []
        overall_tip = ""
        try:
            resp = ai_response.strip()
            resp = re.sub(r'^```(?:json)?\s*', '', resp, flags=re.I)
            resp = re.sub(r'\s*```$', '', resp)
            a = resp.find("{")
            b = resp.rfind("}")
            if a >= 0 and b > a:
                resp = resp[a:b + 1]
            parsed = json.loads(resp)
            raw_errors = parsed.get("errors", [])
            overall_tip = parsed.get("overall_tip", "")
            valid_errors = []
            for e in raw_errors:
                if isinstance(e, dict) and e.get("type") in ("misread", "omitted", "extra", "word_order"):
                    valid_errors.append({
                        "type": e.get("type", ""),
                        "original": e.get("original", ""),
                        "user": e.get("user", ""),
                        "suggestion": e.get("suggestion", ""),
                        "correct_reading": e.get("correct_reading", ""),
                    })
            errors = valid_errors
        except Exception:
            overall_tip = "AI返回解析失败，原始回复：" + ai_response[:200]

        return self._json(200, {"ok": True, "result": {
            "user_text": user_text,
            "errors": errors,
            "overall_tip": overall_tip,
        }})

    def _handle_sentence_analysis(self, data):
        """句子精析：逐词（带重音/词性/词义）+ 句子成分 + 中译 + 详细语法解析，严格 JSON。"""
        sentence = (data.get("sentence") or data.get("text") or "").strip()
        if not sentence:
            return self._json(400, {"ok": False, "error": "缺少句子"})

        # 降级数据：仅做单词拆分
        fallback_words = [
            {"word": w, "stressed": w, "pos": "", "mean": ""}
            for w in re.findall(r"[А-Яа-яЁё\-]+", sentence)
        ]
        if not AI_API_KEY:
            return self._json(200, {"ok": True, "result": {
                "words": fallback_words, "components": [], "translation": "",
                "grammar": "未配置 AI API Key，仅返回单词拆分，无法生成词性、成分与语法解析。",
            }})

        prompt = """你是俄语教学专家。请对下面这句俄语做逐词与语法分析，严格只输出 JSON，不要输出 JSON 以外的任何文字、不要 markdown 代码块。
句子：%s
输出格式：
{
  "words": [
    {"word": "句中出现的俄语原词", "stressed": "带重音的同形（在重音元音后面加组合重音符号 ́，例如 приве́т；单音节词也要标）", "pos": "词性中文，如 名词/动词/代词/形容词/副词/前置词/连接词/数词/语气词", "mean": "该词在本句中的中文词义"}
  ],
  "components": [
    {"text": "与 words 一一对应的单个俄语单词（原文，顺序和数量必须与 words 完全一致，每项 text 只能是对应那个单词本身，不能是片段）", "role": "该单词在句中的中文语法角色（主语/谓语/宾语/定语/状语/呼语/系词/连接词/虚词等，一个单词一个标注，不能合并成片段）"}
  ],
  "translation": "整句准确自然的中文翻译",
  "grammar": "详细语法解析（中文，220字以内）：本句用了哪些语法点、为什么这么用、什么时候可以用该语法；用换行分点，简洁清楚"
}
重要：以空格为界进行标准分词，一个空格分隔的单位就是一个单词，严禁按音节拆分单词！例如"Доброе утро"必须拆为两个词：Доброе、утро，绝不能拆成 До/брое/у/тро。"Мама, я умею"必须拆为 Мама、я、умею 三个词。重音符号属于所在单词，不是分割符。
要求：words 必须覆盖句子中的每一个单词（前置词、连词、语气词也要，不遗漏）；stressed 必须是俄语原词只加重音；components 按俄语句子的真实成分划分。""" % sentence

        messages = [
            {"role": "system", "content": "你是严谨的俄语语法老师，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ]
        try:
            parsed = None
            for _attempt in range(3):
                try:
                    msgs = messages if _attempt == 0 else messages + [
                        {"role": "system", "content":
                         "你上次的输出不是合法 JSON。请重新生成："
                         "只输出一个合法的 JSON 对象，不要任何多余文字、"
                         "解释、markdown 或代码块。"}
                    ]
                    ai_response = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, msgs)
                    parsed = self._parse_ai_json(ai_response)
                    if parsed:
                        break
                except Exception:
                    parsed = None
            if not parsed:
                raise RuntimeError(" AI 返回内容无法解析为 JSON")
            words = parsed.get("words", []) if isinstance(parsed, dict) else []
            # 清洗 words，保证字段齐全
            clean_words = []
            for w in words:
                if not isinstance(w, dict):
                    continue
                wv = (str(w.get("word", "")).strip())
                if not wv:
                    continue
                clean_words.append({
                    "word": wv,
                    "stressed": str(w.get("stressed", "") or wv).strip(),
                    "pos": str(w.get("pos", "") or "").strip(),
                    "mean": str(w.get("mean", "") or "").strip(),
                })
            components = []
            for c in (parsed.get("components", []) if isinstance(parsed, dict) else []):
                if isinstance(c, dict) and str(c.get("text", "")).strip():
                    components.append({
                        "text": str(c.get("text", "")).strip(),
                        "role": str(c.get("role", "") or "").strip(),
                    })
            if not clean_words:
                clean_words = fallback_words
            return self._json(200, {"ok": True, "result": {
                "words": clean_words,
                "components": components,
                "translation": str(parsed.get("translation", "") or "").strip() if isinstance(parsed, dict) else "",
                "grammar": str(parsed.get("grammar", "") or "").strip() if isinstance(parsed, dict) else "",
            }})
        except Exception as e:
            # AI 失败：降级返回单词拆分，前端仍可使用
            return self._json(200, {"ok": True, "result": {
                "words": fallback_words, "components": [], "translation": "",
                "grammar": "语法解析生成失败：" + str(e)[:120],
            }})

    def _handle_pronunciation_score(self, data):
        """口语评测：录音转写 → 逐词严格对齐（错读/漏读/多读）→ AI 五档严格评分与建议。
        分数只可能是 80/85/90/95/100；漏读、错读全部逐词标出。"""
        standard = (data.get("standard") or "").strip()
        if not standard:
            return self._json(200, {"ok": False, "error": "缺少标准原文"})
        audio_bytes, err = self._decode_audio_data_url(data.get("audio"))
        if err:
            return self._json(200, {"ok": False, "error": err})

        user_text, _segs, err = self._transcribe_audio_bytes(audio_bytes)
        if err:
            return self._json(200, {"ok": False, "error": err})
        heard = _normalize_russian_text(user_text) if user_text else user_text

        # 客观逐词对齐 + 客观五档分（防 AI 糊弄的权威兜底）
        word_rows, ratio = _align_pronunciation(standard, heard)
        band = _pronunciation_band(ratio)

        stress_tip = rhythm_tip = summary = ""
        ai_score = None
        if AI_API_KEY and heard:
            align_brief = "；".join(
                ("%s[%s→%s]" % (r["target"], r["status"], r["heard"])) if r["status"] != "correct" else r["target"]
                for r in word_rows
            )
            prompt = """你是严格的俄语口语评测老师。请根据【标准原文】【学生实际朗读】和【逐词对齐】打分并给建议。
标准原文：%s
学生朗读（语音识别）：%s
逐词对齐（correct正确/misread读错/omitted漏读/extra多读）：%s
词正确率：%.0f%%

评分规则（必须严格，不能宽松、不能糊弄，学生没读到的词必须在 summary 中点名）：
- score 只能取 100、95、90、85、80 之一；
- 100：每个词都读对、完整无遗漏，重音语调自然；
- 95：仅 1 处轻微词尾/发音小问题；90：约 20%% 词有问题或 1 处漏读；
- 85：约 30%% 词有问题或多处漏读；80：问题超过 30%%、朗读不完整。
- 你的 score 不得高于按词正确率应得的档位（当前客观上限 %d 分）。
严格只输出 JSON（无 markdown）：
{"score": 整数, "stress": "重音方面的中文点评与纠正（指出哪个词重音位置，读对则肯定）", "rhythm": "停顿、语调、流利度方面的中文点评", "summary": "总体中文评语：逐一点名读错/漏读/多读的词并给正确读法，最后给一句练习建议"}""" % (
                standard, heard, align_brief, ratio * 100, band)
            try:
                resp = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, [
                    {"role": "system", "content": "你是严格的俄语口语评测老师，只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ])
                parsed = self._parse_ai_json(resp)
                if isinstance(parsed, dict):
                    try:
                        ai_score = int(round(float(parsed.get("score"))))
                    except (TypeError, ValueError):
                        ai_score = None
                    stress_tip = str(parsed.get("stress", "") or "").strip()
                    rhythm_tip = str(parsed.get("rhythm", "") or "").strip()
                    summary = str(parsed.get("summary", "") or "").strip()
            except Exception as e:
                print("[score] AI 评分失败，使用客观分：", repr(e))

        # 分数仲裁：必须是五档之一，且不得高于客观上限（严格，不允许 AI 放水）
        valid_bands = (80, 85, 90, 95, 100)
        score = band
        if ai_score in valid_bands:
            score = min(ai_score, band)
        if not heard:
            summary = "没有识别到俄语语音，请靠近麦克风、大声清晰地再读一次。"

        return self._json(200, {"ok": True, "result": {
            "user_text": heard or user_text or "",
            "raw_text": user_text or "",
            "score": score,
            "ratio": round(ratio, 3),
            "words": word_rows,
            "stress": stress_tip,
            "rhythm": rhythm_tip,
            "summary": summary,
        }})

    def _parse_ai_json(self, text):
        """多层容错解析 AI 返回的 JSON：去 markdown → 提取最外层 → 修复常见格式错误 → json.loads。"""
        text = (text or "").strip()
        # 1. 去除 markdown 代码块
        text = re.sub(r'^```(?:json|JSON)?\s*', '', text, flags=re.I)
        text = re.sub(r'\s*```$', '', text)
        # 2. 提取最外层花括号
        a = text.find("{")
        b = text.rfind("}")
        if a >= 0 and b > a:
            text = text[a:b + 1]
        # 3. 去除 JSON 中的单行注释（// ...）
        text = re.sub(r'//[^\n]*', '', text)
        # 4. 去除多行注释（/* ... */）
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        # 5. 去除 trailing commas（} 或 ] 前面的逗号）
        text = re.sub(r',\s*([}\]])', r'\1', text)
        # 6. 状态机修复：字符串内的裸换行/回车转义为 \n，避免破坏 JSON
        out = []
        in_str = False
        esc = False
        for ch in text:
            if in_str:
                if esc:
                    out.append(ch); esc = False
                elif ch == '\\':
                    out.append(ch); esc = True
                elif ch == '"':
                    in_str = False; out.append(ch)
                elif ch == '\n':
                    out.append('\\n')
                elif ch == '\r':
                    pass
                else:
                    out.append(ch)
            else:
                if ch == '"':
                    in_str = True
                out.append(ch)
        text = ''.join(out)
        # 7. 尝试标准解析
        try:
            return json.loads(text)
        except Exception:
            pass
        # 8. 尝试用 ast.literal_eval 解析（更宽松，支持单引号等）
        try:
            import ast
            return ast.literal_eval(text)
        except Exception:
            pass
        # 9. 最后手段：尝试修复常见的引号问题后再解析
        try:
            # 将单引号替换为双引号（简单处理，可能不准确）
            fixed = text.replace("'", '"')
            return json.loads(fixed)
        except Exception:
            pass
        # 全部失败，抛出原始错误
        return json.loads(text)

    def _handle_generate_quiz(self, data):
        """根据文章句子生成30道AI测验题。"""
        sentences = data.get("sentences") or []
        if not isinstance(sentences, list) or len(sentences) == 0:
            return self._json(200, {"ok": False, "error": "sentences 必须是非空数组"})
        if not AI_API_KEY:
            return self._json(200, {"ok": False, "error": "未配置AI API Key，无法生成测验"})

        title = (data.get("title") or "").strip()

        # 构造文章文本（逐句编号列出）
        lines = []
        for i, s in enumerate(sentences, 1):
            ru = (s.get("russian") or "").strip()
            cn = (s.get("chinese") or "").strip()
            lines.append("%d. %s — %s" % (i, ru, cn))
        article_text = "\n".join(lines)

        prompt = """你是俄语测验出题专家。请根据以下俄语文章内容，生成30道测验题。

文章标题：%s
文章内容：
%s

请严格按以下题型和数量生成：
1. 词汇选择题（5道）：从文章中选重点单词，4选1选择正确中文释义
2. 语法填空题（5道）：从文章中选句子，挖空关键语法点，4选1选择正确形式
3. 语法选择题（5道）：基于文章中出现的语法点，出语法规则选择题，4选1
4. 俄译中（5道）：从文章中选句子，给出参考中文翻译
5. 中译俄（5道）：基于文章内容，给中文句子，给出参考俄语翻译
6. 自主造句（3道）：给定文章重点单词，让用户造句
7. 阅读理解（2道）：关于文章内容的理解问题，给出参考答案

请严格以JSON格式返回（不要输出JSON以外的任何文字），格式如下：
{
  "quiz": [
    {"id": 1, "type": "vocab_mcq", "question": "...", "options": ["A","B","C","D"], "answer": 0, "explanation": "..."},
    ...
  ]
}

要求：
- id 从1到30连续编号
- 选择题的 answer 是正确选项的索引（0-3）
- 主观题（ru_to_cn, cn_to_ru, sentence_creation, reading_comprehension）的 options 字段省略，answer 存参考答案（造句题answer为空字符串）
- 题目必须基于文章内容，不能凭空编造
- 难度控制在A1-A2级别
- explanation 用简洁中文
""" % (title, article_text)

        messages = [
            {"role": "system", "content": "你是严格的俄语测验出题专家，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        # 最多重试2次（AI可能返回格式错误或题目数量不足）
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                ai_response = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
            except RuntimeError as e:
                if attempt < max_retries:
                    continue
                return self._json(200, {"ok": False, "error": "AI生成失败：" + str(e)})
            except Exception as e:
                if attempt < max_retries:
                    continue
                return self._json(200, {"ok": False, "error": "AI生成异常：" + str(e)})

            try:
                parsed = self._parse_ai_json(ai_response)
                quiz = parsed.get("quiz", [])
            except Exception as e:
                if attempt < max_retries:
                    # 重试时在消息中强调格式要求
                    messages.append({"role": "user", "content": "请严格只输出合法的JSON格式，不要输出任何其他文字、注释或markdown代码块。确保JSON语法正确，所有字符串用双引号，数组元素之间用逗号分隔。"})
                    continue
                return self._json(200, {"ok": False, "error": "AI返回解析失败：" + str(e)[:200]})

            if isinstance(quiz, list) and len(quiz) >= 15:
                break
            elif attempt < max_retries:
                messages.append({"role": "user", "content": "请生成完整的30道题目，确保quiz数组包含30个元素，每个元素格式正确。"})
            else:
                actual = len(quiz) if isinstance(quiz, list) else 0
                return self._json(200, {"ok": False, "error": "生成的题目数量不足15道（实际%d道），请重试" % actual})

        # 规范化每道题的字段
        normalized = []
        for q in quiz:
            if not isinstance(q, dict):
                continue
            item = {
                "id": q.get("id"),
                "type": q.get("type", ""),
                "question": q.get("question", ""),
                "explanation": q.get("explanation", ""),
                "answer": q.get("answer", ""),
            }
            if q.get("options") is not None:
                item["options"] = q["options"]
            normalized.append(item)

        return self._json(200, {"ok": True, "quiz": normalized, "total": len(normalized)})

    def _handle_grade_quiz(self, data):
        """根据用户答案和正确答案，AI评分主观题 + 自动判分选择题，返回总分和详情。"""
        quiz = data.get("quiz") or []
        user_answers = data.get("userAnswers") or {}
        sentences = data.get("sentences") or []

        if not isinstance(quiz, list) or len(quiz) == 0:
            return self._json(200, {"ok": False, "error": "quiz 必须是非空数组"})
        if not isinstance(user_answers, dict):
            return self._json(200, {"ok": False, "error": "userAnswers 必须是对象"})

        auto_types = {'vocab_mcq', 'grammar_fill', 'grammar_mcq'}
        subjective_types = {'ru_to_cn', 'cn_to_ru', 'sentence_creation', 'reading_comprehension'}

        details = []
        auto_score = 0.0
        subjective_questions = []
        type_stats = {}  # type -> {"correct": int, "total": int}

        # 第一步：自动判分选择题，收集主观题
        for q in quiz:
            qid = q.get("id")
            qtype = q.get("type", "")
            user_ans = user_answers.get(str(qid))

            if qtype not in type_stats:
                type_stats[qtype] = {"correct": 0, "total": 0}
            type_stats[qtype]["total"] += 1

            if qtype in auto_types:
                correct = q.get("answer")
                is_correct = (user_ans == correct)
                if is_correct:
                    auto_score += 1
                    type_stats[qtype]["correct"] += 1
                details.append({
                    "id": qid,
                    "type": qtype,
                    "userAnswer": user_ans,
                    "correctAnswer": correct,
                    "score": 1 if is_correct else 0,
                    "explanation": q.get("explanation", ""),
                })
            elif qtype in subjective_types:
                subjective_questions.append(q)
            else:
                # 未知题型：按0分处理，不阻塞整体评分
                details.append({
                    "id": qid,
                    "type": qtype,
                    "userAnswer": user_ans,
                    "correctAnswer": q.get("answer", ""),
                    "score": 0,
                    "explanation": q.get("explanation", ""),
                })

        # 第二步：主观题评分（AI 或降级默认分）
        ai_scores = {}  # id -> {"score": float, "explanation": str}
        suggestion = ""

        if not AI_API_KEY:
            # 未配置AI：选择题正常判分，主观题全部给0.5默认分
            for q in subjective_questions:
                qid = q.get("id")
                ai_scores[qid] = {"score": 0.5, "explanation": "未配置AI，主观题为默认评分"}
            suggestion = "未配置AI，主观题未评分（默认给0.5分）。配置AI_API_KEY后可获得精准评分。"
        else:
            # 构造文章文本
            art_lines = []
            for i, s in enumerate(sentences, 1):
                ru = (s.get("russian") or "").strip()
                cn = (s.get("chinese") or "").strip()
                art_lines.append("%d. %s — %s" % (i, ru, cn))
            article_text = "\n".join(art_lines) if art_lines else "(未提供文章句子)"

            # 构造主观题列表
            subj_lines = []
            for q in subjective_questions:
                qid = q.get("id")
                qtype = q.get("type", "")
                question = q.get("question", "")
                user_ans = user_answers.get(str(qid), "(未作答)")
                ref_ans = q.get("answer", "(开放题)")
                subj_lines.append(
                    "题号%s（%s）：\n题目：%s\n用户答案：%s\n参考答案：%s\n"
                    % (qid, qtype, question, user_ans, ref_ans)
                )
            subj_text = "\n".join(subj_lines) if subj_lines else "(无主观题)"

            grade_prompt = """你是俄语测验评分专家。请根据以下用户答案和参考答案，对主观题进行评分。

文章内容：%s

需要评分的主观题：
%s

请严格以JSON格式返回（不要输出JSON以外的任何文字）：
{
  "scores": [
    {"id": 16, "score": 0.8, "explanation": "翻译基本正确，但用词不够精准"},
    ...
  ],
  "suggestion": "整体翻译能力不错，建议加强..."
}

评分标准：
- 1.0分：完全正确，表达自然
- 0.8分：基本正确，有小瑕疵（用词不够精准、语法小错）
- 0.5分：部分正确，有明显错误但能理解意思
- 0.2分：大部分错误，仅能看出个别词汇
- 0分：完全错误或未作答
""" % (article_text, subj_text)

            messages = [
                {"role": "system", "content": "你是严格的俄语测验评分专家，只输出JSON。"},
                {"role": "user", "content": grade_prompt},
            ]

            try:
                ai_response = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
                parsed = self._parse_ai_json(ai_response)
                raw_scores = parsed.get("scores", [])
                suggestion = parsed.get("suggestion", "")
                for s in raw_scores:
                    if isinstance(s, dict) and s.get("id") is not None:
                        try:
                            sc = float(s.get("score", 0))
                            sc = max(0.0, min(1.0, sc))
                        except (TypeError, ValueError):
                            sc = 0.0
                        ai_scores[s["id"]] = {
                            "score": sc,
                            "explanation": s.get("explanation", ""),
                        }
            except Exception as e:
                # AI评分失败：主观题给0.5默认分，不阻塞整体返回
                for q in subjective_questions:
                    qid = q.get("id")
                    ai_scores[qid] = {
                        "score": 0.5,
                        "explanation": "AI评分失败（%s），默认给0.5分" % str(e)[:80],
                    }
                suggestion = "AI评分失败，主观题为默认评分。错误：" + str(e)[:100]

        # 第三步：合并主观题得分到 details，计算总分
        subjective_score = 0.0
        for q in subjective_questions:
            qid = q.get("id")
            qtype = q.get("type", "")
            user_ans = user_answers.get(str(qid))
            sc_info = ai_scores.get(qid, {"score": 0.0, "explanation": ""})
            sc = sc_info["score"]
            subjective_score += sc
            if sc >= 0.5:
                type_stats[qtype]["correct"] += 1
            details.append({
                "id": qid,
                "type": qtype,
                "userAnswer": user_ans,
                "correctAnswer": q.get("answer", ""),
                "score": sc,
                "explanation": sc_info.get("explanation") or q.get("explanation", ""),
            })

        # 按题号排序 details
        details.sort(key=lambda d: (d.get("id") is None, d.get("id", 0)))

        # 第四步：计算总分和通过状态
        total_questions = len(quiz)
        total_score = auto_score + subjective_score
        score_percent = round(total_score / total_questions * 100) if total_questions > 0 else 0

        # 通过标准：>=80 优秀通过，60-79 勉强通过，<60 不通过
        if score_percent >= 80:
            pass_flag = True
            if not suggestion:
                suggestion = "成绩优秀！继续保持，可以挑战更高难度的内容。"
        elif score_percent >= 60:
            pass_flag = True
            if not suggestion:
                suggestion = "勉强通过，建议复习错题对应的语法点和词汇，巩固基础后再试一次。"
        else:
            pass_flag = False
            if not suggestion:
                suggestion = "未通过，建议重新学习文章内容，重点掌握基础词汇和语法变化后再测验。"

        # 构造各题型得分统计
        breakdown = {}
        for t, st in type_stats.items():
            breakdown[t] = {"correct": st["correct"], "total": st["total"]}

        result = {
            "score": score_percent,
            "pass": pass_flag,
            "breakdown": breakdown,
            "details": details,
            "suggestion": suggestion,
        }

        return self._json(200, {"ok": True, "result": result})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        data = self._read_json()
        try:
            if path == "/api/transcribe":
                return self._handle_transcribe(data)
            if path == "/api/square/submit":
                return self._handle_square_submit(data)
            if path == "/api/square/delete":
                return self._handle_square_delete(data)
            if path == "/api/tts":
                text = (data.get("text") or "").strip()
                voice = data.get("voice")
                item_id = data.get("id")
                item_type = data.get("type")  # "word" or "statement"
                if not text:
                    return self._json(400, {"ok": False, "error": "text不能为空"})
                # 调用 Yandex（或回退）生成音频，存缓存
                audio_bytes = self._tts_yandex(text, voice)
                if not audio_bytes:
                    audio_bytes = self._tts_edge(text, voice)
                if not audio_bytes:
                    return self._json(500, {"ok": False, "error": "TTS合成失败"})
                # 存到 audio_cache 并返回 URL
                import hashlib
                cache_dir = os.path.join(BASE_DIR, "audio_cache")
                os.makedirs(cache_dir, exist_ok=True)
                cache_key = hashlib.md5(f"{text}_{voice or 'default'}".encode("utf-8")).hexdigest()
                cache_file = os.path.join(cache_dir, f"{cache_key}.mp3")
                if not os.path.isfile(cache_file):
                    with open(cache_file, "wb") as f:
                        f.write(audio_bytes)
                audio_url = f"/audio_cache/{cache_key}.mp3"
                # 更新数据库
                if item_id and item_type in ("word", "statement"):
                    try:
                        conn = _quest_conn()
                        try:
                            with conn.cursor() as cur:
                                table = "quest_words" if item_type == "word" else "quest_statements"
                                cur.execute(f"UPDATE {table} SET audio_url=%s WHERE id=%s", (audio_url, item_id))
                            conn.commit()
                        finally:
                            conn.close()
                    except Exception as e:
                        print(f"[tts] 更新数据库失败: {e}")
                return self._json(200, {"ok": True, "audio_url": audio_url})
            if path == "/api/answer/submit":
                return self._handle_answer_submit(data)
            if path == "/api/course/complete":
                return self._handle_course_complete(data)
            if path == "/api/admin/check":
                return self._handle_admin_check(data)
            if path == "/api/subs":
                url = (data.get("url") or "").strip()
                if not url:
                    return self._json(400, {"ok": False, "error": "缺少 url"})
                text, err = fetch_subs(url)
                if text is None:
                    return self._json(200, {"ok": False, "error": err})
                return self._json(200, {"ok": True, "text": text})
            if path == "/api/segment":
                # 俄语无标点断句：调 razdel 切句。
                text = (data.get("text") or "")
                segs, ok = ru_segment(text)
                if not ok:
                    return self._json(200, {
                        "ok": False,
                        "error": "razdel 未安装。请运行：python -m pip install razdel",
                    })
                return self._json(200, {"ok": True, "sentences": segs})
            if path == "/api/dict":
                word = (data.get("word") or "").strip()
                if not word:
                    return self._json(400, {"ok": False, "error": "缺少 word"})
                t = dict_lookup(word)
                return self._json(200, {"ok": True, "translation": t})
            if path == "/api/grammar":
                sentence = (data.get("sentence") or data.get("text") or "").strip()
                if not sentence:
                    return self._json(400, {"ok": False, "error": "缺少句子"})
                if not AI_API_KEY:
                    return self._json(200, {"ok": False, "error": "未配置 AI API Key（请在环境变量 AI_API_KEY 中设置）"})
                messages = [
                    {"role": "system", "content": """你是资深俄语老师。请对用户输入的俄语句子做完整解析，用简洁中文，Markdown格式，按以下结构输出：

## 📖 整句翻译
给出整句的中文翻译。

## 🔤 逐词解析
用表格，逐词列出：原形、词性、在句中的语法功能、中文释义。

## 🔍 语法拆分
列出这个句子用到的**所有语法点**（如：名词第二格、动词过去时、形容词短尾、前置词+格、句型结构等），每个语法点单独说明。

### 每个语法点包含：
- **语法点名称**：如"名词第二格"
- **句中体现**：指出句中哪个词/结构体现了这个语法
- **为什么这么用**：解释这个语法在这里的作用和原因
- **什么时候用**：说明这个语法的使用场景、条件和规则
- **类似例句**：给1-2个使用相同语法的俄语例句，配中文翻译

## 💡 学习提示
给出1-2条针对这个句子的学习建议或记忆技巧。

如果句子很简单没有复杂语法，也要如实说明，并给出基础语法点的解释。"""},
                    {"role": "user", "content": sentence},
                ]
                try:
                    content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
                    return self._json(200, {"ok": True, "content": content})
                except RuntimeError as e:
                    return self._json(200, {"ok": False, "error": str(e)})
                except Exception as e:
                    return self._json(200, {"ok": False, "error": "语法解析异常：" + str(e)})
            if path == "/api/ai":
                base = (data.get("baseUrl") or AI_BASE_URL).strip()
                key = (data.get("key") or AI_API_KEY).strip()
                model = (data.get("model") or AI_MODEL).strip()
                messages = data.get("messages") or []
                if not messages:
                    return self._json(200, {"ok": False, "error": "缺少 messages 参数"})
                # 兼容修复：智谱/DeepSeek 等接口要求 messages 至少包含一条 user 消息，
                # 只有 system 消息（如 AI 引导语）会返回 1214 messages 参数非法。
                if all((m.get("role") == "system" for m in messages)):
                    messages = list(messages) + [{"role": "user", "content": "请开始。"}]
                if not key:
                    return self._json(200, {"ok": False, "error": "未配置 AI API Key（请在环境变量 AI_API_KEY 中设置）"})
                try:
                    content = ai_chat(base, key, model, messages)
                    return self._json(200, {"ok": True, "content": content})
                except RuntimeError as e:
                    return self._json(200, {"ok": False, "error": str(e)})
                except Exception as e:
                    return self._json(200, {"ok": False, "error": "AI请求异常：" + str(e)})
            if path == "/api/tutor":
                return self._handle_tutor(data)
            if path == "/api/recite-compare":
                return self._handle_recite_compare(data)
            if path == "/api/transcribe-audio":
                return self._handle_transcribe_audio(data)
            if path == "/api/sentence-analysis":
                return self._handle_sentence_analysis(data)
            if path == "/api/pronunciation-score":
                return self._handle_pronunciation_score(data)
            if path == "/api/upload/presign":
                return self._handle_upload_presign(data)
            if path == "/api/upload":
                return self._handle_upload(data)
            if path == "/api/generate-quiz":
                return self._handle_generate_quiz(data)
            if path == "/api/grade-quiz":
                return self._handle_grade_quiz(data)
            return self._json(404, {"ok": False, "error": "未知接口"})
        except Exception as e:
            return self._json(500, {"ok": False, "error": str(e)})

    def log_message(self, *args):  # 安静模式
        pass


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = PORT
    srv = None
    while port < PORT + 50:
        try:
            srv = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            port += 1
    url = "http://localhost:%d" % port
    print("=" * 48)
    print("  看视频学俄语")
    print("  服务地址：" + url)
    print("  （按 Ctrl+C 退出）")
    print("=" * 48)
    print("AI 配置状态：")
    print("  AI_BASE_URL:", AI_BASE_URL)
    print("  AI_MODEL:", AI_MODEL)
    print("  AI_API_KEY:", "已配置 (" + AI_API_KEY[:4] + "***)" if AI_API_KEY else "未配置")
    print("=" * 48)
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    _square_init()
    _quest_init()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
