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
import hashlib
import re
import secrets
import shutil
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 确保项目根目录在 sys.path 里
import tempfile
import threading
import time
import uuid
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

# P0 登录与 RBAC：密码哈希 / JWT 签发校验（纯函数库，见 auth_lib.py）
from auth_lib import (
    hash_password, verify_password, create_token, decode_token,
    extract_bearer, validate_username, pyjwt_available,
    ROLES, BACKEND_ROLES, ADMIN_WRITE_ROLES,
)

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

# ---- P4-B 句乐部 plan Prompt 版本：Prompt 升级后旧缓存自动失效重建（避免旧错误结果一直命中） ----
PLAN_PROMPT_V = "v3.2"

# ---- P5（路线B）：句乐部式 6 列表格 Prompt 版本（同 PLAN 机制：升级即失效重建） ----
SLOT_TABLE_PROMPT_V = "v13"  # v13: prefill 保留 hidden 字段（难度裁剪真正生效）——旧 v12 缓存失效强制重新生成

# ---- 新课程引擎开关：True=走新引擎（GLM-4-plan + pymorphy3），False=全部走旧引擎 ----
USE_NEW_ENGINE = False  # 阶段B任务1验证完成后再切 True

# ---- P0 登录与 RBAC ----
# JWT 签名密钥（务必单独设置一个随机长串，不要与 ADMIN_KEY 相同）
SECRET_KEY = os.environ.get("SECRET_KEY", "")
# 令牌有效期（秒），默认 7 天
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "604800"))

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

# —— 本地 БКРС 词典链（translation_dict.py：A1修正→FreeDict→大БКРС→Natasha词形还原）——
# natasha 缺失时原形查询仍可用；整体 import 失败则 _LOCAL_DICT_OK=False，不影响启动
_LOCAL_DICT_OK = False
_bkrs_translate_chunk = None
try:
    from translation_dict import translate_chunk as _bkrs_translate_chunk
    _LOCAL_DICT_OK = True
except Exception as _e:
    print("[dict] БКРС本地词典不可用: %s" % _e)


def dict_lookup(word):
    """俄→中翻译（三层）：
    1. 本地 БКРС 词典链（A1修正 → 大БКРС 25万词条 → Natasha词形还原，translation_dict.py）
    2. MyMemory 免费在线接口
    3. AI 兜底翻译（已配置大模型时）
    本地词典命中即返回；未命中（返回【词】占位）才走在线。"""
    # —— 第一层：本地 БКРС 词典链 ——
    if _LOCAL_DICT_OK:
        try:
            r = _bkrs_translate_chunk(word)
            if r and r.strip() and not r.strip().startswith("【"):
                return r.strip()
        except Exception:
            pass
    # —— 第二层：MyMemory 免费翻译接口（俄→中），无需 key ——
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


def _parse_json_block(content):
    """从 LLM 返回文本中提取 JSON 对象/数组。先剥 ```json 代码块包裹，兜底截取首个平衡括号块。"""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
    return None


def call_llm(system_prompt, user_prompt="", json_mode=True):
    """高层 LLM 封装（新接口专用，不改动 /api/ai 原有透传逻辑）：
    组装 messages → ai_chat → 按需解析 JSON。
    json_mode=True 返回 dict/list | None；False 返回 str | None。
    未配置 AI_API_KEY 或调用失败均返回 None，不抛异常。"""
    if not AI_API_KEY:
        return None
    messages = [{"role": "system", "content": system_prompt}]
    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})
    else:
        # 兼容修复：智谱/DeepSeek 等接口要求 messages 至少包含一条 user 消息，
        # 只有 system 消息（如 AI 引导语）会返回 1214 messages 参数非法（与 /api/ai 同款修复）
        messages.append({"role": "user", "content": "请开始。"})
    try:
        content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
    except Exception as e:
        print("[call_llm] 调用失败：", e)
        return None
    if not content:
        return None
    if json_mode:
        return _parse_json_block(content)
    return content


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
        "connect_timeout": 60,
        "read_timeout": 60,
        "write_timeout": 60,
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


