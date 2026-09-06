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

PORT = int(os.environ.get("PORT", "8000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")

# AI 中转配置（密钥/地址从环境变量读取，前端不再持有密钥）
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.deepseek.com")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "deepseek-chat")

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
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_OK = True
except Exception:
    _PSYCOPG2_OK = False


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
    """MyMemory 免费翻译接口（俄→中），无需 key。返回译文文本或 None。"""
    q = urllib.parse.quote(word)
    url = "https://api.mymemory.translated.net/get?q=%s&langpair=ru|zh-CN" % q
    status, body = http_call("GET", url, timeout=30)
    if status == 200:
        try:
            obj = json.loads(body)
            return obj.get("responseData", {}).get("translatedText") or None
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


# ---- 音频转写（用本地 faster-whisper 做俄语语音识别）----
# faster-whisper 是 CTranslate2 版的 Whisper，纯本地、离线、无需 key，
# 俄语识别质量好、CPU 可跑。其依赖的 PyAV 直接解码视频里的音频轨，
# 因此无需单独安装系统 ffmpeg。安装：pip install faster-whisper
try:
    from faster_whisper import WhisperModel as _WhisperModel
    _WHISPER_OK = True
except Exception:  # 未安装或导入失败
    _WHISPER_OK = False

_whisper_model = None
_whisper_model_name = None


def get_whisper_model(name):
    """懒加载 + 单例缓存：模型只加载一次，切换模型名时重新加载。"""
    global _whisper_model, _whisper_model_name
    if _whisper_model is None or _whisper_model_name != name:
        _whisper_model = _WhisperModel(name, device="cpu", compute_type="int8")
        _whisper_model_name = name
    return _whisper_model


def _merge_tiny_segments(segs):
    """轻量清理：把极短碎片（<3 字符且与上一段间隔很近）并入上一段，其余保持 Whisper 原样。"""
    out = []
    for s in segs:
        if len(s["text"].strip()) < 3 and out and (s["start"] - out[-1]["end"]) < 0.5:
            out[-1]["end"] = s["end"]
            out[-1]["text"] = (out[-1]["text"] + " " + s["text"]).strip()
        else:
            out.append(s)
    return out


def transcribe_file(path, model_name="tiny"):
    """把视频/音频文件转写成俄语句子列表。返回 (segments, error)，error 为 None 表示成功。
    segments 每项 {start, end, text}（秒）。"""
    if not _WHISPER_OK:
        return None, "未安装 faster-whisper。请运行：python -m pip install faster-whisper"
    try:
        model = get_whisper_model(model_name)
        segments, _info = model.transcribe(
            path, language="ru", word_timestamps=True, vad_filter=True
        )
        out = []
        for s in segments:
            t = s.text.strip()
            if not t:
                continue
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": t})
        if not out:
            return [], "未识别到俄语语音（可能没有音频轨，或内容不是俄语）"
        return _merge_tiny_segments(out), None
    except Exception as e:
        return None, "转写失败：" + str(e)


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
    """调用 OpenAI 兼容接口（DeepSeek 等）。返回助手的文本回复。"""
    log_api_call("AI Chat", messages)
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": 0.4, "stream": False}
    headers = {"Authorization": "Bearer " + key}
    status, body = http_call("POST", url, payload, headers)
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


# 连接数据库前先自动修正地址
def _square_conn():
    fixed_url = _normalize_db_url(DATABASE_URL)
    return psycopg2.connect(fixed_url, sslmode="require")

def _square_init():
    if not (_PSYCOPG2_OK and DATABASE_URL):
        return
    try:
        conn = _square_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS square_items (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        level TEXT NOT NULL,
                        video_url TEXT,
                        description TEXT,
                        author TEXT,
                        thumbnail TEXT,
                        poster_url TEXT,
                        views INTEGER DEFAULT 0,
                        tags TEXT DEFAULT '[]',
                        sentences TEXT DEFAULT '[]',
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
        "videoUrl": row["video_url"] or "",
        "description": row["description"] or "",
        "author": row["author"] or "",
        "thumbnail": row["thumbnail"] or "",
        "posterUrl": row["poster_url"] or "",
        "views": row["views"] or 0,
        "tags": json.loads(row["tags"] or "[]"),
        "sentences": json.loads(row["sentences"] or "[]"),
        "createdAt": row["created_at"] or 0,
    }


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
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
        model = (data.get("model") or "tiny").strip()
        if model not in ("tiny", "base"):
            model = "tiny"
        if not url:
            return self._json(400, {"ok": False, "error": "缺少视频链接"})
        audio_path, err = download_audio(url)
        if err:
            return self._json(200, {"ok": False, "error": err})
        try:
            segs, err = transcribe_file(audio_path, model)
            if err:
                return self._json(200, {"ok": False, "error": err})
            return self._json(200, {"ok": True, "segments": segs})
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
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.send_response(502); self._cors(); self.end_headers()
            try:
                self.wfile.write("流式代理失败：未安装 ffmpeg（服务器需安装 ffmpeg）".encode("utf-8"))
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
        if not (_PSYCOPG2_OK and DATABASE_URL):
            return self._json(200, {"ok": True, "list": []})
        try:
            return self._json(200, {"ok": True, "list": _square_list()})
        except Exception as e:
            print("[square] 读取列表失败：", e)
            return self._json(200, {"ok": True, "list": []})

    def _handle_square_submit(self, data):
        err = self._check_admin(data)
        if err:
            return err
        if not (_PSYCOPG2_OK and DATABASE_URL):
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
        if not (_PSYCOPG2_OK and DATABASE_URL):
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
        if path == "/api/stream":
            return self._handle_stream()
        if path == "/api/square/list":
            return self._handle_square_list()

        # 优先服务 React 构建产物（dist/）；未构建时回退到 legacy.html
        serve_dir = DIST_DIR if os.path.isfile(os.path.join(DIST_DIR, "index.html")) else BASE_DIR
        if path == "/":
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
            ".txt": "text/plain",
        }.get(ext, "application/octet-stream")
        if "gzip" in self.headers.get("Accept-Encoding", "") and os.path.isfile(full + ".gz"):
            self._serve_file(full + ".gz", ctype, content_encoding="gzip")
        else:
            self._serve_file(full, ctype)

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
                    return self._json(400, {"ok": False, "error": "未配置 AI API Key（请在 Render 环境变量 AI_API_KEY 中设置）"})
                messages = [
                    {"role": "system", "content": "你是俄语老师。逐词解析这句俄语：原形、词性、语法功能、整句中文翻译。用简洁中文，适当用列表。"},
                    {"role": "user", "content": sentence},
                ]
                content = ai_chat(AI_BASE_URL, AI_API_KEY, AI_MODEL, messages)
                return self._json(200, {"ok": True, "content": content})
            if path == "/api/ai":
                base = (data.get("baseUrl") or AI_BASE_URL).strip()
                key = (data.get("key") or AI_API_KEY).strip()
                model = (data.get("model") or AI_MODEL).strip()
                messages = data.get("messages") or []
                if not key:
                    return self._json(400, {"ok": False, "error": "未配置 AI API Key（请在 Render 环境变量 AI_API_KEY 中设置）"})
                content = ai_chat(base, key, model, messages)
                return self._json(200, {"ok": True, "content": content})
            if path == "/api/upload":
                return self._handle_upload(data)
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
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    _square_init()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