def _seg_execute(fn):
    """执行 DB 操作；TiDB Serverless 偶发 Lost connection 时换新连接重试一次（只用于新语块接口）。"""
    try:
        return fn()
    except Exception as e:
        if _PYMYSQL_OK and isinstance(e, pymysql.err.OperationalError) and "Lost connection" in str(e):
            print("[segments] 检测到数据库断连，换新连接重试一次")
            time.sleep(0.5)
            return fn()
        raise


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
                # P1-B：学习断点/完成标记上云（每用户×每课时×每模式 一条）
                cur.execute("CREATE TABLE IF NOT EXISTS quest_learning_progress (id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64) NOT NULL, course_id VARCHAR(64) NOT NULL, unit_id VARCHAR(64) NOT NULL, mode VARCHAR(16) NOT NULL, seq_index INTEGER NOT NULL DEFAULT 0, unit_index INTEGER NOT NULL DEFAULT 0, difficulty VARCHAR(16) DEFAULT '', status TINYINT NOT NULL DEFAULT 0, ts BIGINT NOT NULL DEFAULT 0, UNIQUE KEY uk_learning_progress_user_unit_mode (user_id, unit_id, mode))")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_learning_progress_user ON quest_learning_progress(user_id)")
                # P0（语块化）：全局 LLM 缓存表（键=句子hash+难度，同句跨课时共享，命中不重复调 AI）+ 课时语块引用表
                cur.execute("CREATE TABLE IF NOT EXISTS sentence_segment_cache (id VARCHAR(64) PRIMARY KEY, sentence_hash VARCHAR(64) NOT NULL, sentence TEXT NOT NULL, difficulty VARCHAR(16) NOT NULL, segments JSON NOT NULL, review_status VARCHAR(16) NOT NULL DEFAULT 'ok', translation VARCHAR(512) DEFAULT '', created_at BIGINT DEFAULT 0, UNIQUE KEY uk_cache_sent_diff (sentence_hash, difficulty))")
                cur.execute("CREATE TABLE IF NOT EXISTS sentence_segments (id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL, unit_id VARCHAR(64) NOT NULL, cache_id VARCHAR(64) NULL, sentence_hash VARCHAR(64) NOT NULL, difficulty VARCHAR(16) NOT NULL, sort_order INT NOT NULL, text VARCHAR(512) NOT NULL, type VARCHAR(32) NOT NULL DEFAULT 'chunk', chinese VARCHAR(255) DEFAULT '', review_status VARCHAR(16) NOT NULL DEFAULT 'ok', created_at BIGINT DEFAULT 0, UNIQUE KEY uk_seg (course_id, unit_id, sentence_hash, difficulty, sort_order), KEY idx_seg_unit (course_id, unit_id))")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_seg_cache_id ON sentence_segments(cache_id)")
                # P4（句乐部式滚雪球）：槽位/增量规划缓存表（AI 只出增量词序列，电脑拼 target，零拼写错误）
                cur.execute("CREATE TABLE IF NOT EXISTS sentence_slot_plans (id VARCHAR(64) PRIMARY KEY, sentence_hash VARCHAR(64) NOT NULL, difficulty VARCHAR(16) NOT NULL, sentence TEXT NOT NULL, plan JSON NOT NULL, review_status VARCHAR(16) NOT NULL DEFAULT 'ok', created_at BIGINT DEFAULT 0, UNIQUE KEY uk_slot_plan (sentence_hash, difficulty))")
                # P5（路线B）：句乐部式 6 列表格缓存表（键=句子hash+难度+意图指纹；意图变→重建）
                cur.execute("CREATE TABLE IF NOT EXISTS sentence_slot_tables (id VARCHAR(64) PRIMARY KEY, sentence_hash VARCHAR(64) NOT NULL, difficulty VARCHAR(16) NOT NULL, sentence TEXT NOT NULL, intents_fp VARCHAR(16) NOT NULL, `rows` JSON NOT NULL, review_status VARCHAR(16) NOT NULL DEFAULT 'ok', prompt_v VARCHAR(8) DEFAULT 'v1', created_at BIGINT DEFAULT 0, UNIQUE KEY uk_slot_table (sentence_hash, difficulty, intents_fp))")
                # P2：课时维度持久化 6 列表格（学生端数据源；缓存表是全局幂等，这里是课时落地副本）
                cur.execute("CREATE TABLE IF NOT EXISTS sentence_slot_unit_tables (id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL, unit_id VARCHAR(64) NOT NULL, sentence_hash VARCHAR(64) NOT NULL, sentence TEXT NOT NULL, difficulty VARCHAR(16) NOT NULL, intents_fp VARCHAR(16) NOT NULL, `rows` JSON NOT NULL, review_status VARCHAR(16) NOT NULL DEFAULT 'ok', prompt_v VARCHAR(8) DEFAULT 'v6', created_at BIGINT DEFAULT 0, UNIQUE KEY uk_slot_unit (course_id, unit_id, sentence_hash, difficulty, intents_fp), KEY idx_slot_unit (course_id, unit_id))")
                # 阶段A：整课steps表（新引擎分层编排输出）
                cur.execute("CREATE TABLE IF NOT EXISTS course_steps (id INTEGER PRIMARY KEY AUTO_INCREMENT, course_id VARCHAR(64) NOT NULL, unit_id VARCHAR(64) NOT NULL, seq INTEGER NOT NULL, gid VARCHAR(16) NOT NULL, step_type VARCHAR(16) NOT NULL, ru TEXT NOT NULL, zh TEXT NOT NULL, tag VARCHAR(64), created_at BIGINT DEFAULT 0, KEY idx_course_steps_course_id (course_id, unit_id))")
                # 阶段B：异步生成任务表
                cur.execute("CREATE TABLE IF NOT EXISTS generation_tasks (task_id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL, unit_id VARCHAR(64) NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'pending', progress JSON, result JSON, error TEXT, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, KEY idx_gen_tasks_status (status), KEY idx_gen_tasks_created (created_at))")
                # 阶段B：分类缓存表
                cur.execute("CREATE TABLE IF NOT EXISTS sentence_classification_cache (ru_hash VARCHAR(64) PRIMARY KEY, ru TEXT NOT NULL, classification JSON NOT NULL, created_at BIGINT DEFAULT 0)")
                # P4 幂等迁移：plan 缓存加词池指纹列（变体组依赖词池；换词池后缓存失效重建）
                cur.execute("SHOW COLUMNS FROM sentence_slot_plans LIKE 'pool_fp'")
                if not cur.fetchone():
                    cur.execute("ALTER TABLE sentence_slot_plans ADD COLUMN pool_fp VARCHAR(16) DEFAULT ''")
                # P4-B 幂等迁移：plan 缓存加 Prompt 版本列（Prompt 升级后旧缓存失效重建，避免旧错误结果一直命中）
                cur.execute("SHOW COLUMNS FROM sentence_slot_plans LIKE 'prompt_v'")
                if not cur.fetchone():
                    cur.execute("ALTER TABLE sentence_slot_plans ADD COLUMN prompt_v VARCHAR(8) DEFAULT 'v2'")
                # P1 幂等迁移：cache 加 translation 列；sentence_segments.cache_id 允许 NULL（占位行用）
                cur.execute("SHOW COLUMNS FROM sentence_segment_cache LIKE 'translation'")
                if not cur.fetchone():
                    cur.execute("ALTER TABLE sentence_segment_cache ADD COLUMN translation VARCHAR(512) DEFAULT ''")
                cur.execute("SHOW COLUMNS FROM sentence_segments LIKE 'cache_id'")
                _row = cur.fetchone()
                if _row and (_row[2] or "").upper() == "NO":
                    cur.execute("ALTER TABLE sentence_segments MODIFY cache_id VARCHAR(64) NULL")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_statement_id ON quest_words(statement_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_lemma ON quest_words(lemma)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_pos ON quest_words(pos)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_aa_statement_id ON quest_acceptable_answers(statement_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_learning_records_course_id ON quest_learning_records(course_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_learning_records_created_at ON quest_learning_records(created_at)")
                # P1-D：订单表（真实支付骨架：微信支付对接位预留，后台手动确认兜底）
                cur.execute("CREATE TABLE IF NOT EXISTS orders (id VARCHAR(64) PRIMARY KEY, order_no VARCHAR(64) NOT NULL UNIQUE, user_id VARCHAR(64) NOT NULL, plan_key VARCHAR(16) NOT NULL, amount_cents INTEGER NOT NULL, currency VARCHAR(8) NOT NULL DEFAULT 'CNY', status VARCHAR(16) NOT NULL DEFAULT 'created', pay_channel VARCHAR(16) NOT NULL DEFAULT 'wechat', trade_no VARCHAR(64), paid_at BIGINT, created_at BIGINT NOT NULL)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
                # P1-C：课程分类表（主分类 + 子分类；sort_order 排序、is_active 启停；商城标签栏与后台表单数据源）
                cur.execute("CREATE TABLE IF NOT EXISTS categories (id VARCHAR(64) PRIMARY KEY, name VARCHAR(64) NOT NULL, sub_name VARCHAR(64) NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0, is_active TINYINT NOT NULL DEFAULT 1, created_at BIGINT NOT NULL DEFAULT 0, UNIQUE KEY uk_categories_name_sub (name, sub_name))")
                for _sd in _CATEGORY_SEEDS:
                    _sd_id = "cat_" + hashlib.md5((_sd["name"] + "|" + _sd["sub_name"]).encode("utf-8")).hexdigest()[:16]
                    cur.execute("INSERT IGNORE INTO categories (id, name, sub_name, sort_order, is_active, created_at) VALUES (%s, %s, %s, %s, 1, %s)",
                                (_sd_id, _sd["name"], _sd["sub_name"], _sd["sort_order"], int(time.time() * 1000)))
                # 迁移：课程包加子分类字段（可空；主分类沿用既有 category 字段）
                try:
                    cur.execute("ALTER TABLE quest_course_packs ADD COLUMN sub_category VARCHAR(64)")
                    print("[quest] 迁移：已添加 quest_course_packs.sub_category 字段")
                except Exception:
                    pass
                # P1-F：系统设置（key-value；VIP 套餐价格/站点信息后台可配，缺省用常量）
                cur.execute("CREATE TABLE IF NOT EXISTS settings (k VARCHAR(64) PRIMARY KEY, v TEXT, updated_at BIGINT NOT NULL)")
                _seed_settings(cur)
                # 迁移：users 加 VIP 到期时间（毫秒时间戳；终身=2100-01-01；NULL/0=无 VIP）
                try:
                    cur.execute("ALTER TABLE users ADD COLUMN vip_expire_at BIGINT DEFAULT 0")
                    print("[auth] 迁移：已添加 users.vip_expire_at 字段")
                except Exception:
                    pass
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
# P0 登录与 RBAC —— users / admin_operation_logs
# ==========================================================

def _auth_init():
    """增量建表（幂等）：users 用户表 + admin_operation_logs 操作日志表。不改动任何旧表。"""
    if not (_PYMYSQL_OK and DATABASE_URL):
        return
    try:
        conn = _quest_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(64) PRIMARY KEY,
                        username VARCHAR(64) NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        role VARCHAR(16) NOT NULL DEFAULT 'learner',
                        nickname VARCHAR(128),
                        avatar VARCHAR(512),
                        email VARCHAR(128),
                        status TINYINT NOT NULL DEFAULT 1,
                        created_at BIGINT DEFAULT 0,
                        updated_at BIGINT DEFAULT 0,
                        UNIQUE KEY uk_users_username (username)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS admin_operation_logs (
                        id VARCHAR(64) PRIMARY KEY,
                        user_id VARCHAR(64),
                        username VARCHAR(64),
                        action VARCHAR(64) NOT NULL,
                        target_type VARCHAR(64),
                        target_id VARCHAR(64),
                        detail TEXT,
                        ip VARCHAR(64),
                        created_at BIGINT DEFAULT 0
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_aol_created_at ON admin_operation_logs(created_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_aol_user_id ON admin_operation_logs(user_id)")
            conn.commit()
            print("[auth] 用户与操作日志表初始化完成")
        finally:
            conn.close()
    except Exception as e:
        print("[auth] 初始化数据库失败：", e)


# ========== P1-D 会员 / 订单（真实支付骨架） ==========
# 套餐定价（金额单位=分；管理员后续可在后台配置，当前为常量）
VIP_PLANS = {
    "month":   {"name": "月付",   "amount_cents": 2900,  "months": 1,  "tag": "月付 29 元"},
    "quarter": {"name": "季付",   "amount_cents": 8500,  "months": 3,  "tag": "季付 85 元"},
    "year":    {"name": "年付",   "amount_cents": 34500, "months": 12, "tag": "年付 345 元"},
    "lifetime": {"name": "终身",  "amount_cents": 108800, "months": None, "tag": "终身 1088 元"},
}
LIFETIME_EXPIRE = 4102444800000  # 2100-01-01（终身）

# ========== P1-C 课程分类 ==========
# 种子分类：与前端商城/后台表单既有体系对齐（主分类 + 子分类；sort_order 由序号决定）。
# 首次建表写入；后续后台可增删改。INSERT IGNORE 保证幂等。
_CATEGORY_SEEDS = [
    ("教材同步", "全部"), ("教材同步", "走遍俄罗斯"), ("教材同步", "新概念俄语"), ("教材同步", "大学俄语"),
    ("教材同步", "东方俄语"), ("教材同步", "黑大俄语"), ("教材同步", "北外俄语"), ("教材同步", "人教版初中"),
    ("教材同步", "人教版高中"), ("教材同步", "自编课"),
    ("考试备考", "全部"), ("考试备考", "中高考"), ("考试备考", "专四专八"), ("考试备考", "考研"),
    ("考试备考", "ТРКИ等级"), ("考试备考", "留学预科"), ("考试备考", "CATTI"), ("考试备考", "职业俄语"),
    ("少儿俄语", "全部"), ("少儿俄语", "少儿启蒙"), ("少儿俄语", "动画分级"), ("少儿俄语", "分级阅读"),
    ("少儿俄语", "动画绘本"), ("少儿俄语", "儿歌童谣"), ("少儿俄语", "字母拼读"), ("少儿俄语", "少儿词汇"),
    ("基础俄语", "全部"), ("基础俄语", "零基础路线"), ("基础俄语", "字母发音"), ("基础俄语", "基础语法"),
    ("基础俄语", "基础词汇"), ("基础俄语", "核心句型"), ("基础俄语", "经典教材"), ("基础俄语", "综合提升"),
    ("语法专项", "全部"), ("语法专项", "主格"), ("语法专项", "属格"), ("语法专项", "与格"),
    ("语法专项", "宾格"), ("语法专项", "工具格"), ("语法专项", "前置格"),
    ("场景俄语", "全部"), ("场景俄语", "日常对话"), ("场景俄语", "商务职场"), ("场景俄语", "外贸商务"),
    ("场景俄语", "旅游出行"), ("场景俄语", "面试校园"), ("场景俄语", "社交口语"), ("场景俄语", "写作邮件"),
    ("阅读听力", "全部"), ("阅读听力", "短文精读"), ("阅读听力", "俄语故事"), ("阅读听力", "名著简写"),
    ("阅读听力", "新闻短文"), ("阅读听力", "文化科普"), ("阅读听力", "专业阅读"),
    ("影视俄语", "全部"), ("影视俄语", "情景剧"), ("影视俄语", "影视台词"), ("影视俄语", "电影片段"),
    ("影视俄语", "动画片段"), ("影视俄语", "经典教材剧"),
    ("音乐俄语", "全部"), ("音乐俄语", "俄语歌曲"),
]
_CATEGORY_SEEDS = [{"name": n, "sub_name": s, "sort_order": i} for i, (n, s) in enumerate(_CATEGORY_SEEDS)]

def _category_rows(active_only=True):
    """读取分类行；active_only=True 只返回启用项（按 sort_order 排序）。"""
    conn = _quest_conn()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
            if active_only:
                cur.execute("SELECT id, name, sub_name, sort_order, is_active FROM categories WHERE is_active=1 ORDER BY sort_order ASC, created_at ASC")
            else:
                cur.execute("SELECT id, name, sub_name, sort_order, is_active FROM categories ORDER BY sort_order ASC, created_at ASC")
            return cur.fetchall() or []
    finally:
        conn.close()

def _categories_tree():
    """公开分类树：主分类 -> 子分类列表（'全部' 恒为首项）。"""
    rows = _category_rows(active_only=True)
    tree, order = [], []
    for r in rows:
        if r["name"] not in order:
            order.append(r["name"]); tree.append({"name": r["name"], "subs": []})
        tree[order.index(r["name"])]["subs"].append(r["sub_name"] or "全部")
    return tree


# ========== P1-F 系统设置 ==========
_DEFAULT_SITE = {"site_name": "看视频学俄语", "site_subtitle": "Russian Learning", "announcement": ""}

def _seed_settings(cur):
    """初始化缺省设置（INSERT IGNORE：已有配置不覆盖）。vip_plans 与 VIP_PLANS 常量保持一致。"""
    _seed_rows = {
        "site": json.dumps(_DEFAULT_SITE, ensure_ascii=False),
        "vip_plans": json.dumps(VIP_PLANS, ensure_ascii=False),
    }
    for k, v in _seed_rows.items():
        cur.execute("INSERT IGNORE INTO settings (k, v, updated_at) VALUES (%s, %s, %s)", (k, v, int(time.time() * 1000)))

def _get_settings(key, default=None):
    """读单个设置；缺失/解析失败返回 default。"""
    conn = _quest_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT v FROM settings WHERE k=%s", (key,))
            r = cur.fetchone()
            if not r:
                return default
            return r[0]
    except Exception:
        return default
    finally:
        conn.close()

def _save_settings(key, value, is_json=True):
    """写单个设置（JSON 序列化或原样存）。"""
    text = json.dumps(value, ensure_ascii=False) if is_json else str(value)
    conn = _quest_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO settings (k, v, updated_at) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE v=%s, updated_at=%s",
                        (key, text, int(time.time() * 1000), text, int(time.time() * 1000)))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

def _vip_plans():
    """动态套餐配置：settings.vip_plans 优先；未配置/非法则回退 VIP_PLANS 常量。"""
    raw = _get_settings("vip_plans", None)
    if raw:
        try:
            cfg = json.loads(raw)
            if isinstance(cfg, dict) and cfg:
                # 白名单校验：仅接受已知套餐 key 且结构完整
                plans = {}
                for k in ("month", "quarter", "year", "lifetime"):
                    if k in cfg and isinstance(cfg[k], dict) and "amount_cents" in cfg[k]:
                        p = dict(cfg[k])
                        p.setdefault("name", VIP_PLANS[k]["name"])
                        p.setdefault("months", VIP_PLANS[k]["months"])
                        p.setdefault("tag", VIP_PLANS[k]["tag"])
                        try:
                            p["amount_cents"] = int(p["amount_cents"])
                        except (TypeError, ValueError):
                            continue
                        if p["amount_cents"] < 0:
                            continue
                        plans[k] = p
                if plans:
                    return plans
        except Exception:
            pass
    return VIP_PLANS

def _site_info():
    """站点公开信息（站点名/副标题/公告）；缺省回退常量。"""
    raw = _get_settings("site", None)
    if raw:
        try:
            s = json.loads(raw)
            if isinstance(s, dict):
                out = dict(_DEFAULT_SITE)
                for k in out:
                    if k in s and s[k] is not None:
                        out[k] = str(s[k])[:200]
                return out
        except Exception:
            pass
    return dict(_DEFAULT_SITE)


def _wx_pay_ready():
    """微信支付 v3 四项配置是否齐全（未齐全时前端走人工/兑换码兜底，接口位保留）"""
    return bool(os.environ.get("WECHAT_MCHID") and os.environ.get("WECHAT_APPID")
                and os.environ.get("WECHAT_PRIVATE_KEY") and os.environ.get("WECHAT_API_V3_KEY"))


def _grant_vip(uid, plan_key):
    """按套餐为用户发放 VIP 时长。返回 (ok, 新到期ms, 错误)。终身=2100-01-01。"""
    plan = _vip_plans().get(plan_key)
    if not plan:
        return False, 0, "未知套餐"
    now = int(time.time() * 1000)
    def _upd():
        conn = _quest_conn()
        try:
            with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                cur.execute("SELECT vip_expire_at FROM users WHERE id=%s", (uid,))
                r = cur.fetchone()
                cur_vip = (r or {}).get("vip_expire_at") or 0
                base = max(now, cur_vip)
                if plan["months"] is None:
                    new_exp = LIFETIME_EXPIRE
                else:
                    new_exp = base + plan["months"] * 30 * 86400 * 1000
                cur.execute("UPDATE users SET vip_expire_at=%s WHERE id=%s", (new_exp, uid))
                conn.commit()
                return new_exp
        finally:
            conn.close()
    result = _auth_db_call(_upd)
    return (True, result, "") if result else (False, 0, "数据库错误，请重试")


def _auth_get_user_by_id(uid):
    if not (_PYMYSQL_OK and DATABASE_URL) or not uid:
        return None
    def _q():
        conn = _quest_conn()
        try:
            with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT id, username, password_hash, role, nickname, avatar, email, status, created_at, vip_expire_at "
                    "FROM users WHERE id=%s", (uid,))
                return cur.fetchone()
        finally:
            conn.close()
    return _auth_db_call(_q)


def _auth_get_user_by_username(username):
    if not (_PYMYSQL_OK and DATABASE_URL) or not username:
        return None
    def _q():
        conn = _quest_conn()
        try:
            with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT id, username, password_hash, role, nickname, avatar, email, status, created_at "
                    "FROM users WHERE username=%s", (username,))
                return cur.fetchone()
        finally:
            conn.close()
    return _auth_db_call(_q)


def _auth_count_users():
    if not (_PYMYSQL_OK and DATABASE_URL):
        return 0
    def _q():
        conn = _quest_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM users")
                row = cur.fetchone()
                return int(row[0] if isinstance(row, tuple) else row["c"])
        finally:
            conn.close()
    result = _auth_db_call(_q)
    return result if result is not None else 0


def _auth_db_call(fn):
    """执行一次 DB 操作；若因 TiDB 空闲连接回收/Serverless 休眠等原因报
    『连接丢失/超时/无法连接』，自动重连并重试，避免偶发 500。
    - Lost connection / timeout：最多重试 3 次，退避 2s/4s（Serverless 连接回收频繁）
    - Can't connect / 10060：先等待 15s（休眠唤醒通常 10-60s）再重试一次"""
    last_err = None
    for attempt in (1, 2, 3):
        try:
            return fn()
        except Exception as e:
            last_err = e
            msg = str(e)
            if ("Lost connection" in msg or "2013" in msg or "2006" in msg
                    or "timed out" in msg or "Broken pipe" in msg):
                if attempt < 3:
                    time.sleep(2 * attempt)  # 2s、4s 退避
                    continue
                break
            if "Can't connect" in msg or "2003" in msg or "10060" in msg:
                print("[auth] 连接失败，等待 15s 后重试（可能 TiDB 休眠唤醒中）……")
                time.sleep(15)
                try:
                    return fn()
                except Exception as e2:
                    print("[auth] 唤醒重试仍失败：", e2)
                    return None
            break
    print("[auth] 数据库操作失败：", last_err)
    return None


# ================= P1-A 用户管理（后台 admin 专属） =================

def _auth_list_users(page, size, q):
    """分页查询用户列表（不返回 password_hash）。失败返回 None。"""
    if not (_PYMYSQL_OK and DATABASE_URL):
        return None
    def _q():
        conn = _quest_conn()
        try:
            like = "%%%s%%" % (q or "")
            offset = (page - 1) * size
            with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                if q:
                    cur.execute(
                        "SELECT id, username, nickname, role, status, email, created_at "
                        "FROM users WHERE username LIKE %s OR nickname LIKE %s "
                        "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (like, like, size, offset))
                    rows = cur.fetchall()
                    cur.execute(
                        "SELECT COUNT(*) AS c FROM users WHERE username LIKE %s OR nickname LIKE %s",
                        (like, like))
                    total = cur.fetchone()["c"]
                else:
                    cur.execute(
                        "SELECT id, username, nickname, role, status, email, created_at "
                        "FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (size, offset))
                    rows = cur.fetchall()
                    cur.execute("SELECT COUNT(*) AS c FROM users")
                    total = cur.fetchone()["c"]
                return {"rows": rows, "total": total}
        finally:
            conn.close()
    return _auth_db_call(_q)


def _auth_update_user_role(uid, role):
    if not (_PYMYSQL_OK and DATABASE_URL) or not uid:
        return None
    def _q():
        conn = _quest_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET role=%s, updated_at=%s WHERE id=%s",
                    (role, int(time.time() * 1000), uid))
            conn.commit()
            return True
        finally:
            conn.close()
    return _auth_db_call(_q)


def _auth_update_user_status(uid, status):
    if not (_PYMYSQL_OK and DATABASE_URL) or not uid:
        return None
    def _q():
        conn = _quest_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET status=%s, updated_at=%s WHERE id=%s",
                    (int(status), int(time.time() * 1000), uid))
            conn.commit()
            return True
        finally:
            conn.close()
    return _auth_db_call(_q)


def _auth_reset_user_password(uid, password_hash):
    if not (_PYMYSQL_OK and DATABASE_URL) or not uid:
        return None
    def _q():
        conn = _quest_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash=%s, updated_at=%s WHERE id=%s",
                    (password_hash, int(time.time() * 1000), uid))
            conn.commit()
            return True
        finally:
            conn.close()
    return _auth_db_call(_q)


def _auth_count_role(role):
    """统计某角色的用户数（防锁死保护用）。失败返回 0。"""
    if not (_PYMYSQL_OK and DATABASE_URL):
        return 0
    def _q():
        conn = _quest_conn()
        try:
            with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS c FROM users WHERE role=%s AND status=1", (role,))
                return cur.fetchone()["c"]
        finally:
            conn.close()
    result = _auth_db_call(_q)
    return int(result or 0)


def _log_operation(user_id, username, action, target_type="", target_id="", detail=None, ip=""):
    """写一条管理员操作日志（失败仅打印，不影响主流程）。"""
    if not (_PYMYSQL_OK and DATABASE_URL):
        return
    def _w():
        conn = _quest_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO admin_operation_logs (id, user_id, username, action, target_type, target_id, detail, ip, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    ("log_" + uuid.uuid4().hex[:20], user_id or "", username or "",
                     action, target_type or "", target_id or "",
                     json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                     ip or "", int(time.time() * 1000)))
            conn.commit()
        finally:
            conn.close()
    _auth_db_call(_w)



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
    if _MINIO_OK:
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
    def _q():
        conn = _square_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO square_items
                    (id, title, category, level, video_url, description, author,
                     thumbnail, poster_url, views, tags, sentences, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        title = VALUES(title),
                        category = VALUES(category),
                        level = VALUES(level),
                        video_url = VALUES(video_url),
                        description = VALUES(description),
                        author = VALUES(author),
                        thumbnail = VALUES(thumbnail),
                        poster_url = VALUES(poster_url),
                        sentences = VALUES(sentences),
                        tags = VALUES(tags)
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
        return True
    # TiDB/MySQL 兼容重试（原 ON CONFLICT 为 PG 语法，TiDB 不支持，已改为 ON DUPLICATE KEY UPDATE）
    _auth_db_call(_q)


def _square_delete(item_id):
    def _q():
        conn = _square_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM square_items WHERE id = %s", (item_id,))
            conn.commit()
        finally:
            conn.close()
        return True
    _auth_db_call(_q)


COURSE_TAG_SYSTEM_PROMPT = """你是一个专业的中国俄语教育分类专家。你需要根据用户提供的【一级分类】和【OCR文本】，输出该内容对应的【年级】和【教材版本】。

输入变量：
一级分类：{{category}}
OCR文本：{{text}}

可选选项（必须严格从下列选项中选择，不可编造）：
【年级选项】：[全部, 一年级, 二年级, 三年级, 四年级, 五年级, 六年级, 七年级, 八年级, 九年级, 高中, 通用]
【版本选项】：[全部, 走遍俄罗斯, 大学俄语, 东方俄语, 新概念俄语, 黑大俄语, 北外俄语, 人教版初中, 人教版高中, 自编课等等]

判断规则：

二级标签（subcat）判断规则：
根据【一级分类】从下列对应标签池中选出最匹配的一个（不要超出该池；仅教材同步允许按文本中出现的新教材名生成新版本标签）：
- 教材同步 → 版本池：[走遍俄罗斯, 大学俄语, 东方俄语, 新概念俄语, 黑大俄语, 北外俄语, 人教版初中, 人教版高中, 自编课]（文本出现其他教材名时，允许生成该教材名作为标签）
- 考试备考 → [中高考, 专四专八, 考研, ТРКИ等级, 留学预科, CATTI, 职业俄语]
- 少儿俄语 → [少儿启蒙, 动画分级, 分级阅读, 动画绘本, 儿歌童谣, 字母拼读, 少儿词汇]
- 基础俄语 → [零基础路线, 字母发音, 基础语法, 基础词汇, 核心句型, 经典教材, 综合提升]
- 场景俄语 → [日常对话, 商务职场, 外贸商务, 旅游出行, 面试校园, 社交口语, 写作邮件]
- 阅读听力 → [短文精读, 俄语故事, 名著简写, 新闻短文, 文化科普, 专业阅读]
- 影视俄语 → [情景剧, 影视台词, 电影片段, 动画片段, 经典教材剧]
- 音乐俄语 → [俄语歌曲]
依据内容特征（标题关键词、词汇难度、语法点、题材）判断最合适的一项；内容特征不足以判断时填"全部"。该二级标签与年级判断独立，两者都要给出。

版本匹配规则（优先执行）：
- 仔细寻找文本中的教材名称（如"走遍俄罗斯"、"人教版"）、出版社名称（如"外研社"）或作者信息。
- 如果文本特征符合外语教学与研究出版社的《走遍俄罗斯》，则填"走遍俄罗斯"。
- 如果是国内义务教育阶段的教材，请根据学段匹配"人教版初中"或"人教版高中"。
- 如果文本信息太少或明显是机构自编资料，填"自编课"。

年级匹配规则（核心逻辑）：
情况A：有明确年级字样。如果文本中直接出现了"X年级"、"初一"、"高一"等字眼，直接匹配对应的年级。
情况B：无明确年级，根据内容进行推断（重点要求）。如果文本中没有明确出现年级，请根据提取的课程内容（词汇难度、语法知识点、课文主题）进行智能推断：
- 如果是俄语字母发音（33个字母）、拼读儿歌、最基础的问候语（如Привет） → 根据内容进行智能推断标签。
- 如果是基础语法（名词六格、动词第一/第二变位法）、校园日常对话、短篇故事 → 根据内容进行智能推断标签。
- 如果是动词完成体/未完成体、复杂从句、高考真题、俄罗斯文化阅读 → 根据内容进行智能推断标签。
- 如果是专业词汇（经贸、文学、翻译）、报刊选读、大学教材课文 → 根据内容进行智能推断标签。
情况C：彻底无法推断。如果文本纯属毫无特征的通用对话或残缺文本，再将 grade 设为 "通用"。

注意：如果一级分类是"考试备考"、"场景英语"等非年级绑定类别，请优先采用根据内容进行智能推断标签推断法。

置信度控制：
- 如果是有明确年级字样或版本名称（情况A），置信度请给 0.9 以上。
- 如果是根据内容推断的（情况B），置信度必须在 0.5 到 0.8 之间，并说明推断依据。
- 如果完全靠猜（情况C），置信度必须低于 0.5。
"""

COURSE_SPLIT_SYSTEM_PROMPT = """你是一个专业的俄语教材结构切分专家。用户会给你俄语教材（如《走遍俄罗斯》）的连续文本（可能是 OCR 结果，可能包含多课内容），你需要准确找出每一课的起始位置，把文本切成若干课。

切分规则（核心）：
1. 以明确的课程标题作为一课的开始，例如「Урок 1」「УРОК 2」「Урок 3 · 这是谁」「第4课」「第一课」等。课号按在文本中出现的顺序编号（1, 2, 3...），不要假设编号连续（教材中可能有复习课，按出现顺序编号即可）。
2. 一课从它的标题行开始，到下一课标题行之前结束（最后一课到文本结尾）。
3. 一课内部的内容（生词表、课文、例句等）不要拆分到其他课。
4. 如果整个文本中找不到任何可识别的课标题，则把整段文本视为 1 课。
5. 每课输出三个字段：
   - name：课名，保留教材标题原文，如「Урок 1 · 字母与问候」
   - desc：一句话中文简介（该课主题，如「字母与问候」）
   - vocab：该课包含的生词表原始行，逐行原样输出（格式为「词 | 释义」，一行一个词；若该课没有生词表行，则输出空字符串）

输出要求：严格只输出 JSON，格式为 {"lessons": [{"num": 1, "name": "...", "desc": "...", "vocab": "..."}, ...]}，不要输出任何其他文字。
"""

class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        ao = _allowed_origin(self.headers.get("Origin") or "")
        if ao:
            self.send_header("Access-Control-Allow-Origin", ao)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Content-Length, adminKey")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")

    def _handle_course_lesson_gen(self, data):
        """课程内容 AI 生成：生词表 → 一课（单词 + 渐进例句）。先学词、再渐进学句。"""
        title = (data.get("title") or "").strip() or "俄语课"
        category = (data.get("category") or "").strip() or "基础俄语"
        level = (data.get("level") or "").strip() or "A1"
        words_text = (data.get("words") or "").strip()
        if not words_text:
            return self._json(200, {"ok": False, "error": "缺少生词表（每行一个词，格式：词 | 释义）"})
        prompt = (
            "你是一个专业的俄语课程内容生成专家。用户提供一课的生词表，你需要为这一课生成完整学习内容，"
            "用于\"先学单词、再按难度渐进学例句\"的教学法。\n\n"
            "课程标题：" + title + "\n"
            "主分类：" + category + "\n"
            "难度：" + level + "\n"
            "本课生词表（每行：词 | 释义）：\n" + words_text[:2000] + "\n\n"
            "输出要求（严格只输出以下 JSON，不要任何其他文字）：\n"
            "{\n"
            '  "title": "课名，格式：第N课·主题，如：第1课·问候与初识",\n'
            '  "description": "本课一句话简介",\n'
            '  "words": [{"ru": "单词", "zh": "中文释义"}],\n'
            '  "sentences": [{"ru": "俄语句子", "zh": "中文翻译"}]\n'
            "}\n\n"
            "句子生成规则（核心）：\n"
            "1. 生词表中的每一个单词至少配 1 个例句（常用词可配 2 个）。\n"
            "2. 例句必须渐进式排列：先短后长（先 2-4 词的最短句，再逐步加长）；先易后难（先只含 1 个生词的简单陈述句，"
            "再组合多个生词，再带疑问/否定/复合结构）；后面的句子尽量复用前面出现过的生词，滚动巩固。\n"
            "3. 句子必须真实、自然、符合俄语语法与常见使用场景，不要生硬直译。\n"
            "4. 每句只放俄语原句与中文翻译。\n"
            "5. 句子数量（重要）：生词表中的每一个单词至少配 1 句例句，核心常用词可配 2 句；总句数下限 = 生词数 × 1.2，上限 120 句。例如：生词 46 个 → 生成约 55-90 句；生词 10 个 → 生成约 12-20 句。必须保证生词表中的每一个单词都出现在至少一个句子里。"
        )
        messages = [
            {"role": "system", "content": "你是俄语课程内容生成专家，输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ]
        try:
            content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
            self._log_op(data, "course_lesson_gen", "course", title, {"category": category, "level": level})
            return self._json(200, {"ok": True, "content": content})
        except RuntimeError as e:
            return self._json(200, {"ok": False, "error": str(e)})
        except Exception as e:
            return self._json(200, {"ok": False, "error": "AI请求异常：" + str(e)})

    def _rule_split_course(self, text):
        """规则切分：按规范课标题行（Урок N / 第N课）+ 词表行直接切分，不依赖 AI。返回 lessons 或 None"""
        import re as _re
        lines = text.splitlines()
        pat = _re.compile(r'^\s*(?:УРОК|Урок|урок)\s*\d+\s*[·.\-—]?\s*(.*)$|^\s*第\s*\d+\s*课\s*[·.\-—]?\s*(.*)$', _re.I)
        idxs = [i for i, ln in enumerate(lines) if pat.match(ln.strip())]
        if not idxs:
            return None
        lessons = []
        for k, start in enumerate(idxs):
            end = idxs[k + 1] if k + 1 < len(idxs) else len(lines)
            block = lines[start:end]
            head = block[0].strip()
            m = _re.match(r'^\s*(?:УРОК|Урок|урок)\s*\d+\s*[·.\-—]?\s*(.*)$', head, _re.I)
            if not m:
                m = _re.match(r'^\s*第\s*\d+\s*课\s*[·.\-—]?\s*(.*)$', head)
            theme = (m.group(1).strip() if m else head)[:40] or ("第 %d 课" % (k + 1))
            vocab = []
            for ln in block[1:]:
                ln = ln.strip()
                if not ln or ln.startswith('#'):
                    continue
                if _re.match(r'^[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\-\' ]{0,40}\s*[|｜]\s*\S+', ln):
                    vocab.append(ln)
            lessons.append({
                "num": k + 1,
                "name": head[:40],
                "desc": theme,
                "vocab": "\n".join(vocab),
            })
        return lessons

    def _handle_course_split(self, data):
        """自动切课：优先规则切分（规范 Урок N 标题行直接切），规则不适用再 AI 智能识别课边界"""
        title = (data.get("title") or "").strip() or "俄语课程"
        category = (data.get("category") or "").strip() or "基础俄语"
        level = (data.get("level") or "").strip() or "A1"
        text = (data.get("text") or "").strip()
        if not text:
            return self._json(200, {"ok": False, "error": "缺少文本（请粘贴整本书或连续多课的文本）"})
        # 1) 规则切分：格式规范的批次文本直接按「Урок N」标题行切，秒回、100% 准、不依赖 AI
        try:
            lessons = self._rule_split_course(text)
        except Exception:
            lessons = None
        if lessons:
            return self._json(200, {"ok": True, "content": json.dumps({"lessons": lessons}, ensure_ascii=False)})
        # 2) AI 兜底：无规范标题（用户贴 OCR 整书）时智能识别
        truncated = len(text) > 20000
        if truncated:
            text = text[:20000]
        prompt = COURSE_SPLIT_SYSTEM_PROMPT + "\n\n待切分文本（课程标题：" + title + "，主分类：" + category + "，难度：" + level + "）：\n" + text
        if truncated:
            prompt += "\n\n[注意：文本过长已截断，仅切分以上可见部分，其余课请分批粘贴]"
        messages = [
            {"role": "system", "content": "你是俄语教材结构切分专家，输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ]
        try:
            content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
            return self._json(200, {"ok": True, "content": content})
        except RuntimeError as e:
            return self._json(200, {"ok": False, "error": str(e)})
        except Exception as e:
            return self._json(200, {"ok": False, "error": "AI请求异常：" + str(e)})

    def _handle_course_tag(self, data):
        """课程自动打标：根据一级分类 + OCR文本 → {年级, 教材版本, 置信度, 依据}"""
        category = (data.get("category") or "").strip()
        text = (data.get("text") or "").strip()
        if not text:
            return self._json(200, {"ok": False, "error": "缺少 OCR 文本"})
        prompt = COURSE_TAG_SYSTEM_PROMPT.replace("{{category}}", category or "未知").replace("{{text}}", text[:2000])
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请根据以上规则输出分类结果。严格只输出 JSON，格式为：grade(年级)、textbook(教材版本)、subcat(二级筛选标签)、confidence(0到1的置信度数字)、reason(一句话推断依据)。不要输出任何其他文字。"},
        ]
        try:
            content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
            return self._json(200, {"ok": True, "content": content})
        except RuntimeError as e:
            return self._json(200, {"ok": False, "error": str(e)})
        except Exception as e:
            return self._json(200, {"ok": False, "error": "AI请求异常：" + str(e)})

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
        # B2 素材：b2://key → 预签名播放 URL（后端直接下载转写，不经过本服务存储）
        if url.startswith(_B2_PREFIX):
            url = _b2_resolve(url)
            if not url:
                return self._json(200, {"ok": False, "error": "B2 视频解析失败，请确认素材已上传到云端"})
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

    def _auth_identity(self, data):
        """解析当前请求身份。优先 Bearer JWT（或 body token），其次兼容旧 adminKey。
        返回 dict(user) 或 None。"""
        # 1) JWT 登录态
        token = extract_bearer(self.headers, data)
        if token:
            payload = decode_token(SECRET_KEY, token)
            if payload and payload.get("sub"):
                row = _auth_get_user_by_id(payload.get("sub"))
                if row and row.get("status") == 1:
                    return row
        # 2) 旧 adminKey 兼容（双轨过渡）
        if ADMIN_KEY and data and (data.get("adminKey") or "").strip() == ADMIN_KEY:
            return {"id": "", "username": "adminKey", "role": "admin", "nickname": ""}
        return None

    def _require_backend(self, data):
        """管理后台鉴权：返回 (user, None) 或 (None, 错误响应)。角色须在 admin/editor/viewer。"""
        ident = self._auth_identity(data)
        if ident and ident.get("role") in BACKEND_ROLES:
            return ident, None
        if not ADMIN_KEY and not ident:
            return None, self._json(500, {"ok": False, "error": "未配置管理员密钥（ADMIN_KEY）"})
        return None, self._json(403, {"ok": False, "error": "无权限：未登录或角色无权限"})

    def _log_op(self, data, action, target_type="", target_id="", detail=None):
        """便捷埋点：记录当前请求的操作日志（IP 取自连接）。"""
        ident = self._auth_identity(data)
        ip = self.client_address[0] if self.client_address else ""
        _log_operation(
            (ident or {}).get("id", ""),
            (ident or {}).get("username", ""),
            action, target_type, target_id, detail, ip,
        )

    def _check_admin(self, data):
        """管理写操作校验（兼容过渡）：JWT(admin/editor/viewer) 或 adminKey 任一通过。
        返回 None 表示通过，否则返回错误响应。"""
        ident = self._auth_identity(data)
        if ident and ident.get("role") in ADMIN_WRITE_ROLES:
            return None
        if not ADMIN_KEY and not ident:
            return self._json(500, {"ok": False, "error": "未配置管理员密钥（ADMIN_KEY）"})
        return self._json(403, {"ok": False, "error": "无权限：管理员密钥错误或未登录"})

    # ---------- P0 认证接口 ----------

    def _handle_auth_register(self, data):
        """POST /api/auth/register —— 开放注册。首个注册账号自动成为 admin（引导建站），其余为 learner。"""
        if not SECRET_KEY:
            return self._json(500, {"ok": False, "error": "未配置 SECRET_KEY（请设置环境变量后重启）"})
        if not pyjwt_available():
            return self._json(500, {"ok": False, "error": "未安装 PyJWT（pip install PyJWT）"})
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        nickname = str(data.get("nickname") or "").strip()[:64]
        ok, err = validate_username(username)
        if not ok:
            return self._json(400, {"ok": False, "error": err})
        if len(password) < 6:
            return self._json(400, {"ok": False, "error": "密码至少 6 位"})
        if _auth_get_user_by_username(username):
            return self._json(409, {"ok": False, "error": "用户名已存在"})
        role = "admin" if _auth_count_users() == 0 else "learner"
        uid = "u_" + uuid.uuid4().hex[:20]
        now = int(time.time() * 1000)

        def _ins():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO users (id, username, password_hash, role, nickname, status, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (uid, username, hash_password(password), role,
                         nickname or None, 1, now, now))
                conn.commit()
            finally:
                conn.close()
            return True

        if _auth_db_call(_ins) is not True:
            return self._json(500, {"ok": False, "error": "注册失败：数据库写入失败，请重试"})
        token = create_token(SECRET_KEY, uid, role, TOKEN_TTL)
        return self._json(200, {"ok": True, "token": token, "user": {
            "id": uid, "username": username, "role": role, "nickname": nickname or "",
            "isFirstAdmin": role == "admin",
        }})

    def _handle_auth_login(self, data):
        """POST /api/auth/login —— 任何角色（含 learner）均可登录拿 token。"""
        if not SECRET_KEY:
            return self._json(500, {"ok": False, "error": "未配置 SECRET_KEY（请设置环境变量后重启）"})
        if not pyjwt_available():
            return self._json(500, {"ok": False, "error": "未安装 PyJWT（pip install PyJWT）"})
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        if not username or not password:
            return self._json(400, {"ok": False, "error": "请输入用户名和密码"})
        row = _auth_get_user_by_username(username)
        if not row or not verify_password(password, row.get("password_hash") or ""):
            return self._json(401, {"ok": False, "error": "用户名或密码错误"})
        if row.get("status") != 1:
            return self._json(403, {"ok": False, "error": "账号已被禁用"})
        token = create_token(SECRET_KEY, row["id"], row["role"], TOKEN_TTL)
        print("[auth] 登录成功: username=%s role=%s token_len=%s" % (
            row["username"], row["role"], len(token) if token else 0))
        return self._json(200, {"ok": True, "token": token, "user": {
            "id": row["id"], "username": row["username"], "role": row["role"],
            "nickname": row.get("nickname") or "", "avatar": row.get("avatar") or "",
        }})

    def _handle_auth_me(self, data):
        """POST /api/auth/me —— 用 token 换当前用户信息。"""
        ident = self._auth_identity(data)
        if not ident or not ident.get("id"):
            return self._json(401, {"ok": False, "error": "未登录或登录已过期"})
        return self._json(200, {"ok": True, "user": {
            "id": ident["id"], "username": ident["username"], "role": ident["role"],
            "nickname": ident.get("nickname") or "", "avatar": ident.get("avatar") or "",
        }})


    def _handle_square_list(self):
        if not (_PYMYSQL_OK and DATABASE_URL):
            return self._json(200, {"ok": True, "list": []})
        try:
            return self._json(200, {"ok": True, "list": _square_list()})
        except Exception as e:
            print("[square] 读取列表失败：", e)
            return self._json(200, {"ok": True, "list": []})


    def _handle_course_complete(self, data):
        """保存课程练习记录（P1-B：已登录用户记录 user_id，匿名保持 ''）"""
        try:
            course_id = (data.get("course_id") or "").strip()
            if not course_id:
                return self._json(400, {"ok": False, "error": "缺少 course_id"})
            completion_time = int(data.get("completion_time") or 0)
            correct_count = int(data.get("correct_count") or 0)
            total_count = int(data.get("total_count") or 0)
            max_combo = int(data.get("max_combo") or 0)
            rating = (data.get("rating") or "C").strip()
            ident = self._auth_identity(data)
            user_id = (ident or {}).get("id") or ""
            record_id = uuid.uuid4().hex[:24]
            created_at = int(time.time() * 1000)

            def _save():
                conn = _quest_conn()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO quest_learning_records (id, user_id, course_id, completion_time, correct_count, total_count, max_combo, rating, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (record_id, user_id, course_id, completion_time, correct_count, total_count, max_combo, rating, created_at)
                        )
                    conn.commit()
                finally:
                    conn.close()
                return True

            if _auth_db_call(_save) is not True:
                return self._json(500, {"ok": False, "error": "保存失败：数据库错误，请重试"})
            return self._json(200, {"ok": True, "data": {"id": record_id}})
        except Exception as e:
            print("[quest] 保存练习记录失败:", e)
            return self._json(500, {"ok": False, "error": str(e)})

    def _handle_learning_progress_save(self, data):
        """POST /api/learning/progress/save —— 登录用户批量上报学习断点/完成标记（UPSERT）"""
        ident = self._auth_identity(data)
        if not ident or not ident.get("id"):
            return self._json(401, {"ok": False, "error": "未登录，无法同步学习进度"})
        user_id = ident["id"]
        items = data.get("items") or []
        if not isinstance(items, list) or not items:
            return self._json(400, {"ok": False, "error": "缺少 items"})
        if len(items) > 100:
            return self._json(400, {"ok": False, "error": "单次最多 100 条"})

        def _save():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    for it in items:
                        unit_id = (it.get("unit_id") or "").strip()
                        mode = (it.get("mode") or "").strip()
                        course_id = (it.get("course_id") or "").strip()
                        if not unit_id or not mode:
                            continue
                        seq_index = int(it.get("seq_index") or 0)
                        unit_index = int(it.get("unit_index") or 0)
                        difficulty = (it.get("difficulty") or "")[:16]
                        status = 1 if it.get("status") else 0
                        ts = int(it.get("ts") or 0) or int(time.time() * 1000)
                        cur.execute(
                            "INSERT INTO quest_learning_progress (id, user_id, course_id, unit_id, mode, seq_index, unit_index, difficulty, status, ts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                            "ON DUPLICATE KEY UPDATE seq_index=VALUES(seq_index), unit_index=VALUES(unit_index), difficulty=VALUES(difficulty), status=VALUES(status), ts=VALUES(ts)",
                            (uuid.uuid4().hex[:24], user_id, course_id, unit_id, mode,
                             seq_index, unit_index, difficulty, status, ts))
                conn.commit()
            finally:
                conn.close()
            return True

        if _auth_db_call(_save) is not True:
            return self._json(500, {"ok": False, "error": "同步失败：数据库写入失败，请重试"})
        return self._json(200, {"ok": True, "count": len(items)})

    def _handle_learning_progress_get(self, data):
        """POST /api/learning/progress —— 登录用户拉取自己的学习断点/完成标记（可按 course_id 过滤）"""
        ident = self._auth_identity(data)
        if not ident or not ident.get("id"):
            return self._json(401, {"ok": False, "error": "未登录，无法读取学习进度"})
        user_id = ident["id"]
        course_id = (data.get("course_id") or "").strip()

        def _load():
            conn = _quest_conn()
            try:
                with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                    if course_id:
                        cur.execute(
                            "SELECT unit_id, mode, seq_index, unit_index, difficulty, status, ts FROM quest_learning_progress WHERE user_id=%s AND course_id=%s",
                            (user_id, course_id))
                    else:
                        cur.execute(
                            "SELECT unit_id, mode, seq_index, unit_index, difficulty, status, ts FROM quest_learning_progress WHERE user_id=%s",
                            (user_id,))
                    return cur.fetchall() or []
            finally:
                conn.close()

        rows = _auth_db_call(_load)
        if rows is None:
            return self._json(500, {"ok": False, "error": "读取失败：数据库错误，请重试"})
        return self._json(200, {"ok": True, "items": rows})

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
            self._log_op(data, "square_submit", "square_item", item.get("id"), {"title": item.get("title")})
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
            self._log_op(data, "square_delete", "square_item", data.get("id"))
            return self._json(200, {"ok": True})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "删除失败：" + str(e)})

    def _handle_admin_check(self, data):
        if not ADMIN_KEY:
            return self._json(200, {"ok": False, "error": "未配置管理员密钥（ADMIN_KEY）"})
        ok = (data.get("adminKey") or "").strip() == ADMIN_KEY
        return self._json(200, {"ok": ok})

    # ---------- P1-A 用户管理（仅 admin 可调用） ----------

    def _require_admin(self, data):
        """仅管理员可操作（JWT role=admin 或旧 adminKey 兼容）。返回 None 或错误响应。"""
        ident = self._auth_identity(data)
        if ident and ident.get("role") == "admin":
            return None
        if not ADMIN_KEY and not ident:
            return self._json(500, {"ok": False, "error": "未配置管理员密钥（ADMIN_KEY）"})
        return self._json(403, {"ok": False, "error": "无权限：仅管理员可管理用户"})

    def _handle_admin_users_list(self, data):
        err = self._require_admin(data)
        if err:
            return err
        try:
            page = max(1, int(data.get("page") or 1))
            size = min(50, max(1, int(data.get("size") or 10)))
        except (TypeError, ValueError):
            page, size = 1, 10
        q = str(data.get("q") or "").strip()[:64]
        result = _auth_list_users(page, size, q)
        if result is None:
            return self._json(500, {"ok": False, "error": "查询用户失败（数据库不可用）"})
        return self._json(200, {"ok": True, "rows": result["rows"], "total": result["total"], "page": page, "size": size})

    def _handle_admin_user_role(self, data):
        err = self._require_admin(data)
        if err:
            return err
        uid = str(data.get("id") or "").strip()
        role = str(data.get("role") or "").strip()
        if not uid:
            return self._json(400, {"ok": False, "error": "缺少用户 id"})
        if role not in ROLES:
            return self._json(400, {"ok": False, "error": "角色无效：" + role})
        target = _auth_get_user_by_id(uid)
        if not target:
            return self._json(404, {"ok": False, "error": "用户不存在"})
        ident = self._auth_identity(data)
        if ident and ident.get("id") and ident.get("id") == uid:
            return self._json(400, {"ok": False, "error": "不能修改自己的角色（防止锁死后台）"})
        # 最后一个 admin 保护：把 admin 降级前检查剩余 admin 数
        if target.get("role") == "admin" and role != "admin":
            if _auth_count_role("admin") <= 1:
                return self._json(400, {"ok": False, "error": "系统至少保留一名管理员"})
        if _auth_update_user_role(uid, role) is not True:
            return self._json(500, {"ok": False, "error": "更新角色失败"})
        self._log_op(data, "user_role_update", "user", uid, {"role": role, "username": target.get("username")})
        return self._json(200, {"ok": True})

    # ---------- P1-E 数据看板（仅 admin） ----------

    def _handle_admin_dashboard_stats(self, data):
        """POST /api/admin/dashboard/stats —— 后台数据看板聚合统计"""
        err = self._require_admin(data)
        if err:
            return err

        def _stats():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    now = int(time.time() * 1000)
                    d7 = now - 7 * 86400 * 1000
                    d14 = now - 14 * 86400 * 1000

                    # 用户
                    cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
                    role_rows = {r[0]: r[1] for r in cur.fetchall()}
                    cur.execute("SELECT COUNT(*) FROM users")
                    total_users = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM users WHERE created_at >= %s", (d7,))
                    new7 = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM users WHERE created_at >= %s", (d14,))
                    new14 = cur.fetchone()[0]

                    # 近 14 天注册趋势（TiDB: FROM_UNIXTIME(ms/1000)）
                    cur.execute(
                        "SELECT DATE(FROM_UNIXTIME(created_at/1000)), COUNT(*) FROM users "
                        "WHERE created_at >= %s GROUP BY DATE(FROM_UNIXTIME(created_at/1000)) ORDER BY 1", (d14,))
                    trend = {str(r[0]): r[1] for r in cur.fetchall()}

                    # 课程
                    cur.execute("SELECT COUNT(*) FROM quest_course_packs")
                    packs = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM quest_courses")
                    units = cur.fetchone()[0]

                    # 学习记录（含匿名，user_id='' 也计入；活跃按有记名用户）
                    cur.execute("SELECT COUNT(*), COALESCE(AVG(correct_count / NULLIF(total_count, 0)), 0), COALESCE(MAX(max_combo), 0) FROM quest_learning_records")
                    lr = cur.fetchone()
                    cur.execute("SELECT COUNT(*) FROM quest_learning_records WHERE created_at >= %s", (d7,))
                    lr7 = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(DISTINCT user_id) FROM quest_learning_records WHERE created_at >= %s AND user_id <> ''", (d7,))
                    act7 = cur.fetchone()[0]

                    # 评级分布
                    cur.execute("SELECT rating, COUNT(*) FROM quest_learning_records GROUP BY rating")
                    ratings = {r[0]: r[1] for r in cur.fetchall()}

                    # 完成次数 Top 课时（关联课时标题）
                    cur.execute(
                        "SELECT r.course_id, c.title, COUNT(*) FROM quest_learning_records r "
                        "LEFT JOIN quest_courses c ON c.id = r.course_id "
                        "GROUP BY r.course_id, c.title ORDER BY 3 DESC LIMIT 5")
                    top = [{"course_id": r[0], "title": r[1] or r[0], "count": r[2]} for r in cur.fetchall()]
                return {
                    "users": {"total": total_users, "roles": role_rows, "new_7d": new7, "new_14d": new14, "trend": trend},
                    "courses": {"packs": packs, "units": units},
                    "learning": {"records": lr[0], "avg_accuracy": round(float(lr[1]) * 100, 1), "max_combo": lr[2], "records_7d": lr7, "active_users_7d": act7},
                    "ratings": ratings,
                    "top_courses": top,
                }
            finally:
                conn.close()

        stats = _auth_db_call(_stats)
        if stats is None:
            return self._json(500, {"ok": False, "error": "统计失败：数据库错误，请重试"})
        return self._json(200, {"ok": True, "stats": stats})

    # ---------- P1-D 会员 / 订单（微信支付骨架 + 后台手动确认兜底） ----------

    def _handle_vip_plans(self, data):
        """POST /api/vip/plans —— 会员套餐（公开；价格后台可配，缺省用常量）"""
        plans = [{"key": k, "name": v["name"], "amount_cents": v["amount_cents"],
                  "months": v["months"], "tag": v["tag"]} for k, v in _vip_plans().items()]
        return self._json(200, {"ok": True, "plans": plans, "pay_ready": _wx_pay_ready()})

    def _handle_vip_status(self, data):
        """POST /api/vip/status —— 当前登录用户 VIP 状态"""
        ident = self._auth_identity(data)
        if not ident or not ident.get("id"):
            return self._json(401, {"ok": False, "error": "请先登录"})
        now = int(time.time() * 1000)
        exp = ident.get("vip_expire_at") or 0
        if exp >= LIFETIME_EXPIRE:
            is_vip, left, level = True, 99999, "lifetime"
        elif exp > now:
            is_vip, left, level = True, max(1, (exp - now) // 86400000), "term"
        else:
            is_vip, left, level = False, 0, ""
        return self._json(200, {"ok": True, "is_vip": is_vip, "vip_expire_at": exp,
                                "days_left": left, "level": level})

    def _handle_order_create(self, data):
        """POST /api/order/create —— 创建订单（登录；同用户未支付订单幂等复用）"""
        ident = self._auth_identity(data)
        if not ident or not ident.get("id"):
            return self._json(401, {"ok": False, "error": "请先登录"})
        uid = ident["id"]
        plan_key = str(data.get("plan_key") or "").strip()
        plan = _vip_plans().get(plan_key)
        if not plan:
            return self._json(400, {"ok": False, "error": "未知套餐"})
        now = int(time.time() * 1000)

        def _create():
            conn = _quest_conn()
            try:
                with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                    # 幂等：同一用户最近一张未支付同套餐订单直接复用
                    cur.execute("SELECT id, order_no FROM orders WHERE user_id=%s AND plan_key=%s AND status='created' ORDER BY created_at DESC LIMIT 1", (uid, plan_key))
                    r = cur.fetchone()
                    if r:
                        return r
                    oid = "ord_" + uuid.uuid4().hex[:12]
                    ono = "WX" + str(now) + uuid.uuid4().hex[:4]
                    cur.execute(
                        "INSERT INTO orders (id, order_no, user_id, plan_key, amount_cents, currency, status, pay_channel, created_at) "
                        "VALUES (%s,%s,%s,%s,%s,'CNY','created','wechat',%s)", (oid, ono, uid, plan_key, plan["amount_cents"], now))
                    conn.commit()
                    return {"id": oid, "order_no": ono}
            finally:
                conn.close()

        result = _auth_db_call(_create)
        if not result:
            return self._json(500, {"ok": False, "error": "创建订单失败：数据库错误，请重试"})
        return self._json(200, {"ok": True, "order_no": result["order_no"],
                                "plan_key": plan_key, "amount_cents": plan["amount_cents"],
                                "plan_tag": plan["tag"], "pay_ready": _wx_pay_ready()})

    def _handle_order_status(self, data):
        """POST /api/order/status —— 查询本人订单状态（前端轮询支付结果）"""
        ident = self._auth_identity(data)
        if not ident or not ident.get("id"):
            return self._json(401, {"ok": False, "error": "请先登录"})
        order_no = str(data.get("order_no") or "").strip()
        if not order_no:
            return self._json(400, {"ok": False, "error": "缺少订单号"})
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                    cur.execute("SELECT order_no, plan_key, amount_cents, status, paid_at FROM orders WHERE user_id=%s AND order_no=%s", (ident["id"], order_no))
                    return cur.fetchone()
            finally:
                conn.close()
        row = _auth_db_call(_q)
        if not row:
            return self._json(404, {"ok": False, "error": "订单不存在"})
        return self._json(200, {"ok": True, "order": row})

    def _handle_order_manual_pay(self, data):
        """POST /api/order/manual-pay —— 管理员手动确认收款（兜底：无支付资质阶段）"""
        err = self._require_admin(data)
        if err:
            return err
        order_no = str(data.get("order_no") or "").strip()
        trade_no = str(data.get("trade_no") or "").strip()[:64]
        if not order_no:
            return self._json(400, {"ok": False, "error": "缺少订单号"})

        def _pay():
            conn = _quest_conn()
            try:
                with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                    cur.execute("SELECT user_id, plan_key, status FROM orders WHERE order_no=%s", (order_no,))
                    r = cur.fetchone()
                    if not r:
                        return None
                    if r["status"] == "paid":
                        return {"dup": True, "user_id": r["user_id"], "plan_key": r["plan_key"]}
                    now = int(time.time() * 1000)
                    cur.execute("UPDATE orders SET status='paid', trade_no=%s, paid_at=%s WHERE order_no=%s AND status='created'", (trade_no or order_no, now, order_no))
                    if cur.rowcount != 1:
                        return None
                    conn.commit()
                    return {"dup": False, "user_id": r["user_id"], "plan_key": r["plan_key"]}
            finally:
                conn.close()

        row = _auth_db_call(_pay)
        if not row:
            return self._json(404, {"ok": False, "error": "订单不存在或状态已变更"})
        if row.get("dup"):
            return self._json(200, {"ok": True, "already_paid": True})
        ok, new_exp, e = _grant_vip(row["user_id"], row["plan_key"])
        if not ok:
            return self._json(500, {"ok": False, "error": e})
        self._log_op(data, "order_manual_pay", "order", order_no, {"plan": row["plan_key"], "vip_expire_at": new_exp})
        return self._json(200, {"ok": True, "vip_expire_at": new_exp})

    def _handle_admin_orders(self, data):
        """POST /api/admin/orders —— 订单列表（admin，分页搜索）"""
        err = self._require_admin(data)
        if err:
            return err
        try:
            page = max(1, int(data.get("page") or 1))
            size = min(50, max(1, int(data.get("size") or 10)))
        except (TypeError, ValueError):
            page, size = 1, 10
        q = str(data.get("q") or "").strip()[:64]
        status = str(data.get("status") or "").strip()
        offset = (page - 1) * size

        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor(cursor=pymysql.cursors.DictCursor) as cur:
                    where = ["1=1"]
                    args = []
                    if status and status in ("created", "paid", "failed", "cancelled"):
                        where.append("o.status=%s"); args.append(status)
                    if q:
                        where.append("(o.order_no LIKE %s OR u.username LIKE %s)"); args.append("%" + q + "%"); args.append("%" + q + "%")
                    sql = ("SELECT o.order_no, o.user_id, u.username, o.plan_key, o.amount_cents, o.currency, o.status, "
                           "o.pay_channel, o.trade_no, o.paid_at, o.created_at FROM orders o "
                           "LEFT JOIN users u ON u.id=o.user_id WHERE " + " AND ".join(where) +
                           " ORDER BY o.created_at DESC LIMIT %s OFFSET %s")
                    cur.execute(sql, args + [size, offset])
                    rows = cur.fetchall()
                    cur.execute("SELECT COUNT(*) c FROM orders o LEFT JOIN users u ON u.id=o.user_id WHERE " + " AND ".join(where), args)
                    total = cur.fetchone()["c"]
                    return {"rows": rows, "total": total}
            finally:
                conn.close()

        result = _auth_db_call(_q)
        if not result:
            return self._json(500, {"ok": False, "error": "查询订单失败（数据库不可用）"})
        return self._json(200, {"ok": True, "rows": result["rows"], "total": result["total"], "page": page, "size": size})

    def _handle_categories_tree(self, data=None):
        """POST /api/categories/tree —— 公开分类树（商城标签栏/后台表单数据源；失败时前端回退静态体系）"""
        try:
            return self._json(200, {"ok": True, "tree": _categories_tree()})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "读取分类失败：" + str(e)})

    def _handle_admin_categories_list(self, data):
        """POST /api/admin/categories/list —— 全量分类（含停用），admin"""
        err = self._require_admin(data)
        if err:
            return err
        try:
            rows = _category_rows(active_only=False)
            return self._json(200, {"ok": True, "rows": rows})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "读取分类失败：" + str(e)})

    def _handle_admin_categories_save(self, data):
        """POST /api/admin/categories/save —— 新增/修改分类（id 存在=改，否则=增），admin"""
        err = self._require_admin(data)
        if err:
            return err
        name = str(data.get("name") or "").strip()[:64]
        sub_name = str(data.get("sub_name") or "").strip()[:64]
        if not name:
            return self._json(400, {"ok": False, "error": "主分类不能为空"})
        cid = str(data.get("id") or "").strip()
        try:
            sort_order = int(data.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        # 缺省视为启用（新增即上架）；显式传 0/false 才停用
        is_active = 0 if data.get("is_active") in (0, False, "0", "false") else 1

        def _save():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    if cid:
                        cur.execute("UPDATE categories SET name=%s, sub_name=%s, sort_order=%s, is_active=%s WHERE id=%s",
                                    (name, sub_name, sort_order, is_active, cid))
                        if cur.rowcount == 0:
                            return "not_found"
                    else:
                        nid = "cat_" + hashlib.md5((name + "|" + sub_name).encode("utf-8")).hexdigest()[:16]
                        cur.execute("INSERT INTO categories (id, name, sub_name, sort_order, is_active, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                                    (nid, name, sub_name, sort_order, is_active, int(time.time() * 1000)))
                    conn.commit()
                    return "ok"
            except Exception as e:
                conn.rollback()
                return "dup" if ("Duplicate" in str(e)) else ("err:" + str(e))
            finally:
                conn.close()

        result = _auth_db_call(_save)
        if result == "ok":
            return self._json(200, {"ok": True})
        if result == "not_found":
            return self._json(404, {"ok": False, "error": "分类不存在"})
        if result == "dup":
            return self._json(400, {"ok": False, "error": "该主分类下的子分类已存在"})
        return self._json(500, {"ok": False, "error": "保存失败：" + str(result)})

    def _handle_admin_categories_delete(self, data):
        """POST /api/admin/categories/delete —— 删除分类；{id} 删单条，{name} 删整个主分类（含其所有子分类），admin"""
        err = self._require_admin(data)
        if err:
            return err
        cid = str(data.get("id") or "").strip()
        name = str(data.get("name") or "").strip()

        def _del():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    if cid:
                        cur.execute("DELETE FROM categories WHERE id=%s", (cid,))
                    elif name:
                        cur.execute("DELETE FROM categories WHERE name=%s", (name,))
                    else:
                        return "param"
                    conn.commit()
                    return "ok"
            finally:
                conn.close()

        result = _auth_db_call(_del)
        if result == "ok":
            return self._json(200, {"ok": True})
        if result == "param":
            return self._json(400, {"ok": False, "error": "缺少 id 或 name"})
        return self._json(500, {"ok": False, "error": "删除失败"})

    # ---------- P1-F 系统设置 ----------

    def _handle_settings_public(self, data=None):
        """POST /api/settings/public —— 公开设置（站点信息 + 套餐价格；商城/VIP 弹窗读）"""
        try:
            plans = [{"key": k, "name": v["name"], "amount_cents": v["amount_cents"],
                      "months": v["months"], "tag": v["tag"]} for k, v in _vip_plans().items()]
            site = _site_info()
            return self._json(200, {"ok": True, "site": site, "plans": plans})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "读取设置失败：" + str(e)})

    def _handle_admin_settings_get(self, data):
        """POST /api/admin/settings/get —— 全量设置（admin）"""
        err = self._require_admin(data)
        if err:
            return err
        try:
            return self._json(200, {"ok": True, "site": _site_info(), "vip_plans": _vip_plans()})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "读取设置失败：" + str(e)})

    def _handle_admin_settings_save(self, data):
        """POST /api/admin/settings/save —— 保存设置（admin）：site{name,subtitle,announcement} + vip_plans{month/quarter/year/lifetime}"""
        err = self._require_admin(data)
        if err:
            return err
        site = data.get("site")
        if site is not None:
            if not isinstance(site, dict):
                return self._json(400, {"ok": False, "error": "site 参数格式错误"})
            merged = dict(_DEFAULT_SITE)
            for k in merged:
                if k in site:
                    merged[k] = str(site[k] or "").strip()[:200]
            if not merged["site_name"]:
                return self._json(400, {"ok": False, "error": "站点名称不能为空"})
            if not _save_settings("site", merged):
                return self._json(500, {"ok": False, "error": "保存站点信息失败"})
        plans = data.get("vip_plans")
        if plans is not None:
            if not isinstance(plans, dict):
                return self._json(400, {"ok": False, "error": "vip_plans 参数格式错误"})
            base = _vip_plans()
            new_plans = {}
            for k in ("month", "quarter", "year", "lifetime"):
                p = plans.get(k)
                if p is None:
                    new_plans[k] = base[k]
                    continue
                if not isinstance(p, dict):
                    return self._json(400, {"ok": False, "error": "套餐 " + k + " 格式错误"})
                try:
                    amount = int(p.get("amount_cents", base[k]["amount_cents"]))
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False, "error": "套餐 " + k + " 价格必须为整数（单位：分）"})
                if amount < 0:
                    return self._json(400, {"ok": False, "error": "套餐 " + k + " 价格不能为负"})
                name = str(p.get("name") or base[k]["name"]).strip()[:32]
                months = p.get("months")
                if months is not None:
                    try:
                        months = int(months)
                    except (TypeError, ValueError):
                        return self._json(400, {"ok": False, "error": "套餐 " + k + " 时长必须为整数（月）或 null"})
                    if months < 1:
                        return self._json(400, {"ok": False, "error": "套餐 " + k + " 时长必须 ≥1 个月或为终身"})
                tag = str(p.get("tag") or (name + " " + str(amount // 100) + " 元")).strip()[:64]
                new_plans[k] = {"name": name, "amount_cents": amount, "months": months, "tag": tag}
            if not _save_settings("vip_plans", new_plans):
                return self._json(500, {"ok": False, "error": "保存套餐配置失败"})
        return self._json(200, {"ok": True})


    def _handle_pay_wechat_notify(self, data):
        """POST /api/pay/wechat/notify —— 微信支付 v3 回调（骨架：配置未齐时拒绝，齐全后启用）
        真实对接位：验签(WECHAT_API_V3_KEY AES-256-GCM 解密 resource) → 查订单 → 标记 paid → 发 VIP。
        当前实现保留幂等接口，配置齐全即可上线，无需改前端。"""
        if not _wx_pay_ready():
            return self._json(503, {"ok": False, "error": "微信支付未配置"})
        # TODO(资质到位后)：校验 Wechatpay-Signature 请求头（RSA-SHA256 + 平台证书），
        # 用 WECHAT_API_V3_KEY 对 body.resource 做 AES-256-GCM 解密得到 {out_trade_no, transaction_id, ...}，
        # 调用与 _handle_order_manual_pay 相同的“订单→paid→_grant_vip”原子流程（幂等）。
        return self._json(501, {"ok": False, "error": "微信支付对接位已预留，待配置"})

    def _handle_admin_user_detail(self, data):
        """POST /api/admin/users/detail —— 用户详情页聚合（用户 + VIP + 订单 + 学习记录 + 统计）"""
        err = self._require_admin(data)
        if err:
            return err
        uid = str(data.get("id") or "").strip()
        if not uid:
            return self._json(400, {"ok": False, "error": "缺少用户 id"})
        target = _auth_get_user_by_id(uid)
        if not target:
            return self._json(404, {"ok": False, "error": "用户不存在"})
        target.pop("password_hash", None)

        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, order_no, plan_key, amount_cents, currency, status, pay_channel, trade_no, paid_at, created_at "
                        "FROM orders WHERE user_id=%s ORDER BY created_at DESC LIMIT 20", (uid,))
                    orders = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
                    cur.execute(
                        "SELECT course_id, unit_id, mode, seq_index, unit_index, difficulty, status, ts "
                        "FROM quest_learning_progress WHERE user_id=%s ORDER BY ts DESC LIMIT 50", (uid,))
                    progress = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
                    cur.execute("SELECT COUNT(*) FROM quest_learning_progress WHERE user_id=%s", (uid,))
                    total_records = cur.fetchone()[0] or 0
                    cur.execute("SELECT COUNT(DISTINCT course_id) FROM quest_learning_progress WHERE user_id=%s", (uid,))
                    total_courses = cur.fetchone()[0] or 0
                    cur.execute("SELECT COUNT(DISTINCT unit_id) FROM quest_learning_progress WHERE user_id=%s AND status=1", (uid,))
                    done_units = cur.fetchone()[0] or 0
                return orders, progress, total_records, total_courses, done_units
            finally:
                conn.close()

        try:
            orders, progress, total_records, total_courses, done_units = _q()
        except Exception as e:
            print("[admin] 用户详情查询失败：", e)
            return self._json(500, {"ok": False, "error": "查询详情失败（数据库不可用）"})
        active_days = len({time.strftime("%Y-%m-%d", time.localtime(p["ts"] / 1000)) for p in progress})
        stats = {
            "total_records": total_records,
            "courses": total_courses,
            "done_units": done_units,
            "active_days": active_days,
            "last_ts": progress[0]["ts"] if progress else 0,
        }
        self._log_op(data, "user_detail_view", "user", uid, {"username": target.get("username")})
        return self._json(200, {"ok": True, "user": target, "orders": orders, "progress": progress, "stats": stats})

    # ========== P0 语块化：sentence_segments 存取 + 全局 LLM 缓存 ==========
    def _seg_get_cache(self, cur, sentence_hash, difficulty, with_content=False):
        """查全局缓存。with_content=True 时额外返回 segments/translation。"""
        if with_content:
            cur.execute("SELECT id, review_status, segments, translation FROM sentence_segment_cache WHERE sentence_hash=%s AND difficulty=%s", (sentence_hash, difficulty))
            row = cur.fetchone()
            if not row:
                return None
            return {"id": row[0], "review_status": row[1], "segments": row[2], "translation": row[3]}
        cur.execute("SELECT id, review_status FROM sentence_segment_cache WHERE sentence_hash=%s AND difficulty=%s", (sentence_hash, difficulty))
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "review_status": row[1]}

    def _handle_admin_segments_check(self, data):
        """POST /api/admin/segments/check —— 批量查 LLM 缓存命中（前端先查，未命中才调 AI 切块）"""
        err = self._require_admin(data)
        if err:
            return err
        sentences = data.get("sentences") or []
        if not isinstance(sentences, list) or not sentences:
            return self._json(400, {"ok": False, "error": "缺少 sentences 列表"})
        cached = []
        def _q():
            nonlocal cached
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    for s in sentences:
                        h = str(s.get("sentence_hash") or "").strip()
                        d = str(s.get("difficulty") or "medium").strip()
                        if not h:
                            continue
                        row = self._seg_get_cache(cur, h, d)
                        if row:
                            cached.append({"sentence_hash": h, "difficulty": d,
                                           "cache_id": row["id"], "status": row["review_status"]})
                return cached
            finally:
                conn.close()
        try:
            _seg_execute(_q)
        except Exception as e:
            print("[segments] check 失败：", e)
            return self._json(500, {"ok": False, "error": "缓存查询失败（数据库不可用）"})
        return self._json(200, {"ok": True, "cached": cached})

    def _handle_admin_segments_save(self, data):
        """POST /api/admin/segments/save —— 写语块（upsert，不做整课时 DELETE）：
        - 有 segments：写/升级全局 cache（幂等，translation 仅传入非空时覆盖），再 upsert 引用行
        - 无 segments 且 cache 命中：纯引用（从 cache 取语块写引用行）
        - 无 segments 且无 cache：写占位引用行（cache_id=NULL, review_status='generating'）
        - 组尾部裁剪：只清该句该难度 sort_order>=新组数的旧残余（异步增量互不影响）
        唯一键 uk_seg(course_id,unit_id,sentence_hash,difficulty,sort_order)，逐块 ON DUPLICATE KEY UPDATE。"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        unit_id = str(data.get("unit_id") or "").strip()
        items = data.get("items") or []
        if not course_id or not unit_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id / unit_id"})
        if not isinstance(items, list) or not items:
            return self._json(400, {"ok": False, "error": "缺少 items 列表"})
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    saved = 0
                    now = int(time.time() * 1000)
                    for it in items:
                        h = str(it.get("sentence_hash") or "").strip()
                        d = str(it.get("difficulty") or "medium").strip()
                        if not h:
                            continue
                        status = str(it.get("status") or "ok").strip()
                        if status not in ("ok", "pending", "generating"):
                            status = "ok"
                        segs = it.get("segments") or []
                        translation = str(it.get("translation") or "").strip()
                        row = self._seg_get_cache(cur, h, d, with_content=True)
                        cache_id = None
                        if segs:
                            # 1) 全局 cache upsert（同句同难度只存一份；translation 传入非空才覆盖）
                            cache_id = "segc_" + hashlib.md5((h + "|" + d).encode("utf-8")).hexdigest()[:20]
                            cur.execute(
                                "INSERT INTO sentence_segment_cache (id, sentence_hash, sentence, difficulty, segments, review_status, translation, created_at) "
                                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                                "ON DUPLICATE KEY UPDATE segments=VALUES(segments), review_status=VALUES(review_status), "
                                "translation=IF(VALUES(translation)='', translation, VALUES(translation))",
                                (cache_id, h, str(it.get("sentence") or ""), d,
                                 json.dumps(segs, ensure_ascii=False), status, translation, now))
                            _c = self._seg_get_cache(cur, h, d)
                            if _c:
                                cache_id = _c["id"]
                        elif row:
                            # 2) 纯引用：从全局缓存取语块
                            cache_id = row["id"]
                            try:
                                segs = json.loads(row["segments"] or "[]")
                            except Exception:
                                segs = []
                            status = row["review_status"]
                            translation = row["translation"] or ""
                        # 3) 组尾部裁剪：只清该句该难度 sort_order>=新组数的旧残余
                        cur.execute("DELETE FROM sentence_segments WHERE course_id=%s AND unit_id=%s AND sentence_hash=%s AND difficulty=%s AND sort_order>=%s",
                                    (course_id, unit_id, h, d, len(segs)))
                        if segs:
                            for s in segs:
                                seg_id = "segs_" + hashlib.md5((course_id + "|" + unit_id + "|" + h + "|" + d + "|" + str(s.get("sort_order") or 0)).encode("utf-8")).hexdigest()[:20]
                                cur.execute(
                                    "INSERT INTO sentence_segments (id, course_id, unit_id, cache_id, sentence_hash, difficulty, sort_order, text, type, chinese, review_status, created_at) "
                                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                                    "ON DUPLICATE KEY UPDATE cache_id=VALUES(cache_id), text=VALUES(text), type=VALUES(type), chinese=VALUES(chinese), review_status=VALUES(review_status)",
                                    (seg_id, course_id, unit_id, cache_id, h, d, int(s.get("sort_order") or 0),
                                     str(s.get("text") or ""), str(s.get("type") or "chunk"),
                                     str(s.get("chinese") or ""), status, now))
                            saved += 1
                        else:
                            # 4) 占位行（未生成）：cache_id=NULL, review_status='generating'；upsert 幂等
                            seg_id = "segs_" + hashlib.md5((course_id + "|" + unit_id + "|" + h + "|" + d + "|0").encode("utf-8")).hexdigest()[:20]
                            cur.execute(
                                "INSERT INTO sentence_segments (id, course_id, unit_id, cache_id, sentence_hash, difficulty, sort_order, text, type, chinese, review_status, created_at) "
                                "VALUES (%s,%s,%s,NULL,%s,%s,0,'','pending_placeholder','','generating',%s) "
                                "ON DUPLICATE KEY UPDATE cache_id=NULL, text='', type='pending_placeholder', review_status='generating'",
                                (seg_id, course_id, unit_id, h, d, now))
                            saved += 1
                    conn.commit()
                    return saved
            finally:
                conn.close()
        try:
            saved = _seg_execute(_q)
            return self._json(200, {"ok": True, "saved": saved})
        except Exception as e:
            print("[segments] save 失败：", e)
            return self._json(500, {"ok": False, "error": "保存语块失败（数据库不可用）"})

    def _handle_admin_segments_update(self, data):
        """POST /api/admin/segments/update —— P4 人工编辑语块（单句单档整组覆盖）：
        - 保存前硬校验：按 sort_order 拼接必须逐字符等于基准原句（俄语化），否则 400 并回显拼接结果
        - 校验通过 → 同一事务：覆盖该 (句,档) 全部引用行 + 同步覆盖全局 cache.segments
          （同步 cache：补跑幂等命中返回编辑后语块，人工修改不会被重跑冲掉；同句跨课时切分全局一致）
        - review_status 置 'ok'（人工确认过），translation 不动
        - 数据库 0 改动（全部写现有列）"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        unit_id = str(data.get("unit_id") or "").strip()
        h = str(data.get("sentence_hash") or "").strip()
        d = str(data.get("difficulty") or "medium").strip()
        segs = data.get("segments") or []
        if not course_id or not unit_id or not h:
            return self._json(400, {"ok": False, "error": "缺少 course_id / unit_id / sentence_hash"})
        if not isinstance(segs, list) or not segs:
            return self._json(400, {"ok": False, "error": "缺少 segments 列表"})
        try:
            ordered = sorted(segs, key=lambda s: int(s.get("sort_order") or 0))
            joined = " ".join(str(s.get("text") or "").strip() for s in ordered if str(s.get("text") or "").strip())
        except Exception:
            return self._json(400, {"ok": False, "error": "segments 结构无效"})
        if not joined:
            return self._json(400, {"ok": False, "error": "语块文本为空"})
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    # 1) 基准原句：优先全局 cache.sentence（俄语化原句）；无 cache 时用现有引用行拼接（编辑前==原句）
                    cache_row = self._seg_get_cache(cur, h, d, with_content=True)
                    baseline = (cache_row or {}).get("sentence") or ""
                    if not baseline:
                        cur.execute("SELECT text FROM sentence_segments WHERE course_id=%s AND unit_id=%s AND sentence_hash=%s AND difficulty=%s AND text<>'' AND type<>'pending_placeholder' ORDER BY sort_order",
                                    (course_id, unit_id, h, d))
                        baseline = " ".join(r[0] for r in cur.fetchall())
                    baseline = (baseline or "").strip()
                    if not baseline:
                        return ("NO_BASELINE",)
                    # 2) 硬校验：拼接 == 基准原句（逐字符）
                    if joined != baseline:
                        return ("MISMATCH", joined, baseline)
                    # 3) 覆盖引用行 + 同步覆盖全局 cache（同一事务）
                    now = int(time.time() * 1000)
                    cache_id = None
                    if cache_row and cache_row.get("id"):
                        cache_id = cache_row["id"]
                    else:
                        cache_id = "segc_" + hashlib.md5((h + "|" + d).encode("utf-8")).hexdigest()[:20]
                    cur.execute(
                        "INSERT INTO sentence_segment_cache (id, sentence_hash, sentence, difficulty, segments, review_status, translation, created_at) "
                        "VALUES (%s,%s,%s,%s,%s,'ok','',%s) "
                        "ON DUPLICATE KEY UPDATE segments=VALUES(segments), review_status='ok', "
                        "translation=IF(translation='', '', translation)",
                        (cache_id, h, baseline, d, json.dumps(ordered, ensure_ascii=False), now))
                    cur.execute("DELETE FROM sentence_segments WHERE course_id=%s AND unit_id=%s AND sentence_hash=%s AND difficulty=%s",
                                (course_id, unit_id, h, d))
                    for s in ordered:
                        seg_id = "segs_" + hashlib.md5((course_id + "|" + unit_id + "|" + h + "|" + d + "|" + str(s.get("sort_order") or 0)).encode("utf-8")).hexdigest()[:20]
                        cur.execute(
                            "INSERT INTO sentence_segments (id, course_id, unit_id, cache_id, sentence_hash, difficulty, sort_order, text, type, chinese, review_status, created_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ok',%s)",
                            (seg_id, course_id, unit_id, cache_id, h, d, int(s.get("sort_order") or 0),
                             str(s.get("text") or ""), str(s.get("type") or "chunk"), str(s.get("chinese") or ""), now))
                    conn.commit()
                    return ("OK", len(ordered))
            finally:
                conn.close()
        try:
            r = _seg_execute(_q)
            if r[0] == "NO_BASELINE":
                return self._json(400, {"ok": False, "error": "找不到基准原句（该句尚无语块，请先补跑生成）"})
            if r[0] == "MISMATCH":
                return self._json(400, {"ok": False, "error": "拼接校验失败：编辑后语块必须逐字符等于原句", "joined": r[1], "baseline": r[2]})
            return self._json(200, {"ok": True, "updated": r[1]})
        except Exception as e:
            print("[segments] update 失败：", e)
            return self._json(500, {"ok": False, "error": "更新语块失败（数据库不可用）"})

    def _handle_admin_segments_delete(self, data):
        """POST /api/admin/segments/delete —— 删课程/课时语块（同一事务内删除；全局 cache 保留）"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        unit_id = str(data.get("unit_id") or "").strip()
        if not course_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id"})
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    if unit_id:
                        cur.execute("DELETE FROM sentence_segments WHERE course_id=%s AND unit_id=%s", (course_id, unit_id))
                        cur.execute("DELETE FROM sentence_slot_unit_tables WHERE course_id=%s AND unit_id=%s", (course_id, unit_id))
                    else:
                        cur.execute("DELETE FROM sentence_segments WHERE course_id=%s", (course_id,))
                        cur.execute("DELETE FROM sentence_slot_unit_tables WHERE course_id=%s", (course_id,))
                    deleted = cur.rowcount
                    conn.commit()
                    return deleted
            finally:
                conn.close()
        try:
            deleted = _seg_execute(_q)
            return self._json(200, {"ok": True, "deleted": deleted})
        except Exception as e:
            print("[segments] delete 失败：", e)
            return self._json(500, {"ok": False, "error": "删除语块失败（数据库不可用）"})

    def _handle_admin_segments_pending(self, data):
        """POST /api/admin/segments/pending —— 该课时待处理句子（后台筛选用）。
        body.status 可选：pending（默认）/ generating / all。对外字段统一 status。"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        unit_id = str(data.get("unit_id") or "").strip()
        if not course_id or not unit_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id / unit_id"})
        req_status = str(data.get("status") or "pending").strip()
        if req_status not in ("pending", "generating", "all"):
            req_status = "pending"
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    if req_status == "all":
                        cur.execute("SELECT DISTINCT sentence_hash, difficulty, review_status FROM sentence_segments WHERE course_id=%s AND unit_id=%s", (course_id, unit_id))
                    else:
                        cur.execute("SELECT DISTINCT sentence_hash, difficulty, review_status FROM sentence_segments WHERE course_id=%s AND unit_id=%s AND review_status=%s", (course_id, unit_id, req_status))
                    rows = cur.fetchall()
                    return [{"sentence_hash": r[0], "difficulty": r[1], "status": r[2]} for r in rows]
            finally:
                conn.close()
        try:
            pending = _seg_execute(_q)
        except Exception as e:
            print("[segments] pending 查询失败：", e)
            return self._json(500, {"ok": False, "error": "查询失败（数据库不可用）"})
        return self._json(200, {"ok": True, "pending": pending})

    # ---------- P1：llm-segment（后端持 key，AI 只做分组决策） ----------
    def _seg_build_prompt(self, tokens, difficulty):
        lines = [
            "你是俄语教学\u201c语块切分\u201d助手。你只做分组决策，绝不输出俄语或中文的句子文本。只输出 JSON，不要任何解释或 markdown 包裹。",
            "",
            "【任务】把 token 列表按教学语义分成连续的\u201c语块\u201d，供连词成句练习。",
            "【token 列表】（编号从 0 开始，已俄语化）",
        ]
        for i, t in enumerate(tokens):
            lines.append("%d: %s" % (i, t))
        lines.append("")
        lines.append("【铁律】")
        lines.append("1. 只能引用上面的编号；每组 indexes 必须连续递增（如 [0,1]、[2]、[3,4]）。")
        lines.append("2. 所有组并集必须恰好覆盖全部编号：不重、不漏、不跳号。")
        if difficulty == "easy":
            lines.append("3. 难度【初级·零件模式】：鼓励拆到最小可独立成组的教学零件——代词、名词、动词变位、副词、形容词等【允许单字成组】；")
            lines.append("   只要不是固定搭配或专名（如 Чистые пруды / в университете / на втором этаже），能拆就拆，不要为了完整合并成多词短语。")
        elif difficulty == "hard":
            lines.append("3. 难度【高级】：整句作为一组（该档正常不请求 AI）。")
        else:
            lines.append("3. 难度【中级·语块模式】：【禁止任何单字成组】！最小单元必须是 2 词以上的短语/语块（主谓短语、介词短语、固定搭配、从句片段）；")
            lines.append("   单字必须并入相邻语块，不允许孤词独立成组。")
        lines.append("4. 固定搭配/专名必须整组：в университете / на втором этаже 等，禁止拆碎。")
        lines.append("5. 标点必须附着在所在组的最后一个 token 上，禁止标点单独成组。")
        lines.append("6. 每组给出 type（word/phrase/verb/prep_phrase/fixed/clause）与 chinese（只译该语块本身）。")
        lines.append("7. translation = 整句中文，必须符合现代中文语序，禁止俄式硬译（例：Я люблю книгу → \u201c我爱书\u201d，不是\u201c我书爱\u201d）。")
        lines.append("8. chinese/type/translation 无法确定时允许省略或留空，绝不编造。")
        lines.append("")
        lines.append("【输出格式】严格 JSON：")
        lines.append('{"segments":[{"indexes":[0,1],"type":"phrase","chinese":"我将"},{"indexes":[2],"type":"verb","chinese":"学习"}],"translation":"我将要学习。"}')
        lines.append("只输出 JSON。")
        return "\n".join(lines)

    def _seg_verify_indexes(self, groups, n):
        """索引校验：并集=0..n-1 不重不漏 + 每组 indexes 连续。按首索引升序重排后返回，非法返回 None。"""
        if not isinstance(groups, list) or not groups:
            return None
        seen = set()
        for g in groups:
            idx = g.get("indexes")
            if not isinstance(idx, list) or not idx:
                return None
            for i in idx:
                if not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= n or i in seen:
                    return None
                seen.add(i)
            for a, b in zip(idx, idx[1:]):
                if b != a + 1:
                    return None
        if seen != set(range(n)):
            return None
        return sorted(groups, key=lambda g: g["indexes"][0])

    def _seg_repair_missing_indexes(self, groups, n):
        """漏索引自动修复：结构合法但并集缺索引时，把缺失索引并入相邻组（优先前组末尾，其次后组开头），保持组内连续。
        只处理\u201c漏\u201d——其他非法（重复/越界/组内不连续）返回 None，交回原 fallback 链路。"""
        if not isinstance(groups, list) or not groups:
            return None
        seen = set()
        for g in groups:
            idx = g.get("indexes")
            if not isinstance(idx, list) or not idx:
                return None
            prev = -1
            for i in idx:
                if not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= n or i in seen:
                    return None
                if prev >= 0 and i != prev + 1:
                    return None  # 组内不连续——非\u201c漏\u201d，不修
                seen.add(i)
                prev = i
        miss = sorted(set(range(n)) - seen)
        if not miss:
            return groups
        for i in miss:
            fixed = False
            for g in groups:  # 优先并入前组末尾（语义更完整）
                gi = g["indexes"]
                if gi[-1] + 1 == i:
                    gi.append(i)
                    fixed = True
                    break
            if not fixed:
                for g in groups:  # 其次插到后组开头
                    gi = g["indexes"]
                    if gi[0] - 1 == i:
                        gi.insert(0, i)
                        fixed = True
                        break
            if not fixed:
                return None
        return groups

    def _handle_admin_segments_llm_segment(self, data):
        """POST /api/admin/segments/llm-segment —— AI 切块（后端持 key，前端只传数据）。
        幂等：cache ok → 直接返回缓存（文本组，cached）；cache generating → {pending:true}；
        未命中/cache pending → 调 LLM → 索引+拼接校验 → 写 cache ok → 返回索引组。
        校验失败/AI 失败 → {fallback:true}（前端走机械兜底）。"""
        err = self._require_admin(data)
        if err:
            return err
        sentence_hash = str(data.get("sentence_hash") or "").strip()
        russian_text = str(data.get("russian_text") or "").strip()
        tokens = data.get("tokens") or []
        difficulty = str(data.get("difficulty") or "medium").strip()
        if not sentence_hash or not russian_text or not isinstance(tokens, list) or not tokens:
            return self._json(400, {"ok": False, "error": "缺少 sentence_hash / russian_text / tokens"})
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"
        n = len(tokens)
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    row = self._seg_get_cache(cur, sentence_hash, difficulty, with_content=True)
                    if row and row["review_status"] == "ok":
                        try:
                            segs = json.loads(row["segments"] or "[]")
                        except Exception:
                            segs = []
                        return {"cached": True, "segments": segs, "translation": row["translation"] or ""}
                    if row and row["review_status"] == "generating":
                        return {"pending": True}
                    return {"cached": False}
            finally:
                conn.close()
        try:
            r = _seg_execute(_q)
        except Exception as e:
            print("[segments] llm-segment 缓存查询失败：", e)
            return self._json(500, {"ok": False, "error": "缓存查询失败（数据库不可用）"})
        if r.get("cached"):
            return self._json(200, {"ok": True, "cached": True, "segments": r["segments"], "translation": r["translation"]})
        if r.get("pending"):
            return self._json(200, {"ok": False, "pending": True})
        # 未命中 / cache pending：调 LLM
        obj = call_llm(self._seg_build_prompt(tokens, difficulty), "", json_mode=True)
        if not obj:
            return self._json(200, {"ok": False, "fallback": True, "reason": "ai_none"})
        groups = obj.get("segments")
        translation = str(obj.get("translation") or "").strip()
        raw_groups = groups
        groups = self._seg_verify_indexes(raw_groups, n)
        if groups is None:
            # 自动修复：AI 偶发漏索引 → 并入相邻组后重验；仍非法才 fallback
            repaired = self._seg_repair_missing_indexes(raw_groups, n)
            if repaired is not None:
                re_checked = self._seg_verify_indexes(repaired, n)
                if re_checked is not None:
                    print("[segments] llm-segment 漏索引自动修复成功 tokens=%d 原始返回=%s" % (n, json.dumps(obj, ensure_ascii=False)[:400]))
                    groups = re_checked
                else:
                    groups = None
            else:
                groups = None
        if groups is None:
            print("[segments] llm-segment 索引校验失败 tokens=%d 原始返回=%s" % (n, json.dumps(obj, ensure_ascii=False)[:800]))
            return self._json(200, {"ok": False, "fallback": True, "reason": "indexes_invalid", "raw": json.dumps(obj, ensure_ascii=False)[:500]})
        # 拼接校验（机械截取 == russian_text）
        try:
            full = " ".join(" ".join(tokens[i] for i in g["indexes"]) for g in groups)
        except Exception:
            full = ""
        if full != russian_text:
            print("[segments] llm-segment 拼接校验失败：", repr(full), "!=", repr(russian_text))
            return self._json(200, {"ok": False, "fallback": True, "reason": "concat_mismatch", "full": repr(full)[:300], "expected": repr(russian_text)[:300]})
        # 写全局 cache（ok；translation 非空才覆盖）
        now = int(time.time() * 1000)
        cache_id = "segc_" + hashlib.md5((sentence_hash + "|" + difficulty).encode("utf-8")).hexdigest()[:20]
        segs_for_cache = [{"sort_order": i, "text": " ".join(tokens[ix] for ix in g["indexes"]),
                           "type": g.get("type") or "chunk", "chinese": g.get("chinese") or ""}
                          for i, g in enumerate(groups)]
        def _w():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO sentence_segment_cache (id, sentence_hash, sentence, difficulty, segments, review_status, translation, created_at) "
                        "VALUES (%s,%s,%s,%s,%s,'ok',%s,%s) "
                        "ON DUPLICATE KEY UPDATE segments=VALUES(segments), review_status='ok', "
                        "translation=IF(VALUES(translation)='', translation, VALUES(translation))",
                        (cache_id, sentence_hash, russian_text, difficulty, json.dumps(segs_for_cache, ensure_ascii=False), translation, now))
                    conn.commit()
            finally:
                conn.close()
        try:
            _seg_execute(_w)
        except Exception as e:
            print("[segments] llm-segment 写缓存失败：", e)
        # 返回索引组（前端机械截取 + verifySegments 双保险）
        return self._json(200, {"ok": True, "segments": groups, "translation": translation})

    # ---------- P4：句乐部式滚雪球规划（AI 出增量词序列，电脑拼 target） ----------
    def _slot_build_prompt(self, tokens, difficulty, russian_text, pool=None):
        lines = [
            "你是俄语教学\u201c句乐部式滚雪球\u201d规划师。你输出\u201c教学块序列\u201d（块模式：系统直接显示每步 add 作为 russian，不做累加）。只输出 JSON，不要任何解释或 markdown 包裹。",
            "",
            "【目标句】（已俄语化，系统最终校验每组最后一步必须逐字符等于对应的完整句）：",
            russian_text,
            "",
            "【token 列表】（编号从 0 开始，仅作参考）：",
        ]
        for i, t in enumerate(tokens):
            lines.append("%d: %s" % (i, t))
        if isinstance(pool, dict):
            lines.append("")
            lines.append("【本课变体词池】（【变体组的 add 只能从这里取】，禁止新造词；骨架组仍用目标句的原文词）：")
            for key, zh_label in (("negation", "否定"), ("time", "时间"), ("predicates", "谓语"),
                                  ("objects", "补语"), ("evaluation", "评价形容词"), ("degree", "程度副词"),
                                  ("preposition", "介词短语"), ("connector", "连词"), ("place", "地点")):
                items = pool.get(key)
                if isinstance(items, list) and items:
                    shown = " / ".join(
                        ("%s(%s)" % (str(it.get("ru") or it.get("word") or "").strip(), str(it.get("zh") or "").strip()))
                        for it in items if isinstance(it, dict) and str(it.get("ru") or it.get("word") or "").strip())
                    if shown:
                        lines.append("  [%s] %s" % (zh_label, shown))
        lines.append("")
        lines.append("【输出格式】groups = 教学组序列，每组 = 一条滚雪球路径：")
        lines.append('{"groups":[{"title":"骨架","steps":[{"add":"Это","zh":"这","type":"pronoun"},{"add":"мой","zh":"我的","type":"adj"},{"add":"Это мой друг","zh":"这是我的朋友","type":"sentence"}]},{"title":"否定","steps":[{"add":"не","zh":"不","type":"neg"},{"add":"мой друг","zh":"我的朋友","type":"chunk"},{"add":"Это не мой друг","zh":"这不是我的朋友","type":"sentence"}]}],"translation":"这是我的朋友"}')
        lines.append("")
        lines.append("【当前难度（决定块粒度，必须遵守）】%s" % difficulty)
        lines.append("【难度粒度规则】")
        lines.append("- easy（初级）：允许单字成组；固定搭配整体一组；骨架按教学节奏逐步拆到单词/短语级（对齐句乐部 01-05：I → like → I like → the food → I like the food）。")
        lines.append("- medium（中级）：禁止单字成组，最小教学块是短语/语块（至少 2 个词）；骨架块数比 easy 少。")
        lines.append("- hard（高级）：不拆块，整句一组——骨架组直接 1 步 = 完整句；变体组也尽量一步 = 完整变体句（如否定 = «Это не мой друг» 一步）。")
        lines.append("")
        lines.append("【铁律】")
        lines.append("1. add = 这一步\u201c新建立的教学块\u201d（词 / 短语组合 / 完整句）。不允许为空。")
        lines.append("2. 块模式：系统直接显示 add 作为 russian。每组从\u201c新块单出\u201d开始逐步组合更大的块，**每组最后一步 add 必须是完整句**（句乐部：don't → like → don't like → I don't like the food）。")
        lines.append("3. 第1组必须是【骨架组】：add 序列覆盖目标句全部内容，系统拼接后【最后一步必须逐字符等于目标句】。")
        lines.append("4. 骨架组节奏：主语/指示词单出 → 谓语单出 → 主谓组合 → 补语块单出（介词短语/不定式短语先组合成块）→ 最后拼出完整句。每步只加一个\u201c教学零件\u201d。")
        lines.append("5. 后续组 = 变体组。变体类型【只能从以下 9 类白名单选择】，且【必须按该类固定节奏出步】——你只负责填词，禁止自己改步数节奏：")
        lines.append("   [1 否定]（4步）не 单出 → 原句其余成分成块单出 → 组合（не+成块）→ 完整否定句")
        lines.append("   [2 时间状语]（3步）时间词单出（завтра）→ 完整句+追加时间 → 否定完整句+追加时间")
        lines.append("   [3 换谓语]（5步）新谓语单出（должен）→ 原句补语/不定式单出 → 完整肯定句（**整句重写**）→ 否定组合（не+新谓语）→ 完整否定句（**整句重写**）")
        lines.append("   [4 换补语]（3-4步）新补语单出 → 与已有动词组合成块 → 完整肯定句（**整句重写**）→（可选）完整否定句")
        lines.append("   [5 评价句]（3-4步）это 单出 → это+形容词（это хорошо）→ 扩展词追加（очень/для меня）→ 完整评价句（**整句重写**）")
        lines.append("   [6 程度副词]（2步）程度词单出（очень）→ 完整评价句+程度词")
        lines.append("   [7 介词短语]（2步）短语单出（для меня）→ 完整句+短语")
        lines.append("   [8 复合句]（3步）连词单出（поэтому）→ 完整句A → 完整句A+连词+完整句B（**整句重写**）")
        lines.append("   [9 地点]（3步）地点词单出（здесь）→ 组合（动词+地点）→ 完整句")
        lines.append("6. 节奏铁律：每组的【第1步永远是单出新词/新块】；【能组合的先组合成块再拼完整句】；【完整句只能在每组最后一步】；【肯定句后尽量跟否定句（配对；状语类除外）】；全程复用已学词块，禁止重复引入。")
        lines.append("7. 【变体组硬规则——最重要】")
        lines.append("   a. 变体组最后一步 = 语法完全正确、语义自然通顺的完整俄语句子。")
        lines.append("   b. 【换谓语/换补语/评价句/复合句】必须【整体重写句子结构】：在目标句语义基础上重新组织词序（例：目标句 «Это мой друг» 换谓语 → «Я вижу своего друга»；评价句 → «Это очень хороший друг»；换补语 → «Это мой друг в Москве»）。**禁止把新词硬塞进原句的语序**（禁止 «Это мой друг вижу» 这种词序错乱）。")
        lines.append("   c. 【否定/时间/地点】在原句框架内最小改动：否定插到系词/谓语后（«Это не мой друг»）、状语追加到句尾（«Это мой друг сегодня»），保持原句语序。")
        lines.append("   d. 变体组末步【禁止与骨架末步相同】（不能重复原句）。")
        lines.append("   e. 每个变体句都是**新句子**，允许增减词、改变词序，只要语义是目标句的自然变形。")
        lines.append("8. 【中文翻译硬规则】")
        lines.append("   a. 每步 zh = 该步 add 俄语的【准确中文翻译】，禁止照抄别的步骤的翻译。")
        lines.append("   b. **translation 只用于骨架组（第1组）末步的 zh**；【所有变体组末步的 zh 必须与 translation 不同】，必须反映该变体的语义：否定句翻\u201c不\u201d、时间句翻时间词、换谓语句翻新动词。")
        lines.append("   c. 例子：translation=「这是我的朋友」；否定组末步 zh 必须是「这不是我的朋友」，不能还是「这是我的朋友」；换谓语组末步 zh 必须是「我看见我的朋友」。")
        lines.append("   d. 实在无法准确翻译某步时，zh 允许留空，但【禁止把其他句子的中文填进来】。")
        lines.append("9. 每组 title 用中文简短说明（骨架 / 否定 / 加时间 / 换谓语 / 换补语 / 评价句 / 程度 / 介词 / 复合句 / 地点）。")
        lines.append("10. 每句 3-6 组为宜（骨架 + 2-4 个变体，从白名单挑 2-4 类），不要超过 8 组；变体类型尽量不重复。")
        return "\n".join(lines)

    def _slot_verify_and_build(self, obj, russian_text, tokens, difficulty):
        """校验 + 拼装：第1组（骨架）拼接必须逐字符 == 目标句；返回拼好的 groups（每步含 russian/target）。
        非法返回 (None, reason)。"""
        if not isinstance(obj, dict):
            return None, "not_dict"
        groups = obj.get("groups")
        if not isinstance(groups, list) or not groups:
            return None, "no_groups"
        built = []
        for gi, g in enumerate(groups):
            steps = g.get("steps")
            if not isinstance(steps, list) or not steps:
                return None, "group_%d_no_steps" % gi
            acc = ""
            built_steps = []
            for si, st in enumerate(steps):
                add = str(st.get("add") or "").strip()
                if not add:
                    return None, "group_%d_step_%d_empty_add" % (gi, si)
                # 块模式（对齐句乐部）：add = 该步的教学块（词/短语/完整句），系统直接显示，不做累加
                built_steps.append({
                    "add": add,
                    "russian": add,
                    "zh": str(st.get("zh") or "").strip(),
                    "type": str(st.get("type") or "chunk").strip(),
                })
            built.append({"title": str(g.get("title") or "组%d" % (gi + 1)).strip(),
                          "steps": built_steps,
                          "final": built_steps[-1]["russian"]})
        # 强校验：骨架组（第1组）末步块 == 目标句（俄语化压缩空白后）——句乐部机制：末步 add = 完整句
        if built[0]["final"] != russian_text:
            return None, "skeleton_concat_mismatch"
        # 变体组强校验（Prompt v3.1 配套）：末步不能重复原句；末步中文不能照抄 translation（AI 常犯）
        translation = str(obj.get("translation") or "").strip()
        skeleton_final = built[0]["final"]
        for gi in range(1, len(built)):
            final = built[gi]["final"]
            if final == skeleton_final:
                return None, "variant_dup_sentence"
            last_zh = str(built[gi]["steps"][-1].get("zh") or "").strip()
            if not last_zh:
                return None, "variant_zh_empty"
            if translation and last_zh == translation:
                return None, "variant_zh_same"
        return built, None

    def _handle_admin_segments_plan(self, data):
        """POST /api/admin/segments/plan —— 句乐部式滚雪球规划（AI 出增量词序列，后端拼 target 强校验）。
        幂等：cache ok → 返回缓存；未命中 → 调 LLM → 校验（骨架拼接==原句）→ 写 cache。
        失败 → {fallback:true} 携带 reason。"""
        err = self._require_admin(data)
        if err:
            return err
        sentence_hash = str(data.get("sentence_hash") or "").strip()
        russian_text = str(data.get("russian_text") or "").strip()
        tokens = data.get("tokens") or []
        difficulty = str(data.get("difficulty") or "medium").strip()
        pool = data.get("pool")
        if not isinstance(pool, dict):
            pool = None
        pool_fp = ""
        if pool:
            try:
                pool_fp = hashlib.md5(json.dumps(pool, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
            except Exception:
                pool_fp = ""
        if not sentence_hash or not russian_text or not isinstance(tokens, list) or not tokens:
            return self._json(400, {"ok": False, "error": "缺少 sentence_hash / russian_text / tokens"})
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT plan, review_status, COALESCE(pool_fp,''), COALESCE(prompt_v,'v2') FROM sentence_slot_plans WHERE sentence_hash=%s AND difficulty=%s",
                                (sentence_hash, difficulty))
                    row = cur.fetchone()
                    if row:
                        return {"plan": row[0], "status": row[1], "pool_fp": row[2], "prompt_v": row[3]}
                    return {"plan": None, "status": None, "pool_fp": "", "prompt_v": ""}
            finally:
                conn.close()
        try:
            r = _seg_execute(_q)
        except Exception as e:
            print("[slots] plan 缓存查询失败：", e)
            return self._json(500, {"ok": False, "error": "缓存查询失败（数据库不可用）"})
        # 缓存命中条件：plan 存在 + 词池指纹一致 + Prompt 版本一致（Prompt 升级后旧缓存自动失效）
        if r.get("plan") and r.get("pool_fp") == pool_fp and r.get("prompt_v") == PLAN_PROMPT_V:
            try:
                cached = json.loads(r["plan"])
                groups = cached.get("groups")
                # 老缓存可能是重组前的 AI 原样 → 命中后仍做难度重组，保证三档粒度（无需等 AI 重生成）
                if groups:
                    groups = self._slot_apply_difficulty(groups, difficulty, russian_text, str(cached.get("translation") or "").strip())
                return self._json(200, {"ok": True, "cached": True, "groups": groups, "translation": cached.get("translation") or ""})
            except Exception:
                pass
        # 校验失败重试策略：AI 一次不听话（变体中文照抄/硬塞词）→ 重试 1 次；仍失败才 fallback
        obj = None
        built = None
        reason = ""
        for _attempt in range(2):
            obj = call_llm(self._slot_build_prompt(tokens, difficulty, russian_text, pool), "", json_mode=True)
            if not obj:
                return self._json(200, {"ok": False, "fallback": True, "reason": "ai_none"})
            built, reason = self._slot_verify_and_build(obj, russian_text, tokens, difficulty)
            if built is not None:
                break
            print("[slots] plan 校验失败(第%d次) reason=%s tokens=%d 原始返回=%s" % (_attempt + 1, reason, len(tokens), json.dumps(obj, ensure_ascii=False)[:400]))
        if built is None:
            return self._json(200, {"ok": False, "fallback": True, "reason": reason, "raw": json.dumps(obj, ensure_ascii=False)[:500]})
        translation = str(obj.get("translation") or "").strip()
        # 难度粒度确定性重组（不依赖 AI 自觉）：骨架组按难度重排，变体组保持 AI 原样
        built = self._slot_apply_difficulty(built, difficulty, russian_text, translation)
        plan_json = json.dumps({"groups": built, "translation": translation}, ensure_ascii=False)
        def _w():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    pid = "slot_" + hashlib.md5((sentence_hash + "|" + difficulty).encode("utf-8")).hexdigest()[:20]
                    cur.execute(
                        "INSERT INTO sentence_slot_plans (id, sentence_hash, difficulty, sentence, plan, review_status, created_at, pool_fp, prompt_v) "
                        "VALUES (%s,%s,%s,%s,%s,'ok',%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE plan=VALUES(plan), review_status='ok', pool_fp=VALUES(pool_fp), prompt_v=VALUES(prompt_v)",
                        (pid, sentence_hash, difficulty, russian_text, plan_json, int(time.time() * 1000), pool_fp, PLAN_PROMPT_V))
                    conn.commit()
            finally:
                conn.close()
        try:
            _seg_execute(_w)
        except Exception as e:
            print("[slots] plan 写缓存失败：", e)
        return self._json(200, {"ok": True, "groups": built, "translation": translation})

    # ---------- P4-B：难度粒度确定性重组（骨架组按难度重排；变体组保持 AI 原样） ----------
    def _slot_apply_difficulty(self, built, difficulty, russian_text, translation):
        """句乐部三档粒度（对齐用户定案：初级=词+短语 / 中级=短语+语块 / 高级=整句不拆）。
        easy   骨架 = 逐词出（Это → мой → друг → 完整句）
        medium 骨架 = 前2词合成短语块 + AI 其余中间块 + 完整句（Это мой → друг → 完整句）
        hard   骨架 = 完整句一步
        变体组保持 AI 生成的节奏（结构本身已含完整句与组合块）。"""
        if not built:
            return built
        words = [w for w in russian_text.split(" ") if w]
        sk_steps = built[0].get("steps") or []
        zh_by_word = {}
        zh_by_block = {}
        for s in sk_steps:
            txt = str(s.get("russian") or s.get("add") or "").strip()
            if not txt:
                continue
            zh = str(s.get("zh") or "").strip()
            if " " not in txt:
                zh_by_word[txt] = zh
            else:
                zh_by_block[txt] = zh
        def _combo_zh(w1, w2):
            z1, z2 = zh_by_word.get(w1, ""), zh_by_word.get(w2, "")
            if not z1 and not z2:
                return ""
            # 俄语零系词结构：Это/не 开头 → 插"是"（这是/不是）
            p1 = (z1 + "是") if w1 in ("Это", "не") else z1
            return (p1 + z2).strip()
        out = []
        for gi, g in enumerate(built):
            if gi != 0:
                out.append(g)
                continue
            new_steps = []
            if difficulty == "hard":
                new_steps.append({"add": russian_text, "russian": russian_text, "zh": translation, "type": "sentence"})
            elif difficulty == "medium":
                w1, w2 = words[0], words[1]
                combo_txt = w1 + " " + w2
                combo_zh = zh_by_block.get(combo_txt) or _combo_zh(w1, w2)
                new_steps.append({"add": combo_txt, "russian": combo_txt, "zh": combo_zh, "type": "comb"})
                for s in sk_steps:
                    txt = str(s.get("russian") or s.get("add") or "").strip()
                    if not txt or txt == russian_text:
                        continue
                    toks = txt.split(" ")
                    if all(t in (w1, w2) for t in toks):
                        continue
                    new_steps.append({"add": txt, "russian": txt, "zh": str(s.get("zh") or "").strip(), "type": "comb"})
                new_steps.append({"add": russian_text, "russian": russian_text, "zh": translation, "type": "sentence"})
            else:  # easy：保留 AI 生成的骨架（词+短语混合，对齐用户定案"初级=词+短语"）
                out.append(g)
                continue
            out.append({"title": g.get("title") or "骨架", "steps": new_steps})
        return out

    # ---------- P4：课程级变体词池（9 类各 2-4 词，整课生成一次，全课变体复用） ----------
    _POOL_KEYS = (("negation", "否定词"), ("time", "时间词"), ("predicates", "谓语（变位形式）"),
                  ("objects", "补语/不定式短语"), ("evaluation", "评价形容词"), ("degree", "程度副词"),
                  ("preposition", "介词短语"), ("connector", "连词"), ("place", "地点词"))
    def _pool_build_prompt(self, sentences):
        lines = [
            "你是俄语教学词池设计师。为下面这一课的句子设计【课程级变体词池】——句乐部式教学会在全课反复使用同一批变体词。只输出 JSON，不要解释。",
            "",
            "【本课句子】（用于判断教学阶段与难度，决定词池词汇量）：",
        ]
        for i, s in enumerate(sentences[:12]):
            lines.append("%d. %s" % (i + 1, str(s.get("ru") or s.get("russian") or s.get("text") or "").strip()))
        lines.append("")
        lines.append("【输出格式】9 类词池，每类 2-4 个词（词条= {ru: 俄语可用形式, zh: 中文}）：")
        lines.append('{"negation":[{"ru":"не","zh":"不"}],"time":[{"ru":"сейчас","zh":"现在"}],"predicates":[{"ru":"хочу","zh":"想"}],"objects":[{"ru":"делать это","zh":"做这个"}],"evaluation":[{"ru":"важно","zh":"重要"}],"degree":[{"ru":"очень","zh":"非常"}],"preposition":[{"ru":"для меня","zh":"对我来说"}],"connector":[{"ru":"поэтому","zh":"所以"}],"place":[{"ru":"здесь","zh":"这里"}]}')
        lines.append("")
        lines.append("【铁律】")
        lines.append("1. 9 类都要有，每类 2-4 个词，不允许空类。")
        lines.append("2. 词必须是【可用形式】：谓语用变位形式（хочу / должен / нужно / люблю）、名词补语用正确格（еду / книгу）。")
        lines.append("3. 难度贴合本课句子：初级课给高频简单词（сейчас / сегодня / здесь），不要给冷僻词。")
        lines.append("4. 词与词之间教学上是同一难度梯队，不要混入太难的词。")
        lines.append("5. zh 用现代中文，逐词对应，不要整句翻译。")
        lines.append("6. 禁止编造俄语词形；拿不准就留空该条，但不许整类为空。")
        lines.append("7. 【时间词专规】time 类必须是【时间点/时间段名词】：сегодня（今天）/ завтра（明天）/ вчера（昨天）/ сейчас（现在）/ утром（早上）/ вечером（晚上）/ на этой неделе（本周）。【严禁】方式副词：поздно（晚）/ рано（早）/ быстро（快）/ медленно（慢）——这些是修饰动作方式的，不是时间。")
        return "\n".join(lines)

    def _pool_verify(self, obj):
        """校验词池：9 类全是非空数组、词条含 ru；返回规范后的 pool 或 (None, reason)。"""
        if not isinstance(obj, dict):
            return None, "not_dict"
        pool = {}
        for key, label in self._POOL_KEYS:
            items = obj.get(key)
            if not isinstance(items, list):
                return None, "missing_%s" % key
            cleaned = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                ru = str(it.get("ru") or it.get("word") or "").strip()
                if not ru:
                    continue
                cleaned.append({"ru": ru, "zh": str(it.get("zh") or "").strip()})
            if not cleaned:
                return None, "empty_%s" % key
            pool[key] = cleaned[:6]
        return pool, None

    def _handle_admin_segments_pool(self, data):
        """POST /api/admin/segments/pool —— 课程级变体词池生成（整课一次；前端存回课时 variantPool）。
        入参: {unit_id?, sentences:[{ru,zh}]}；AI 出 9 类词池；弱校验非空。"""
        err = self._require_admin(data)
        if err:
            return err
        sentences = data.get("sentences") or []
        if not isinstance(sentences, list) or not sentences:
            return self._json(400, {"ok": False, "error": "缺少 sentences（本课句子列表）"})
        obj = call_llm(self._pool_build_prompt(sentences), "", json_mode=True)
        if not obj:
            return self._json(200, {"ok": False, "fallback": True, "reason": "ai_none"})
        pool, reason = self._pool_verify(obj)
        if pool is None:
            print("[slots] pool 校验失败 reason=%s 原始返回=%s" % (reason, json.dumps(obj, ensure_ascii=False)[:500]))
            return self._json(200, {"ok": False, "fallback": True, "reason": reason, "raw": json.dumps(obj, ensure_ascii=False)[:400]})
        return self._json(200, {"ok": True, "pool": pool})

    # ---------- P5（路线B）：句乐部式 6 列表格生成 ----------
    # AI 只做 3 件事：① 意群分组决策（骨架，返回索引组）② 从词池/模板选词填文本 ③ 变格变位 + 中文翻译 + 语法标签。
    # 结构（序号/卡片类型/组ID/步骤顺序）全部由机器按前端模板引擎（jlTableEngine.js）的意图序列补齐 → 结构错误率趋近 0。
    _SLOT_TABLE_FIXED_POOL_KEYS = ("negation", "time", "place", "degree", "evaluation", "preposition", "connector", "predicates", "objects")
    _SLOT_TABLE_TEMPLATE_ZH = {
        "skeleton": "骨架完整句", "negation": "否定句", "time_pos": "加时间状语", "time_neg": "否定+时间",
        "predicate_pos": "换谓语肯定句", "predicate_neg": "换谓语否定句", "object_pos": "换宾语肯定句",
        "object_neg": "换宾语否定句", "evaluation": "评价句", "evaluation_ext": "评价句扩展",
        "degree": "程度副词句", "prep": "介词短语句", "compound": "复合句", "place_pos": "加地点句",
        "place_neg": "否定+地点", "if": "条件句", "so": "so 连句", "not": "否定评价句", "review": "复习句",
        "freq_neg": "否定+频率", "swap_neg": "换宾语否定句",
    }

    def _slot_table_intents_fp(self, intents, pool=None):
        try:
            # 指纹 = 意图结构 + 词池内容：改模板结构或改词池都会自动失效缓存（防止旧词池脏表命中）
            payload = {"intents": intents, "pool": pool or {}}
            return hashlib.md5(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        except Exception:
            return ""

    def _slot_table_group_prompt(self, tokens, russian_text, difficulty):
        lines = [
            "你是俄语教学句乐部课程的【意群分组】规划师。你只把 token 编号分组，禁止生成任何俄语文本。只输出 JSON，不要解释。",
            "【核心句】（已俄语化）：", russian_text, "",
            "【token 编号列表】（编号从 0 开始）：",
        ]
        for i, t in enumerate(tokens):
            lines.append("%d: %s" % (i, t))
        lines += [
            "",
            "【任务】按教学意群把全部编号分成若干组：",
            "- 【铁律】谓语（动词变位/谓语性副词，如 люблю、хочу、нужно）必须【单独一组】，禁止与宾语/补语合并",
            "- 固定搭配/介词短语/不可拆短语整体一组（如 в парке、мой друг 各一组）",
            "- 宾语/补语/时间/地点可单独或合并成意群",
            "- 所有编号必须用且只用一次；每组编号必须连续",
            "【分组粒度】一律词级拆分（难度差异由后续骨架裁剪控制，分组只负责喂词准确）",
            "【每组角色 role】只能取：主语 / 谓语 / 补语 / 介词短语 / 副词 / 其他",
            '【输出】{"groups":[{"indexes":[0],"role":"主语"},{"indexes":[1],"role":"谓语"},{"indexes":[2,3],"role":"补语"}]}',
        ]
        return "\n".join(lines)

    def _slot_table_group_verify(self, groups, n):
        """校验分组（与前端 verifyIndexes 同逻辑）：不重不漏、组内连续、编号界内；返回按首索引排序的 [{indexes,role}] 或 None。"""
        if not isinstance(groups, list) or not groups:
            return None
        seen = set()
        out = []
        for g in groups:
            idx = g.get("indexes") if isinstance(g, dict) else None
            if not isinstance(idx, list) or not idx:
                return None
            for i in idx:
                if not isinstance(i, int) or i < 0 or i >= n or i in seen:
                    return None
                seen.add(i)
            for k in range(1, len(idx)):
                if idx[k] != idx[k - 1] + 1:
                    return None
            out.append({"indexes": idx, "role": str(g.get("role") or "其他").strip()})
        if len(seen) != n:
            return None
        return sorted(out, key=lambda x: x["indexes"][0])

    def _slot_table_skeleton_steps(self, tokens, groups, difficulty="easy"):
        """由分组决策机器生成骨架意图（与前端 buildSkeletonIntent 逐字节一致）：
        意群1 单出 → 每新意群单出 + 累积组合 → 最后完整句；单意群补完整句行。
        分组一律词级（喂词完整：sub/pred/obj 都进 ctx）；表格显示粒度按难度裁剪：
        - medium：主语/谓语单个词积木隐藏（只显示 ≥2 词组合块 + 完整句）
        - hard：全部骨架积木隐藏（只显示完整句）——隐藏行照常喂 ctx，组合块拼装不受影响"""
        n = len(tokens)
        steps = []
        g0 = groups[0]
        steps.append({"kind": "part", "cardType": "积木", "source": "core",
                      "tokensRef": [g0["indexes"][0], g0["indexes"][-1]], "role": g0.get("role") or "chunk", "groupId": "G_01"})
        for i in range(1, len(groups)):
            g = groups[i]
            end = g["indexes"][-1]
            steps.append({"kind": "part", "cardType": "积木", "source": "core",
                          "tokensRef": [g["indexes"][0], end], "role": g.get("role") or "chunk", "groupId": "G_01"})
            if i < len(groups) - 1:
                steps.append({"kind": "part", "cardType": "积木", "source": "core",
                              "tokensRef": [0, end], "role": "comb", "groupId": "G_01"})
            else:
                steps.append({"kind": "full", "cardType": "完整句", "template": "skeleton",
                              "compose": [{"source": "core", "tokensRef": [0, n - 1]}], "groupId": "G_01"})
        if steps[-1]["kind"] != "full":
            steps.append({"kind": "full", "cardType": "完整句", "template": "skeleton",
                          "compose": [{"source": "core", "tokensRef": [0, n - 1]}], "groupId": "G_01"})
        # 难度裁剪（2026-10-06 用户定稿：medium 只显 ≥2 词积木 / hard 纯完整句）
        if difficulty == "hard":
            for s in steps:
                if s.get("kind") == "part":
                    s["hidden"] = True
        elif difficulty == "medium":
            for s in steps:
                if s.get("kind") == "part" and s.get("role") in ("主语", "谓语") and s.get("tokensRef") and s["tokensRef"][0] == s["tokensRef"][-1]:
                    s["hidden"] = True
        return steps

    def _slot_table_prefill(self, intents, tokens, pool):
        """机械预填：确定每行 ru 是否已由机器定死（fixed）。
        fixed 行：core 截取 / 模板固定词 / 不需形态变化的词池词（时间、地点、程度、否定等）。
        !fixed 行：完整句（整句重写）、需变位/变格的词池词（谓语/补语）、复用块 —— AI 填 ru/zh/tag。"""
        pool = pool if isinstance(pool, dict) else {}
        rows = []
        for st in intents:
            row = {
                "kind": st.get("kind"), "cardType": st.get("cardType"), "groupId": st.get("groupId") or "G_01",
                "template": st.get("template"), "role": st.get("role") or "chunk", "tag": "",
            }
            fixed = None
            src = st.get("source")
            if st.get("kind") == "part":
                if src == "core" and isinstance(st.get("tokensRef"), list) and len(st["tokensRef"]) == 2:
                    s, e = st["tokensRef"]
                    if 0 <= s <= e < len(tokens):
                        fixed = " ".join(tokens[s:e + 1])
                elif src == "template" and st.get("templateText"):
                    fixed = str(st["templateText"]).strip()
                elif src == "pool" and st.get("poolKey") in self._SLOT_TABLE_FIXED_POOL_KEYS:
                    items = pool.get(st["poolKey"]) if isinstance(pool.get(st["poolKey"]), list) else []
                    idx = st.get("poolIndex")
                    if isinstance(idx, int) and 0 <= idx < len(items):
                        # 词池条目可带扩展字段（如 objects: {ru:'еду', inf:'есть'}）；step 指定 poolField 时取其字段
                        _it = items[idx] if isinstance(items[idx], dict) else {}
                        fixed = str((_it.get(st.get("poolField") or "ru") or _it.get("ru") or "")).strip()
            row["fixed"] = fixed if fixed else None
            row["source"] = src
            row["poolKey"] = st.get("poolKey")
            row["reuseRef"] = st.get("reuseRef")
            row["hint"] = st.get("hint")
            row["compose"] = st.get("compose")
            row["tokensRef"] = st.get("tokensRef")
            row["hidden"] = st.get("hidden")  # 难度档裁剪标记（medium/hard 隐藏行照常喂 ctx、组装时跳过）
            # 组合类 part 行（не люблю / делать это / Я люблю）：组装阶段机器拼（neg+pred / inf+obj / sub+pred）
            if st.get("kind") == "part" and st.get("role") in ("组合", "否定组合"):
                row["comb"] = True
            rows.append(row)
        return rows

    # ============ 机器拼装：组合块（part 行 role=组合/否定组合） ============
    # 词来自 ctx（前序已机器确定的词）：не+谓语 / 不定式+宾语 / 不定式+地点 / 主语+谓语 / 谓语+宾语
    def _slot_table_machine_comb(self, role, ctx):
        if not role:
            return ""
        neg = ctx.get("neg") or ""
        pred = ctx.get("pred") or ""
        obj = ctx.get("obj") or ""
        inf = ctx.get("inf") or ""
        place = ctx.get("place") or ""
        sub = ctx.get("sub") or ""
        if role == "否定组合":
            return (" ".join(x for x in (neg, pred) if x)).strip()
        # 组合：按教学上下文择优（优先级 = 已出现词的最自然块）
        # ⚠️ 宾语已含不定式（делать это）时不再重复拼 inf，避免 "делать делать это"
        if inf and obj:
            if obj.startswith(inf):
                return obj.strip()
            return (" ".join(x for x in (inf, obj) if x)).strip()
        if inf and place:
            return (" ".join(x for x in (inf, place) if x)).strip()
        if neg and pred:
            return (" ".join(x for x in (neg, pred) if x)).strip()
        if sub and pred and not obj:
            return (" ".join(x for x in (sub, pred) if x)).strip()
        if pred and obj:
            return (" ".join(x for x in (pred, obj) if x)).strip()
        return ""

    # ============ 机器拼装：完整句（full 行；除 if/so/review/skeleton 全由机器拼） ============
    # 后端兜底句型检测：非动词句自动过滤掉换谓语/换宾语 intents
    def _slot_table_filter_by_sentence_type(self, intents, russian_text, tokens):
        """检测句子类型，非动词句自动去掉高风险 intents（换谓语/换宾语/不定式扩展）。
        动词句保留完整长链；判断句/疑问句/无人称句走短链。"""
        text = (russian_text or "").strip().lower().rstrip(".!?,;:")
        tokens_lower = [t.lower().strip(".,!?") for t in tokens if t]

        # —— 规则：判断是否为非动词句 ——
        is_non_verbal = False

        # 规则1：Это/это 开头 → 判断句
        if tokens_lower and tokens_lower[0] in ("это",):
            is_non_verbal = True

        # 规则2：结尾是 дома/здесь/тут/там → 存在句（Анна дома. / Книга здесь.）
        if tokens_lower and tokens_lower[-1] in ("дома", "здесь", "тут", "там"):
            is_non_verbal = True

        # 规则3：疑问词开头 → 疑问句
        if tokens_lower and tokens_lower[0] in ("кто", "что", "где", "когда", "почему", "как", "сколько", "чей"):
            is_non_verbal = True

        # 规则4：无人称句开头词
        if tokens_lower and tokens_lower[0] in ("мне", "тебе", "нам", "вам", "надо", "нужно", "можно", "холодно", "тепло", "весело", "грустно"):
            is_non_verbal = True

        if not is_non_verbal:
            return intents  # 动词句，保留完整长链

        # —— 非动词句：过滤掉高风险 intents ——
        # 要过滤的模板：换谓语/换宾语/不定式扩展相关
        SKIP_TEMPLATES = {"infinitive", "predicate_pos", "predicate_neg",
                          "object_pos", "object_neg", "swap_neg", "freq_neg"}
        # 要过滤的角色：词池来的新谓语/新宾语积木
        SKIP_ROLES = {"谓语", "补语"}

        filtered = []
        for st in intents:
            tmpl = st.get("template") or ""
            role = st.get("role") or ""
            src = st.get("source") or ""

            # 跳过换谓语/换宾语模板
            if tmpl in SKIP_TEMPLATES:
                continue

            # 跳过词池来的谓语/补语积木（换谓语/换宾语段的积木行）
            if src == "pool" and role in SKIP_ROLES and st.get("poolKey") in ("predicates", "objects"):
                continue

            filtered.append(st)

        print(f"[slot_table] 非动词句检测: '{russian_text[:30]}' → 过滤前 {len(intents)} 行 → 过滤后 {len(filtered)} 行")
        return filtered

    # 模板结构由模板定死，槽位词来自 ctx（前序词池/模板词/上一完整句）→ 结构错误率趋近 0
    def _slot_table_build_full(self, template, ctx):
        if not template:
            return ""
        sub = "Мне" if ctx.get("nominal_pred") else (ctx.get("sub") or "Я")
        neg = ctx.get("neg") or ""
        pred = ctx.get("pred") or ""
        obj = ctx.get("obj") or ""
        time_adv = ctx.get("time_adv") or ""
        place = ctx.get("place") or ""
        evalw = ctx.get("eval") or ""
        last_base = ctx.get("last_base") or ""  # 最近基础肯定句（无时间/地点/频率状语）
        last_neg_base = ctx.get("last_neg_base") or ""  # 最近基础否定句（无状语）
        last_full = ctx.get("last_full") or ""
        last_neg = ctx.get("last_neg") or ""  # 最近否定句（含已叠加状语 → time_neg 叠加基准）
        last_eval = ctx.get("last_eval") or ""
        if template == "negation":
            return (" ".join(x for x in (sub, neg, pred, obj) if x)).strip()
        if template in ("object_pos", "predicate_pos"):
            inf = ctx.get("inf") or ""
            if inf and obj.startswith(inf):
                # 宾语已含不定式（делать это）→ 不重复拼 inf，避免 "делать делать это"
                return (" ".join(x for x in (sub, pred, obj) if x)).strip()
            if inf:
                # 谓语/宾语换新后保留不定式短语（句乐部 I want to do it 结构）
                return (" ".join(x for x in (sub, pred, inf, obj) if x)).strip()
            return (" ".join(x for x in (sub, pred, obj) if x)).strip()
        if template in ("object_neg", "predicate_neg"):
            inf = ctx.get("inf") or ""
            if inf and obj.startswith(inf):
                return (" ".join(x for x in (sub, neg, pred, obj) if x)).strip()
            if inf:
                return (" ".join(x for x in (sub, neg, pred, inf, obj) if x)).strip()
            return (" ".join(x for x in (sub, neg, pred, obj) if x)).strip()
        # 判断句（Это + 名词）：状语放句首更自然（Сегодня это мама），而非句尾（Это мама сегодня）
        is_copula = sub.lower() == "это"
        # 状语放句首时，原句开头的 Это 要小写（变成 это）
        def _lower_first(s):
            if not s: return s
            parts = s.split(" ", 1)
            parts[0] = parts[0].lower()
            return parts[0] + (" " + parts[1] if len(parts) > 1 else "")
        if template == "time_pos":
            # 基于基础肯定句 + 时间（避免 "сегодня каждый день" 等状语残留叠加）
            base = last_base or last_full
            if is_copula:
                return (" ".join(x for x in (time_adv, _lower_first(base)) if x)).strip()
            return (" ".join(x for x in (base, time_adv) if x)).strip()
        if template == "time_neg":
            # 基于最近否定句 + 时间（G_04 基础否定；G_05 带地点否定 → 天然叠加，句乐部节奏）
            if is_copula:
                return (" ".join(x for x in (time_adv, _lower_first(last_neg)) if x)).strip()
            return (" ".join(x for x in (last_neg, time_adv) if x)).strip()
        if template == "swap_neg":
            # 换宾语段否定句（句乐部 46 结构）：主语 + 否定组合 + 不定式 + 宾语 + 时间，不依赖 last_neg
            parts = [sub]
            nc = ctx.get("neg_comb") or ""
            if nc:
                parts.append(nc)
            else:
                parts.append(neg)
                if pred:
                    parts.append(pred)
            inf = ctx.get("inf") or ""
            obj = ctx.get("obj") or ""
            if inf and obj:
                if not obj.startswith(inf):
                    parts.append(inf)
                parts.append(obj)
            elif inf:
                parts.append(inf)
            elif obj:
                parts.append(obj)
            if time_adv:
                parts.append(time_adv)
            return (" ".join(parts)).strip()
        if template == "freq_neg":
            # 频率段否定句：当前状态直拼（主语+否定组合+不定式+宾语+频率），避免 last_neg_base 残留旧宾语
            parts = [sub]
            nc = ctx.get("neg_comb") or ""
            if nc:
                parts.append(nc)
            else:
                parts.append(neg)
                if pred:
                    parts.append(pred)
            inf = ctx.get("inf") or ""
            obj = ctx.get("obj") or ""
            if inf and obj:
                if not obj.startswith(inf):
                    parts.append(inf)
                parts.append(obj)
            elif inf:
                parts.append(inf)
            elif obj:
                parts.append(obj)
            if time_adv:
                parts.append(time_adv)
            return (" ".join(parts)).strip()
        if template == "freq_neg":
            # 频率段专用：基础否定句 + 频率（避免 "сегодня каждый день" 残留）
            return (" ".join(x for x in (last_neg_base, time_adv) if x)).strip()
        if template == "place_pos":
            base = last_base or last_full
            if is_copula:
                return (" ".join(x for x in (place, _lower_first(base)) if x)).strip()
            return (" ".join(x for x in (base, place) if x)).strip()
        if template == "place_neg":
            # 基于基础否定句 + 地点（避免把前面时间词带进来 → "сегодня здесь"）
            if is_copula:
                return (" ".join(x for x in (place, _lower_first(last_neg_base)) if x)).strip()
            return (" ".join(x for x in (last_neg_base, place) if x)).strip()
        if template == "evaluation":
            return ("Это " + evalw).strip() if evalw else ""
        if template == "degree":
            return ("Это очень " + evalw).strip() if evalw else ""
        if template == "evaluation_ext":
            ext = ctx.get("ext") or ctx.get("inf") or ""
            return (" ".join(x for x in (last_eval, ext) if x)).strip()
        if template == "not":
            return "Это не важно"
        return ""  # if / so / review / skeleton 不在此机器拼

    # ============ 机器拼装：part 行更新 ctx（组装状态机） ============
    def _slot_table_ctx_update(self, ctx, role, ru, source, pool_key, tokens_ref=None):
        if not ru:
            return
        if role == "谓语":
            # 多词谓语意群（LLM 把宾语并入谓语组，如 [1,2]=люблю еду）→ 拆分：pred=首词，obj=其余
            if ctx.get("tokens") and tokens_ref and len(tokens_ref) == 2:
                s0, e0 = tokens_ref
                ts = ctx["tokens"]
                if 0 <= s0 <= e0 < len(ts):
                    if e0 > s0:
                        ctx["pred"] = ts[s0]
                        rest = ts[s0 + 1:e0 + 1]
                        if rest and not ctx.get("obj"):
                            ctx["obj"] = " ".join(rest)
                    else:
                        ctx["pred"] = ts[s0]
            else:
                ctx["pred"] = ru
            ctx["nominal_pred"] = ru in ("нужно", "надо", "можно", "нельзя")
        elif role == "补语":
            if source == "template":
                ctx["ext"] = ru
            else:
                ctx["obj"] = ru
        elif role == "宾语":
            ctx["obj"] = ru
        elif role == "否定":
            ctx["neg"] = ru
        elif role == "否定组合":
            ctx["neg_comb"] = ru
        elif role == "时间":
            # 硬过滤：方式副词不能当时间词（поздно/быстро 等），自动替换成 сегодня
            TIME_BLACKLIST = {"поздно", "рано", "быстро", "медленно", "хорошо", "плохо",
                              "тихо", "громко", "весело", "грустно", "трудно", "легко"}
            if ru.lower().strip() in TIME_BLACKLIST:
                ru = "сегодня"
            ctx["time_adv"] = ru
        elif role == "频率":
            ctx["time_adv"] = ru
        elif role == "地点":
            ctx["place"] = ru
        elif role == "程度":
            ctx["deg"] = ru
        elif role == "评价":
            ctx["eval"] = ru
        elif role == "不定式":
            ctx["inf"] = ru
        elif role == "连词":
            ctx["conn"] = ru
        elif role in ("组合", "否定组合", "comb"):
            # 骨架组合块（固定 tokensRef 截取）：反推谓语供否定/换谓复用
            ctx["last_comb"] = ru
            if not ctx.get("pred") and ctx.get("tokens") and tokens_ref and len(tokens_ref) == 2:
                s0, e0 = tokens_ref
                ts = ctx["tokens"]
                if 0 <= s0 <= e0 < len(ts):
                    ctx["pred"] = ts[1] if s0 == 0 and e0 >= 1 else ts[s0]

    _SLOT_TABLE_NEG_TEMPLATES = ("negation", "time_neg", "place_neg", "predicate_neg", "object_neg")

    # ============ 同组完整句互重重填（禁用 AI 造词：任何重复一律 fallback dup_full，前端机械兜底 pending） ============
    # ⚠️ 2026-10-06 根因修复：此函数此前让 LLM 重写整句（如 "в библиотеке нет…" / "я не успеваю… по вечерам"），
    # 是表格野词 + 中文错位的最后入口。机器拼装修复（time_pos 基于 last_affirm）后同组重复应消失；
    # 若个别句子仍重复 → 直接返回 None → 整次 fallback（前端机械兜底表完全干净），绝不 AI 造词。
    def _slot_table_retry_dup(self, prefilled, out_rows, dup_idx, russian_text):
        return None

    def _slot_table_fill_prompt(self, russian_text, rows, pool=None):
        pool_label = dict(self._POOL_KEYS)
        lines = [
            "你是俄语教学句乐部课程的【填词与翻译】。你只填每张学习卡片的内容，禁止改变卡片顺序和数量。只输出 JSON，不要解释。",
            "【核心句】（已俄语化，骨架完整句由机器拼装保证等于它）：", russian_text, "",
            "【规则】",
            "- 俄语已定（fixed_ru / 机器拼装）的行：你【禁止修改】俄语，只填 zh（准确中文翻译）和 tag（语法标签，如 主语 / 动词变位 / 名词宾格 / 否定句 / 主谓宾结构）。",
            "- 俄语未定的行（只可能是 组合块 或 复合句 if/so）：组合块填 ru（短语，禁止整句）；if/so 填 ru（完整句子，语法正确）。其余行俄语都已被机器拼装确定，你【禁止】改动。",
            "- 【组合块中文铁律】组合块如 не X：zh 必须译成“不”+X 的动词义（не люблю=不爱/不喜欢），禁止带宾语；如 X+Y（不定式+宾语）：zh 译整块（делать это=做这个）。禁止只翻译其中一个词。",
            "- 每行 zh 必须反映该行内容；完整句行的 zh 是整句翻译，禁止照抄其他句的翻译。",
            "- 【铁律】完整句之间不得互相重复；任何完整句不得等于或照抄核心句（russian_text）。",
            "- tag 用中文简短提炼语法点（3-10 字）。",
            "- 行数必须与输入一致，顺序不可调换。",
            "",
            "【逐行输入】",
        ]
        for i, r in enumerate(rows):
            hint = r.get("hint") or ""
            if not hint:
                if r["kind"] == "part":
                    if r["poolKey"]:
                        hint = "词池词：" + pool_label.get(r["poolKey"], r["poolKey"])
                    elif r["role"] == "comb":
                        hint = "组合块（整块翻译，禁止只翻其中一个词；не X 译为 不X）"
                    else:
                        hint = "零件：" + (r["role"] or "chunk")
                elif r["kind"] == "full":
                    hint = "完整句：" + (self._SLOT_TABLE_TEMPLATE_ZH.get(r["template"]) or r["template"])
            if r["fixed"]:
                lines.append('%d. 卡片类型=%s 俄语已定="%s"（禁止修改） 提示=%s' % (i + 1, r["cardType"], r["fixed"], hint))
            else:
                lines.append('%d. 卡片类型=%s 提示=%s → 需填 ru/zh/tag' % (i + 1, r["cardType"], hint))
        lines.append("")
        lines.append('【输出】{"rows":[{"ru":"（仅未定俄语的行）","zh":"...","tag":"..."}]}（与输入行数一致）')
        return "\n".join(lines)

    def _handle_admin_segments_table_fill(self, data):
        import re as _re
        """POST /api/admin/segments/table-fill —— 句乐部式 6 列表格生成（路线B）。
        入参: {sentence_hash, russian_text, tokens, difficulty, intents, pool?}
        intents = 前端模板引擎（jlTableEngine.js）的意图序列；骨架部分若缺 tokensRef → 后端做 AI 分组决策后机器生成。
        返回: {ok:true, rows:[{seq,cardType,ru,zh,tag,groupId}]} 或 {fallback:true, reason}。
        幂等：缓存键 (sentence_hash, difficulty, intents_fp)；命中 ok 直接返回，不重复调 LLM。"""
        err = self._require_admin(data)
        if err:
            return err
        sentence_hash = str(data.get("sentence_hash") or "").strip()
        russian_text = str(data.get("russian_text") or "").strip()
        tokens = data.get("tokens") or []
        difficulty = str(data.get("difficulty") or "easy").strip()
        intents = data.get("intents")
        pool = data.get("pool")
        if not isinstance(pool, dict):
            pool = None
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "easy"
        if not sentence_hash or not russian_text or not isinstance(tokens, list) or not tokens:
            return self._json(400, {"ok": False, "error": "缺少 sentence_hash / russian_text / tokens"})
        if not isinstance(intents, list) or not intents:
            return self._json(400, {"ok": False, "error": "缺少 intents（模板引擎意图序列）"})

        # ===== 新课程引擎：先试新引擎，失败就 fallback 到旧引擎 =====
        if USE_NEW_ENGINE and difficulty == "easy":
            try:
                from course_engine.generate import generate_course_steps
                result = generate_course_steps(russian_text, "")
                if result["success"]:
                    # 转换格式：新引擎输出 → 旧引擎 rows 格式
                    rows = []
                    for s in result["steps"]:
                        rows.append({
                            "seq": s["seq"],
                            "cardType": s["type"],
                            "ru": s["ru"],
                            "zh": s["zh"],
                            "tag": s["tag"],
                            "groupId": s["gid"],
                        })
                    print(f"[course_gen] engine=new, ru={russian_text[:30]}, success=True, rows={len(rows)}")
                    return self._json(200, {"ok": True, "engine": "new", "rows": rows})
                else:
                    print(f"[course_gen] engine=new, ru={russian_text[:30]}, success=False, error={result['error'][:80]}")
                    # 失败了，继续走旧引擎
            except Exception as e:
                print(f"[course_gen] engine=new_exception, ru={russian_text[:30]}, error={str(e)[:80]}")
                # 异常了，继续走旧引擎

        intents_fp = self._slot_table_intents_fp(intents, pool)
        # 1) 骨架分组：intents 骨架段缺 tokensRef → 后端 AI 分组 + 机器生成骨架（前端已给分组则跳过）
        need_group = True
        for st in intents:
            if st.get("template") == "skeleton" and isinstance(st.get("compose"), list) and st["compose"] and st["compose"][0].get("tokensRef"):
                need_group = False
                break
        # 2) 缓存幂等
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT `rows`, review_status, COALESCE(prompt_v,'v1') FROM sentence_slot_tables WHERE sentence_hash=%s AND difficulty=%s AND intents_fp=%s",
                                (sentence_hash, difficulty, intents_fp))
                    row = cur.fetchone()
                    if row:
                        return {"rows": row[0], "status": row[1], "prompt_v": row[2]}
                    return {"rows": None, "status": None, "prompt_v": ""}
            finally:
                conn.close()
        try:
            r = _seg_execute(_q)
        except Exception as e:
            print("[slot_table] 缓存查询失败：", e)
            return self._json(500, {"ok": False, "error": "缓存查询失败（数据库不可用）"})
        if r.get("rows") and r.get("status") == "ok" and r.get("prompt_v") == SLOT_TABLE_PROMPT_V:
            try:
                cached_rows = json.loads(r["rows"])
                if isinstance(cached_rows, list) and cached_rows:
                    return self._json(200, {"ok": True, "cached": True, "rows": cached_rows})
            except Exception:
                pass
        # 3) 生成（含骨架分组）
        # 3.0) 后端兜底：自动句型检测 — 非动词句自动过滤掉换谓语/换宾语 intents
        built_intents = self._slot_table_filter_by_sentence_type(intents, russian_text, tokens)
        if need_group:
            obj = None
            for _g in range(2):  # 分组 LLM 偶发空响应，重试 1 次
                obj = call_llm(self._slot_table_group_prompt(tokens, russian_text, difficulty), "", json_mode=True)
                if obj:
                    break
            if not obj:
                return self._json(200, {"ok": False, "fallback": True, "reason": "group_ai_none"})
            groups = self._slot_table_group_verify(obj.get("groups"), len(tokens))
            if groups is None:
                return self._json(200, {"ok": False, "fallback": True, "reason": "group_invalid", "raw": json.dumps(obj, ensure_ascii=False)[:400]})
            skeleton = self._slot_table_skeleton_steps(tokens, groups, difficulty)
            # 骨架段边界：从首个 template='skeleton' 的 full 行往回都是 G_01 骨架行 → 整段替换
            sk_end = -1
            for i, st in enumerate(intents):
                if st.get("template") == "skeleton":
                    sk_end = i
                    break
            if sk_end >= 0:
                built_intents = skeleton + [st for j, st in enumerate(intents) if j > sk_end]
            else:
                built_intents = skeleton + [st for st in intents if st.get("template") != "skeleton"]
        # 4) 机械预填（fixed 判定）
        prefilled = self._slot_table_prefill(built_intents, tokens, pool)
        # 4.5) 机器预拼第一遍：确定【每一行】的 ru（含 full 行），LLM-2 只填 zh/tag，绝不 AI 造词
        #      fixed 只覆盖 part 行；full 行（skeleton/变体/review）在此机器拼出并回写 fixed，
        #      → fill_prompt 会把所有行视为"俄语已定"→ AI 无法输出 ru（if/so 复合句除外，保留 AI ru）。
        mctx = {"sub": (tokens[0] if tokens else ""), "pred": "", "obj": "", "neg": "", "neg_comb": "", "inf": "",
                "time_adv": "", "place": "", "eval": "", "deg": "", "ext": "", "conn": "", "nominal_pred": False,
                "last_full": "", "last_full_zh": "", "last_neg": "", "last_affirm": "", "last_base": "", "last_neg_base": "", "last_eval": "", "full_by_template": {},
                "tokens": tokens, "last_comb": "", "pred_zh": ""}
        for _r in prefilled:
            _mru = _r.get("fixed") or ""
            _tpl = _r.get("template") or ""
            if not _mru and _r.get("comb"):
                _mru = self._slot_table_machine_comb(_r.get("role"), mctx)
            if not _mru and _r.get("kind") == "part" and not _r.get("source"):
                # 兼容旧前端模板（infinitive 段零件未标 source 的过渡版本）：固定词兜底
                _role = _r.get("role") or ""
                if _role == "不定式":
                    _mru = "делать"
                elif _role == "宾语":
                    _mru = "это"
            if not _mru and _r.get("kind") == "part" and _r.get("role") == "补语" and _r.get("source") == "reuse":
                # 复用骨架宾语（predicate_swap 段）：取 ctx.obj（骨架补语/宾语已机器确定）
                _mru = mctx.get("obj") or ""
            if not _mru and _r.get("kind") == "full":
                if _tpl == "review":
                    # 复习行：按 hint 模板名复制已生成完整句（机器已存 full_by_template）
                    _m = _re.search(r"复习[:：]\s*([a-z_]+)", _r.get("hint") or "")
                    _src_tpl = _m.group(1) if _m else ""
                    _src = mctx.get("full_by_template", {}).get(_src_tpl)
                    if _src:
                        _mru = _src["ru"]
                    elif mctx.get("last_full"):
                        _mru = mctx["last_full"]
                elif _tpl == "skeleton":
                    _comp = _r.get("compose") or []
                    if _comp and isinstance(_comp[0].get("tokensRef"), list) and len(_comp[0]["tokensRef"]) == 2:
                        _s0, _e0 = _comp[0]["tokensRef"]
                        if 0 <= _s0 <= _e0 < len(tokens):
                            _mru = " ".join(tokens[_s0:_e0 + 1])
                else:
                    _mru = self._slot_table_build_full(_tpl, mctx)
            if not _mru and _tpl not in ("if", "so"):
                # 机器拼不出的非 if/so 行：宁可整次失败（前端机械兜底 pending），绝不让 AI 造词
                return self._json(200, {"ok": False, "fallback": True, "reason": "machine_gap", "detail": _tpl or (_r.get("role") or "")})
            if _mru:
                _r["fixed"] = _mru
            if _r.get("kind") == "part":
                self._slot_table_ctx_update(mctx, _r.get("role"), _mru, _r.get("source"), _r.get("poolKey"), _r.get("tokensRef"))
            elif _r.get("kind") == "full" and _mru and _tpl != "review":
                mctx["last_full"] = _mru
                mctx["full_by_template"][_tpl] = {"ru": _mru}
                if _tpl in self._SLOT_TABLE_NEG_TEMPLATES:
                    mctx["last_neg"] = _mru
                    if _tpl in ("negation", "object_neg", "predicate_neg"):
                        mctx["last_neg_base"] = _mru  # 基础否定句（place_neg/freq_neg 基准）
                else:
                    mctx["last_affirm"] = _mru
                    if _tpl in ("skeleton", "object_pos", "predicate_pos"):
                        mctx["last_base"] = _mru  # 基础肯定句（time_pos/place_pos 基准）
                if _tpl in ("evaluation", "degree", "evaluation_ext", "not"):
                    mctx["last_eval"] = _mru
        # 5) LLM-2 填词（失败重试 1 次；行多时拆批并行——单次大 JSON 生成可能超 Render 60s 网关限制）
        CHUNK = 28

        def _fill_chunk(rows_batch):
            obj = call_llm(self._slot_table_fill_prompt(russian_text, rows_batch, pool), "", json_mode=True)
            if obj and isinstance(obj.get("rows"), list) and len(obj["rows"]) == len(rows_batch):
                return obj["rows"]
            return None

        obj2 = None
        for _attempt in range(2):
            if len(prefilled) <= CHUNK:
                chunk_rows = _fill_chunk(prefilled)
                if chunk_rows is not None:
                    obj2 = {"rows": chunk_rows}
            else:
                chunks = [prefilled[i:i + CHUNK] for i in range(0, len(prefilled), CHUNK)]
                results = [None] * len(chunks)
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=len(chunks)) as ex:
                        for k, r2 in enumerate(ex.map(_fill_chunk, chunks)):
                            results[k] = r2
                except Exception:
                    results = [None] * len(chunks)
                if all(r2 is not None for r2 in results):
                    obj2 = {"rows": [row for r2 in results for row in r2]}
            if obj2 and isinstance(obj2.get("rows"), list) and len(obj2["rows"]) == len(prefilled):
                break
            print("[slot_table] 填词失败(第%d次) 原始=%s" % (_attempt + 1, json.dumps(obj2, ensure_ascii=False)[:300] if obj2 else "ai_none"))
            obj2 = None
        if obj2 is None:
            return self._json(200, {"ok": False, "fallback": True, "reason": "fill_failed"})
        # 6) 组装：机器拼装状态机（AI 只填 zh/tag 与 if/so；结构由模板定死，错误率趋近 0）
        ai_rows = obj2["rows"]
        ctx = {"sub": (tokens[0] if tokens else ""), "pred": "", "obj": "", "neg": "", "neg_comb": "", "inf": "",
               "time_adv": "", "place": "", "eval": "", "deg": "", "ext": "", "conn": "", "nominal_pred": False,
               "last_full": "", "last_full_zh": "", "last_neg": "", "last_affirm": "", "last_base": "", "last_neg_base": "", "last_eval": "", "full_by_template": {},
               "tokens": tokens, "last_comb": "", "pred_zh": ""}
        out_rows = []
        for i, r in enumerate(prefilled):
            if r.get("hidden"):
                # hidden 行（前端难度档标记）：prefill/LLM 填词已处理并更新 ctx，但不出现在表格
                # （2026-10-06 三档粒度：medium 隐藏单字积木、hard 隐藏全部积木——完整句仍靠其 ctx 机器拼装）
                continue
            ai = ai_rows[i] if isinstance(ai_rows[i], dict) else {}
            ru = r["fixed"] or ""
            if not ru and r.get("comb"):
                ru = self._slot_table_machine_comb(r.get("role"), ctx)
            if not ru and r.get("kind") == "full":
                tpl = r.get("template") or ""
                if tpl == "skeleton":
                    # 骨架完整句 = compose tokensRef 机械截取（拼接天然 == 原句）
                    comp = r.get("compose") or []
                    if comp and isinstance(comp[0].get("tokensRef"), list) and len(comp[0]["tokensRef"]) == 2:
                        s0, e0 = comp[0]["tokensRef"]
                        if 0 <= s0 <= e0 < len(tokens):
                            ru = " ".join(tokens[s0:e0 + 1])
                else:
                    ru = self._slot_table_build_full(tpl, ctx)
            if not ru:
                # 兜底：仅 if/so 复合句允许 AI 填整句；其余行机器拼不出 → 整次失败（前端机械兜底 pending），绝不 AI 造词
                if r.get("template") in ("if", "so"):
                    ru = str(ai.get("ru") or "").strip()
                else:
                    return self._json(200, {"ok": False, "fallback": True, "reason": "machine_gap", "detail": r.get("template") or r.get("role") or ""})
            zh = str(ai.get("zh") or "").strip()
            tag = str(ai.get("tag") or "").strip() or r["role"] or ""
            if r.get("comb"):
                tag = "组合块"  # 组合块 tag 机器固定，AI 填的 tag 不稳定
                # 否定组合块 zh 机器兜底：не X → "不"+谓语中文（AI 常漏"不"）
                if r.get("role") in ("组合", "否定组合", "comb") and ru.startswith("не ") and ctx.get("pred_zh") and not zh.startswith("不"):
                    zh = "不" + ctx["pred_zh"]
            if r.get("kind") == "part" and r.get("role") == "谓语" and zh:
                ctx["pred_zh"] = zh
            if r.get("kind") == "part":
                self._slot_table_ctx_update(ctx, r.get("role"), ru, r.get("source"), r.get("poolKey"), r.get("tokensRef"))
            elif r.get("kind") == "full":
                tpl = r.get("template") or ""
                if tpl == "review":
                    # 复习行：按 hint 模板名复制已生成完整句（含 zh/tag），零 AI 结构决策
                    m = _re.search(r"复习[:：]\s*([a-z_]+)", r.get("hint") or "")
                    src_tpl = m.group(1) if m else ""
                    src = ctx.get("full_by_template", {}).get(src_tpl)
                    if src:
                        ru = src["ru"]
                        zh = src["zh"]
                        tag = "复习回顾"
                    elif ctx.get("last_full"):
                        ru = ctx["last_full"]
                        zh = str(ctx.get("last_full_zh") or "").strip()
                        tag = "复习回顾"
                else:
                    if ru:
                        ctx["last_full"] = ru
                        ctx["last_full_zh"] = zh
                        ctx["full_by_template"][tpl] = {"ru": ru, "zh": zh}
                        if tpl in self._SLOT_TABLE_NEG_TEMPLATES:
                            ctx["last_neg"] = ru
                            if tpl in ("negation", "object_neg", "predicate_neg"):
                                ctx["last_neg_base"] = ru
                        else:
                            ctx["last_affirm"] = ru
                            if tpl in ("skeleton", "object_pos", "predicate_pos"):
                                ctx["last_base"] = ru
                        if tpl in ("evaluation", "degree", "evaluation_ext", "not"):
                            ctx["last_eval"] = ru
            out_rows.append({"seq": len(out_rows) + 1, "cardType": r["cardType"], "ru": ru, "zh": zh, "tag": tag, "groupId": r["groupId"]})
        # 6.5) 骨架完整句防御：第一完整句必须逐字符 == 原句（数字俄语化后比较），否则回写机器值
        sk_ru = ""
        for row in out_rows:
            if row["cardType"] == "完整句":
                sk_ru = row["ru"]
                break
        if sk_ru and sk_ru != russian_text:
            sk_ru2 = " ".join(tokens)
            for row in out_rows:
                if row["cardType"] == "完整句":
                    row["ru"] = sk_ru2
                    break
        # 6.6) 同组完整句互重 / 变体重复原句 检测（机器拼装天然不重；if/so 由 AI 填 → 重填 1 次 → 仍重 → fallback dup_full）
        seen_in_group = {}
        dup_idx = []
        first_full_seen = False
        for i, row in enumerate(out_rows):
            if row["cardType"] != "完整句":
                continue
            if not first_full_seen:
                # 第一完整句 = 骨架行（=原句），作基准不入 dup 检测
                first_full_seen = True
                s = seen_in_group.setdefault(row["groupId"], set())
                s.add(row["ru"])
                continue
            s = seen_in_group.setdefault(row["groupId"], set())
            if row["ru"] in s or row["ru"] == russian_text:
                dup_idx.append(i)
            s.add(row["ru"])
        if dup_idx:
            retried = self._slot_table_retry_dup(prefilled, out_rows, dup_idx, russian_text)
            if retried is None:
                return self._json(200, {"ok": False, "fallback": True, "reason": "dup_full"})
            out_rows = retried
        # 7) 写缓存（幂等 upsert）
        rows_json = json.dumps(out_rows, ensure_ascii=False)

        def _w():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    pid = "slott_" + hashlib.md5((sentence_hash + "|" + difficulty + "|" + intents_fp).encode("utf-8")).hexdigest()[:20]
                    cur.execute(
                        "INSERT INTO sentence_slot_tables (id, sentence_hash, difficulty, sentence, intents_fp, `rows`, review_status, prompt_v, created_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,'ok',%s,%s) "
                        "ON DUPLICATE KEY UPDATE `rows`=VALUES(`rows`), review_status='ok', prompt_v=VALUES(prompt_v)",
                        (pid, sentence_hash, difficulty, russian_text, intents_fp, rows_json, SLOT_TABLE_PROMPT_V, int(time.time() * 1000)))
                    conn.commit()
            finally:
                conn.close()
        try:
            _seg_execute(_w)
        except Exception as e:
            print("[slot_table] 写缓存失败：", e)
        return self._json(200, {"ok": True, "rows": out_rows})

    def _handle_admin_slot_tables_save(self, data):
        """POST /api/admin/slot-tables/save —— 课时维度持久化 6 列表格（批量 replace 语义）：
        事务内 DELETE 该 unit 全部旧行 + INSERT 新行（幂等，与 segments save 同款）。
        入参：{course_id, unit_id, items:[{sentence_hash, sentence, difficulty, intents_fp, rows, review_status}]}"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        unit_id = str(data.get("unit_id") or "").strip()
        items = data.get("items")
        if not course_id or not unit_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id / unit_id"})
        if not isinstance(items, list) or not items:
            return self._json(400, {"ok": False, "error": "items 为空（应为 [句×档] 数组）"})
        cleaned = []
        for it in items:
            if not isinstance(it, dict):
                continue
            sh = str(it.get("sentence_hash") or "").strip()
            diff = str(it.get("difficulty") or "").strip()
            rows = it.get("rows")
            if not sh or diff not in ("easy", "medium", "hard") or not isinstance(rows, list) or not rows:
                continue
            cleaned.append({
                "sentence_hash": sh,
                "sentence": str(it.get("sentence") or "")[:1000],
                "difficulty": diff,
                "intents_fp": str(it.get("intents_fp") or "")[:16],
                "rows": rows,
                "review_status": str(it.get("review_status") or "ok")[:16] or "ok",
            })
        if not cleaned:
            return self._json(400, {"ok": False, "error": "无有效条目（rows 必须是非空数组）"})

        def _w():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    # ⚠️ 2026-10-06 修复：不再整课时 DELETE —— 只覆盖本次 items 涉及的 (sentence_hash, difficulty)，
                    # 保留本次未生成（网络/LLM 失败）的难度旧记录，避免「补跑只成功一个难度 → 其余被删成未生成」。
                    seen = set()
                    for it in cleaned:
                        k = (it["sentence_hash"], it["difficulty"])
                        if k in seen:
                            continue
                        seen.add(k)
                        cur.execute(
                            "DELETE FROM sentence_slot_unit_tables WHERE course_id=%s AND unit_id=%s AND sentence_hash=%s AND difficulty=%s",
                            (course_id, unit_id, it["sentence_hash"], it["difficulty"]))
                    pid = str(uuid.uuid4())
                    for it in cleaned:
                        pid = str(uuid.uuid4())
                        cur.execute(
                            "INSERT INTO sentence_slot_unit_tables (id, course_id, unit_id, sentence_hash, sentence, difficulty, intents_fp, `rows`, review_status, prompt_v, created_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                            "ON DUPLICATE KEY UPDATE `rows`=VALUES(`rows`), review_status=VALUES(review_status), prompt_v=VALUES(prompt_v)",
                            (pid, course_id, unit_id, it["sentence_hash"], it["sentence"], it["difficulty"], it["intents_fp"],
                             json.dumps(it["rows"], ensure_ascii=False), it["review_status"], SLOT_TABLE_PROMPT_V, int(time.time() * 1000)))
                    conn.commit()
            finally:
                conn.close()
        try:
            _seg_execute(_w)
        except Exception as e:
            print("[slot_tables] 保存失败：", e)
            return self._json(500, {"ok": False, "error": "保存表格失败（数据库不可用）"})
        self._log_op(data, "slot_tables_save", "unit", unit_id, {"course_id": course_id, "saved": len(cleaned)})
        return self._json(200, {"ok": True, "saved": len(cleaned)})

    # ========== 阶段A：整课生成接口 ==========
    def _handle_admin_course_generate(self, data):
        """POST /api/admin/course/generate —— 整课生成（新引擎分层编排）。
        入参：{course_id, sentences: [{ru, zh}]}
        出参：{ok, success, total_groups, total_steps, engine}"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        sentences = data.get("sentences") or []
        if not course_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id"})
        if not isinstance(sentences, list) or not sentences:
            return self._json(400, {"ok": False, "error": "sentences 为空"})

        # 调用新引擎
        try:
            from course_engine.generate import generate_chapter_course
            result = generate_chapter_course(sentences)
        except Exception as e:
            print(f"[course_gen] new engine exception: {e}")
            return self._json(500, {"ok": False, "success": False, "error": f"新引擎异常: {str(e)}"})

        if not result["success"]:
            print(f"[course_gen] engine=new, course={course_id}, success=False, error={result['error']}")
            return self._json(200, {"ok": True, "success": False, "error": result["error"], "engine": "new"})

        steps = result["steps"]
        total_groups = result.get("total_groups", 0)
        total_steps = len(steps)

        # 写入数据库：先删旧数据，再插新数据
        def _w():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM course_steps WHERE course_id=%s", (course_id,))
                    for s in steps:
                        cur.execute(
                            "INSERT INTO course_steps (course_id, seq, gid, step_type, ru, zh, tag, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (course_id, s["seq"], s["gid"], s["type"], s["ru"], s["zh"], s.get("tag", ""), int(time.time() * 1000))
                        )
                    conn.commit()
            finally:
                conn.close()

        try:
            _seg_execute(_w)
        except Exception as e:
            print(f"[course_gen] 写数据库失败: {e}")
            return self._json(500, {"ok": False, "success": False, "error": f"写数据库失败: {str(e)}"})

        print(f"[course_gen] engine=new, course={course_id}, sentences={len(sentences)}, groups={total_groups}, steps={total_steps}")
        self._log_op(data, "course_generate", "course", course_id, {"sentences": len(sentences), "steps": total_steps})

        return self._json(200, {
            "ok": True,
            "success": True,
            "course_id": course_id,
            "total_groups": total_groups,
            "total_steps": total_steps,
            "engine": "new"
        })

    def _handle_admin_course_steps(self, data):
        """GET /api/admin/course/steps?course_id=xxx —— 查询已生成的课程步骤"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        if not course_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id"})

        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT seq, gid, step_type, ru, zh, tag FROM course_steps WHERE course_id=%s ORDER BY seq ASC", (course_id,))
                    rows = cur.fetchall()
                    return [{"seq": r[0], "gid": r[1], "type": r[2], "ru": r[3], "zh": r[4], "tag": r[5]} for r in rows]
            finally:
                conn.close()

        try:
            steps = _seg_execute(_q)
        except Exception as e:
            print(f"[course_steps] 查询失败: {e}")
            return self._json(500, {"ok": False, "error": "查询失败"})

        return self._json(200, {"ok": True, "course_id": course_id, "total_steps": len(steps), "steps": steps})

    def _handle_admin_course_generate_async(self, data):
        """POST /api/admin/course/generate-async —— 异步整课生成。
        立刻返回 task_id，后台线程跑生成任务。
        入参：{course_id, unit_id, sentences: [{ru, zh}]}
        出参：{ok, task_id, status}"""
        err = self._require_admin(data)
        if err:
            return err
        course_id = str(data.get("course_id") or "").strip()
        unit_id = str(data.get("unit_id") or "").strip()
        sentences = data.get("sentences") or []
        if not course_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id"})
        if not isinstance(sentences, list) or not sentences:
            return self._json(400, {"ok": False, "error": "sentences 为空"})

        # 生成 task_id
        task_id = "task_" + uuid.uuid4().hex[:16]
        now_ms = int(time.time() * 1000)

        # 写入任务记录
        def _create_task():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO generation_tasks (task_id, course_id, unit_id, status, progress, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (task_id, course_id, unit_id, "pending", json.dumps({"classified_count": 0, "total": len(sentences)}), now_ms, now_ms)
                    )
                conn.commit()
            finally:
                conn.close()

        try:
            _seg_execute(_create_task)
        except Exception as e:
            print(f"[gen_task] 创建任务失败: {e}")
            return self._json(500, {"ok": False, "error": "创建任务失败"})

        # 后台线程跑生成任务
        def _run_task():
            try:
                # 更新状态：classifying
                self._update_task_status(task_id, "classifying", {"classified_count": 0, "total": len(sentences)})

                # 调用新引擎生成
                from course_engine.generate import generate_chapter_course_async
                result = generate_chapter_course_async(
                    sentences,
                    on_progress=lambda classified_count: self._update_task_status(
                        task_id, "classifying", {"classified_count": classified_count, "total": len(sentences)}
                    )
                )

                if not result["success"]:
                    self._update_task_status(task_id, "failed", error=result.get("error", "未知错误"))
                    return

                # 更新状态：done，存结果
                self._update_task_status(task_id, "done", result=result)

            except Exception as e:
                print(f"[gen_task] 任务异常: {task_id}, {e}")
                self._update_task_status(task_id, "failed", error=str(e))

        threading.Thread(target=_run_task, daemon=True).start()

        return self._json(200, {
            "ok": True,
            "task_id": task_id,
            "status": "pending"
        })

    def _handle_admin_course_task_status(self, data):
        """GET /api/admin/course/task-status?task_id=xxx —— 查询任务状态"""
        err = self._require_admin(data)
        if err:
            return err
        task_id = str(data.get("task_id") or "").strip()
        if not task_id:
            return self._json(400, {"ok": False, "error": "缺少 task_id"})

        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT task_id, status, progress, result, error FROM generation_tasks WHERE task_id=%s", (task_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {
                        "task_id": row[0],
                        "status": row[1],
                        "progress": json.loads(row[2]) if row[2] else None,
                        "result": json.loads(row[3]) if row[3] else None,
                        "error": row[4],
                    }
            finally:
                conn.close()

        try:
            task = _seg_execute(_q)
        except Exception as e:
            print(f"[gen_task] 查询失败: {e}")
            return self._json(500, {"ok": False, "error": "查询失败"})

        if not task:
            return self._json(404, {"ok": False, "error": "任务不存在"})

        return self._json(200, {"ok": True, **task})

    def _update_task_status(self, task_id, status, progress=None, result=None, error=None):
        """更新任务状态（内部用）"""
        now_ms = int(time.time() * 1000)
        def _u():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    sql = "UPDATE generation_tasks SET status=%s, updated_at=%s"
                    params = [status, now_ms]
                    if progress is not None:
                        sql += ", progress=%s"
                        params.append(json.dumps(progress))
                    if result is not None:
                        sql += ", result=%s"
                        params.append(json.dumps(result, ensure_ascii=False))
                    if error is not None:
                        sql += ", error=%s"
                        params.append(error)
                    sql += " WHERE task_id=%s"
                    params.append(task_id)
                    cur.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
        try:
            _seg_execute(_u)
        except Exception as e:
            print(f"[gen_task] 更新状态失败: {task_id}, {e}")

    def _handle_slot_tables_read(self, params):
        """GET /api/slot-tables?course_id=&unit_id=&difficulty=&include_pending=1 —— 公开读课时 6 列表格（学生端数据源）。
        默认只回 review_status='ok' 且 rows 非空的行；无 → items=[]（前端自动降级现有链路）。
        include_pending=1（后台校对页用）：回全部行（ok/pending/generating），rows 为空也回（区分"未生成"）。
        对外字段统一 status（映射自 review_status）；rows 按 seq 升序。"""
        course_id = (params.get("course_id", [""])[0] or "").strip()
        unit_id = (params.get("unit_id", [""])[0] or "").strip()
        diff = (params.get("difficulty", [""])[0] or "").strip()
        include_pending = (params.get("include_pending", ["0"])[0] or "0").strip() in ("1", "true", "yes")
        if not course_id or not unit_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id / unit_id"})
        if diff and diff not in ("easy", "medium", "hard"):
            return self._json(400, {"ok": False, "error": "difficulty 非法（easy|medium|hard）"})

        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    if include_pending:
                        if diff:
                            cur.execute("SELECT sentence_hash, sentence, difficulty, review_status, `rows` FROM sentence_slot_unit_tables "
                                        "WHERE course_id=%s AND unit_id=%s AND difficulty=%s "
                                        "ORDER BY sentence_hash, difficulty", (course_id, unit_id, diff))
                        else:
                            cur.execute("SELECT sentence_hash, sentence, difficulty, review_status, `rows` FROM sentence_slot_unit_tables "
                                        "WHERE course_id=%s AND unit_id=%s "
                                        "ORDER BY sentence_hash, difficulty", (course_id, unit_id))
                    else:
                        if diff:
                            cur.execute("SELECT sentence_hash, sentence, difficulty, review_status, `rows` FROM sentence_slot_unit_tables "
                                        "WHERE course_id=%s AND unit_id=%s AND difficulty=%s AND review_status='ok' "
                                        "ORDER BY sentence_hash, difficulty", (course_id, unit_id, diff))
                        else:
                            cur.execute("SELECT sentence_hash, sentence, difficulty, review_status, `rows` FROM sentence_slot_unit_tables "
                                        "WHERE course_id=%s AND unit_id=%s AND review_status='ok' "
                                        "ORDER BY sentence_hash, difficulty", (course_id, unit_id))
                    return cur.fetchall()
            finally:
                conn.close()
        try:
            rows = _seg_execute(_q)
        except Exception as e:
            print("[slot-tables] 读取失败：", e)
            return self._json(500, {"ok": False, "error": "读取表格失败（数据库不可用）"})
        groups = {}
        for r in rows:
            if not include_pending and r[3] != "ok":
                continue  # 防御：SQL 已过滤，代码层再兜一道（pending/generating 不进学生端）
            if diff and r[2] != diff:
                continue  # 防御：difficulty 过滤（假 DB/竞态下 SQL 未生效时兜底）
            # ⚠️ 2026-10-06 根因修复：key 必须含 difficulty —— 同一句子的初/中/高 3 条记录 sentence_hash 相同，
            # 只用 hash 作 key 会互相覆盖，read 只剩 1 档（用户看到"只生成一个级"的真根因）
            key = f"{r[0]}::{r[2]}"
            parsed = []
            try:
                parsed = json.loads(r[4]) if isinstance(r[4], str) else (r[4] or [])
            except Exception:
                parsed = []
            parsed = [p for p in parsed if isinstance(p, dict)]
            if not include_pending and not parsed:
                continue
            parsed.sort(key=lambda p: int(p.get("seq") or 0))
            groups[key] = {"sentence_hash": r[0], "sentence": r[1], "difficulty": r[2], "status": r[3], "rows": parsed}
        return self._json(200, {"ok": True, "items": list(groups.values())})

    def _handle_segments_read(self, params):
        """GET /api/segments?course_id=&unit_id= —— 公开读课时语块（按句+难度分组，供连词成句练习页）。
        对外字段统一 status（映射自 review_status）；占位行（未生成）→ status='generating'、segments=[]；
        每句附全局 translation（LEFT JOIN cache）。"""
        course_id = (params.get("course_id", [""])[0] or "").strip()
        unit_id = (params.get("unit_id", [""])[0] or "").strip()
        if not course_id or not unit_id:
            return self._json(400, {"ok": False, "error": "缺少 course_id / unit_id"})
        def _q():
            conn = _quest_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT s.sentence_hash, s.difficulty, s.sort_order, s.text, s.type, s.chinese, s.review_status, COALESCE(c.translation,'') "
                                "FROM sentence_segments s LEFT JOIN sentence_segment_cache c ON c.id = s.cache_id "
                                "WHERE s.course_id=%s AND s.unit_id=%s ORDER BY s.sentence_hash, s.difficulty, s.sort_order", (course_id, unit_id))
                    return cur.fetchall()
            finally:
                conn.close()
        try:
            rows = _seg_execute(_q)
        except Exception as e:
            print("[segments] 读取失败：", e)
            return self._json(500, {"ok": False, "error": "读取语块失败（数据库不可用）"})
        groups = {}
        for r in rows:
            key = (r[0], r[1])
            if key not in groups:
                groups[key] = {"sentence_hash": r[0], "difficulty": r[1], "status": r[6], "translation": r[7], "segments": []}
            if r[3] or r[4] != "pending_placeholder":
                groups[key]["segments"].append({"sort_order": r[2], "text": r[3], "type": r[4], "chinese": r[5]})
        for g in groups.values():
            if not g["segments"] and g["status"] == "ok":
                # 理论不发生：占位行 status 是 generating；防御性视为未生成
                g["status"] = "generating"
        return self._json(200, {"ok": True, "items": list(groups.values())})

    def _handle_admin_user_status(self, data):
        err = self._require_admin(data)
        if err:
            return err
        uid = str(data.get("id") or "").strip()
        try:
            status = 1 if int(data.get("status")) else 0
        except (TypeError, ValueError):
            return self._json(400, {"ok": False, "error": "状态无效（应为 0 或 1）"})
        if not uid:
            return self._json(400, {"ok": False, "error": "缺少用户 id"})
        target = _auth_get_user_by_id(uid)
        if not target:
            return self._json(404, {"ok": False, "error": "用户不存在"})
        ident = self._auth_identity(data)
        if ident and ident.get("id") and ident.get("id") == uid and status == 0:
            return self._json(400, {"ok": False, "error": "不能禁用自己（防止锁死后台）"})
        if target.get("role") == "admin" and status == 0:
            if _auth_count_role("admin") <= 1:
                return self._json(400, {"ok": False, "error": "系统至少保留一名启用状态的管理员"})
        if _auth_update_user_status(uid, status) is not True:
            return self._json(500, {"ok": False, "error": "更新状态失败"})
        self._log_op(data, "user_status_update", "user", uid,
                     {"status": status, "username": target.get("username")})
        return self._json(200, {"ok": True})

    def _handle_admin_user_reset_password(self, data):
        err = self._require_admin(data)
        if err:
            return err
        uid = str(data.get("id") or "").strip()
        if not uid:
            return self._json(400, {"ok": False, "error": "缺少用户 id"})
        target = _auth_get_user_by_id(uid)
        if not target:
            return self._json(404, {"ok": False, "error": "用户不存在"})
        new_password = str(data.get("new_password") or "")
        if new_password:
            if len(new_password) < 6:
                return self._json(400, {"ok": False, "error": "新密码至少 6 位"})
        else:
            new_password = secrets.token_urlsafe(9)  # 未指定则随机生成 12 位
        new_hash = hash_password(new_password)
        if _auth_reset_user_password(uid, new_hash) is not True:
            return self._json(500, {"ok": False, "error": "重置密码失败"})
        self._log_op(data, "user_password_reset", "user", uid,
                     {"username": target.get("username")})
        return self._json(200, {"ok": True, "new_password": new_password})

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
            self._log_op(data, "upload_presign", "b2_object", key, {"kind": kind, "filename": filename})
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

    def _handle_videos_sync(self, data):
        """投稿名单写入 B2（videos/index.json）。所有访客通过 GET /api/videos/list 读到。"""
        err = self._check_admin(data)
        if err:
            return err
        if not _b2_configured():
            return self._json(500, {"ok": False, "error": "B2 未配置"})
        videos = data.get("videos")
        if not isinstance(videos, list):
            return self._json(400, {"ok": False, "error": "videos 必须是数组"})
        try:
            client = _get_b2()
            body = json.dumps(videos, ensure_ascii=False).encode("utf-8")
            client.put_object(
                Bucket=_B2_BUCKET, Key="videos/index.json",
                Body=io.BytesIO(body), ContentType="application/json",
            )
            self._log_op(data, "videos_sync", "videos_index", None, {"count": len(videos)})
            return self._json(200, {"ok": True, "count": len(videos)})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "名单同步失败：" + str(e)})

    def _handle_videos_list(self):
        """读取 B2 上的投稿名单（无需密钥，所有访客可读）。"""
        if not _b2_configured():
            return self._json(200, {"ok": True, "videos": []})
        try:
            client = _get_b2()
            obj = client.get_object(Bucket=_B2_BUCKET, Key="videos/index.json")
            raw = obj["Body"].read().decode("utf-8")
            videos = json.loads(raw)
            if not isinstance(videos, list):
                videos = []
            for v in videos:
                if isinstance(v, dict) and v.get("videoUrl"):
                    v["videoUrl"] = _b2_resolve(v["videoUrl"])
                if isinstance(v, dict) and v.get("thumbnail") and v["thumbnail"].startswith(_B2_PREFIX):
                    v["thumbnail"] = _b2_resolve(v["thumbnail"])
            return self._json(200, {"ok": True, "videos": videos})
        except Exception as e:
            return self._json(200, {"ok": True, "videos": [], "error": str(e)})

    # ---- 课程评价（B2 reviews/index.json，全网公开）----
    _REVIEW_LOCK = threading.Lock()
    _REVIEW_RATE = {}  # (courseId, ip) -> 上次提交时间，简易防刷

    def _reviews_load_all(self):
        """读取 B2 上的全部评价。"""
        if not _b2_configured():
            return []
        try:
            client = _get_b2()
            obj = client.get_object(Bucket=_B2_BUCKET, Key="reviews/index.json")
            raw = obj["Body"].read().decode("utf-8")
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _reviews_save_all(self, reviews):
        """整体写回 B2。"""
        if not _b2_configured():
            return False
        try:
            client = _get_b2()
            body = json.dumps(reviews, ensure_ascii=False).encode("utf-8")
            client.put_object(
                Bucket=_B2_BUCKET, Key="reviews/index.json",
                Body=io.BytesIO(body), ContentType="application/json",
            )
            return True
        except Exception:
            return False

    def _handle_reviews_list(self):
        """GET /api/reviews/list?courseId=xxx —— 所有访客可读。"""
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        course_id = (params.get("courseId", [""])[0] or "").strip()
        if not course_id:
            return self._json(400, {"ok": False, "error": "缺少 courseId"})
        try:
            reviews = self._reviews_load_all()
            mine = [r for r in reviews if r.get("courseId") == course_id]
            mine.sort(key=lambda r: r.get("time", 0), reverse=True)
            return self._json(200, {"ok": True, "reviews": mine})
        except Exception as e:
            return self._json(200, {"ok": True, "reviews": [], "error": str(e)})

    def _handle_reviews_submit(self, data):
        """POST /api/reviews/submit —— 所有人可提交（不做管理员校验）。"""
        course_id = str(data.get("courseId") or "").strip()
        name = str(data.get("name") or "").strip()[:20] or "匿名"
        text = str(data.get("text") or "").strip()
        rating = data.get("rating")
        try:
            rating = int(rating)
        except Exception:
            rating = 0
        if not course_id:
            return self._json(400, {"ok": False, "error": "缺少 courseId"})
        if not text:
            return self._json(400, {"ok": False, "error": "评价内容不能为空"})
        if len(text) > 500:
            return self._json(400, {"ok": False, "error": "评价最多 500 字"})
        if rating < 1 or rating > 5:
            return self._json(400, {"ok": False, "error": "评分需在 1-5 星之间"})
        # 简易防刷：同一课程同一 IP 60 秒内限 1 条
        ip = self.client_address[0] if self.client_address else "unknown"
        key = (course_id, ip)
        now = time.time()
        with self._REVIEW_LOCK:
            last = self._REVIEW_RATE.get(key, 0)
            if now - last < 60:
                return self._json(429, {"ok": False, "error": "提交太频繁，请稍后再试"})
            self._REVIEW_RATE[key] = now
        try:
            with self._REVIEW_LOCK:
                reviews = self._reviews_load_all()
                reviews.append({
                    "id": "r_" + str(int(now * 1000)),
                    "courseId": course_id,
                    "name": name,
                    "rating": rating,
                    "text": text,
                    "time": int(now * 1000),
                })
                ok = self._reviews_save_all(reviews)
            if not ok:
                return self._json(500, {"ok": False, "error": "存储失败，请稍后重试"})
            return self._json(200, {"ok": True, "id": "r_" + str(int(now * 1000))})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "提交失败：" + str(e)})

    def _handle_reviews_delete(self, data):
        """POST /api/reviews/delete —— 管理员删除评价（adminKey 校验）。"""
        err = self._check_admin(data)
        if err:
            return err
        rid = str(data.get("id") or "").strip()
        if not rid:
            return self._json(400, {"ok": False, "error": "缺少评价 id"})
        try:
            with self._REVIEW_LOCK:
                reviews = self._reviews_load_all()
                before = len(reviews)
                reviews = [r for r in reviews if str(r.get("id") or "") != rid]
                if len(reviews) == before:
                    return self._json(404, {"ok": False, "error": "评价不存在"})
                if not self._reviews_save_all(reviews):
                    return self._json(500, {"ok": False, "error": "存储失败"})
            self._log_op(data, "reviews_delete", "review", rid)
            return self._json(200, {"ok": True, "deleted": rid})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "删除失败：" + str(e)})

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
            self._log_op(data, "upload_file", "file", filename, {"content_type": content_type})
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
        if path == "/api/videos/list":
            return self._handle_videos_list()
        if path == "/api/segments":
            query = urllib.parse.urlparse(self.path).query
            return self._handle_segments_read(urllib.parse.parse_qs(query))
        if path == "/api/slot-tables":
            query = urllib.parse.urlparse(self.path).query
            return self._handle_slot_tables_read(urllib.parse.parse_qs(query))
        if path == "/api/admin/course/steps":
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            data = {"course_id": params.get("course_id", [""])[0], "adminKey": params.get("adminKey", [""])[0]}
            return self._handle_admin_course_steps(data)
        if path == "/api/admin/course/task-status":
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            data = {"task_id": params.get("task_id", [""])[0], "adminKey": params.get("adminKey", [""])[0]}
            return self._handle_admin_course_task_status(data)
        if path == "/api/reviews/list":
            return self._handle_reviews_list()
        if path == "/api/videos/resolve":
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            url = (params.get("url", [""])[0] or "").strip()
            return self._json(200, {"ok": True, "url": _b2_resolve(url)})
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
    {"word": "句中出现的俄语原词", "stressed": "带重音的同形（在重音元音后面加组合重音符号 ́，例如 приве́т；单音节词也要标）", "pos": "词性中文，如 名词/动词/代词/形容词/副词/前置词/连接词/数词/语气词", "mean": "该词在本句中的中文词义", "gender": "名词/代词/形容词的性（阳性/阴性/中性，动词/副词等无性写 无）", "grammar_case": "名词/代词/形容词的格（第一格/第二格/第三格/第四格/第五格/第六格，动词/副词等无格写 无）", "number": "数（单数/复数，不可数或不确定写 无）"}
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
                    "gender": str(w.get("gender", "") or "").strip(),
                    "grammar_case": str(w.get("grammar_case", "") or "").strip(),
                    "number": str(w.get("number", "") or "").strip(),
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
        print(f"[DEBUG] POST path: {path}")  # 调试打印
        data = self._read_json()
        try:
            if path == "/api/transcribe":
                return self._handle_transcribe(data)
            if path == "/api/auth/register":
                return self._handle_auth_register(data)
            if path == "/api/auth/login":
                return self._handle_auth_login(data)
            if path == "/api/auth/me":
                return self._handle_auth_me(data)
            if path == "/api/admin/users":
                return self._handle_admin_users_list(data)
            if path == "/api/admin/dashboard/stats":
                return self._handle_admin_dashboard_stats(data)
            if path == "/api/vip/plans":
                return self._handle_vip_plans(data)
            if path == "/api/vip/status":
                return self._handle_vip_status(data)
            if path == "/api/order/create":
                return self._handle_order_create(data)
            if path == "/api/order/status":
                return self._handle_order_status(data)
            if path == "/api/order/manual-pay":
                return self._handle_order_manual_pay(data)
            if path == "/api/admin/orders":
                return self._handle_admin_orders(data)
            if path == "/api/pay/wechat/notify":
                return self._handle_pay_wechat_notify(data)
            if path == "/api/categories/tree":
                return self._handle_categories_tree(data)
            if path == "/api/admin/categories/list":
                return self._handle_admin_categories_list(data)
            if path == "/api/admin/categories/save":
                return self._handle_admin_categories_save(data)
            if path == "/api/admin/categories/delete":
                return self._handle_admin_categories_delete(data)
            if path == "/api/settings/public":
                return self._handle_settings_public(data)
            if path == "/api/admin/settings/get":
                return self._handle_admin_settings_get(data)
            if path == "/api/admin/settings/save":
                return self._handle_admin_settings_save(data)
            if path == "/api/admin/users/role":
                return self._handle_admin_user_role(data)
            if path == "/api/admin/users/status":
                return self._handle_admin_user_status(data)
            if path == "/api/admin/users/reset-password":
                return self._handle_admin_user_reset_password(data)
            if path == "/api/admin/users/detail":
                return self._handle_admin_user_detail(data)
            if path == "/api/admin/segments/check":
                return self._handle_admin_segments_check(data)
            if path == "/api/admin/segments/save":
                return self._handle_admin_segments_save(data)
            if path == "/api/admin/segments/delete":
                return self._handle_admin_segments_delete(data)
            if path == "/api/admin/segments/pending":
                return self._handle_admin_segments_pending(data)
            if path == "/api/admin/segments/llm-segment":
                return self._handle_admin_segments_llm_segment(data)
            if path == "/api/admin/segments/plan":
                return self._handle_admin_segments_plan(data)
            if path == "/api/admin/segments/pool":
                return self._handle_admin_segments_pool(data)
            if path == "/api/admin/segments/table-fill":
                return self._handle_admin_segments_table_fill(data)
            if path == "/api/admin/slot-tables/save":
                return self._handle_admin_slot_tables_save(data)
            if path == "/api/admin/course/generate":
                return self._handle_admin_course_generate(data)
            if path == "/api/admin/course/generate-async":
                return self._handle_admin_course_generate_async(data)
            if path == "/api/admin/course/task-status":
                return self._handle_admin_course_task_status(data)
            if path == "/api/admin/course/steps":
                return self._handle_admin_course_steps(data)
            if path == "/api/admin/segments/update":
                return self._handle_admin_segments_update(data)
            if path == "/api/learning/progress/save":
                return self._handle_learning_progress_save(data)
            if path == "/api/learning/progress":
                return self._handle_learning_progress_get(data)
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
            if path == "/api/videos/sync":
                return self._handle_videos_sync(data)
            if path == "/api/reviews/submit":
                return self._handle_reviews_submit(data)
            if path == "/api/reviews/delete":
                return self._handle_reviews_delete(data)
            if path == "/api/upload":
                return self._handle_upload(data)
            if path == "/api/generate-quiz":
                return self._handle_generate_quiz(data)
            if path == "/api/grade-quiz":
                return self._handle_grade_quiz(data)
            if path == "/api/course-split":
                return self._handle_course_split(data)
            if path == "/api/course-tag":
                return self._handle_course_tag(data)
            if path == "/api/course-lesson-gen":
                return self._handle_course_lesson_gen(data)
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
    _auth_init()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
