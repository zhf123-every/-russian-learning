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


# ---- 学习广场持久化（Postgres）----
def _normalize_db_url(url):
    """修正 Render 从 fromDatabase 注入的 DATABASE_URL 缺失端口问题。

    Render 的 fromDatabase.property=connectionString 有时返回
    postgres://user:pass@HOST/dbname 的简写形式，HOST 缺少 :5432 端口。
    libpq 会把裸 hostname 直接拿去做 DNS 解析，而 Render 内部 hostname
    （dpg-xxx-a）没有域名后缀时解析失败，报：
        could not translate host name "dpg-xxx-a" to address
    这里自动补上 :5432 端口，并确保 hostname 完整。
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
    port = parsed.port
    if port:
        return url  # 已有端口，无需处理
    # 补端口：5432
    if parsed.username:
        userinfo = "%s:%s@" % (parsed.username,
                              urllib.parse.quote(parsed.password or "", safe=""))
    else:
        userinfo = ""
    netloc = "%s%s:5432" % (userinfo, host)
    if parsed.path:
        path = parsed.path
    else:
        path = ""
    query = ("?" + parsed.query) if parsed.query else ""
    return "%s://%s%s%s" % (parsed.scheme, netloc, path, query)


# 数据库（学习广场投稿持久化，Render Postgres 提供 DATABASE_URL）
# Render 的 fromDatabase.property=connectionString 有时返回
# postgres://user:pass@HOST/dbname 的简写，HOST 缺少 :5432 端口。
# libpq 会把裸 hostname 直接拿去做 DNS 解析，而 Render 内部 hostname
# （dpg-xxx-a）没有域名后缀时解析失败，报 could not translate host name。
# 这里读取后立即规范化，自动补上默认端口 :5432。
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
            "-o", out_tmpl, url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if proc.returncode != 0:
            detail = (proc.stdout + "\n" + proc.stderr).strip()
            if "No module named" in detail:
                return None, "未安装 yt-dlp。请运行：python -m pip install yt-dlp"
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
        "-o", out_tmpl, url,
    ]
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
        return None, "下载音频失败：" + detail[-800:]
    files = [f for f in os.listdir(tmp)]
    if not files:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, "下载音频失败：没有找到音频文件"
    return os.path.join(tmp, files[0]), None


def resolve_stream(url):
    """用 yt-dlp 解析视频直链 + 请求头（B 站等需要 Referer 防盗链）。
    优先选单文件 mp4，便于做 Range 代理让 <video> 支持拖动进度条。
    返回 (直链 URL, 请求头 dict)；失败返回 (None, 错误信息)。"""
    try:
        import yt_dlp
    except Exception:
        return None, "未安装 yt-dlp。请运行：python -m pip install yt-dlp"
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "format": "best[ext=mp4]/best",  # 优先单文件 mp4，避免 HLS 分片代理复杂
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return None, "解析视频失败：" + str(e)[:300]
    formats = info.get("formats") or []
    chosen = None
    for f in formats:
        if f.get("protocol") not in ("m3u8", "m3u8_native") and f.get("url"):
            chosen = f
            break
    if chosen is None and formats:
        chosen = formats[0]
    if chosen is None:
        chosen = {"url": info.get("url")}
    direct = chosen.get("url")
    headers = chosen.get("http_headers") or info.get("http_headers") or {}
    if not direct:
        return None, "未找到可播放的视频流"
    return direct, headers


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


def transcribe_file(path, model_name="small"):
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

# ---- 自动修正数据库地址（补端口） ----
def _normalize_db_url(url):
    if not url:
        return url
    if not url.startswith(("postgres://", "postgresql://")):
        return url
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
    except Exception:
        return url
    
    host = parsed.hostname or ""
    port = parsed.port
    # 已经有端口就直接返回
    if port:
        return url
    
    # 没端口就补上PostgreSQL默认的5432端口
    if parsed.username:
        userinfo = f"{parsed.username}:{parsed.password}@"
    else:
        userinfo = ""
    
    netloc = f"{userinfo}{host}:5432"
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{netloc}{path}{query}"

# 连接数据库前先自动修正地址
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


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

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
        model = (data.get("model") or "small").strip()
        if model not in ("tiny", "base", "small", "medium"):
            model = "small"
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
        """流式代理：解析视频直链（B 站等）并转发给 <video>，支持 Range 拖动进度条。"""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        url = (qs.get("url") or [""])[0]
        if not url:
            self.send_response(400); self._cors(); self.end_headers(); return
        direct, headers = resolve_stream(url)
        if direct is None:
            self.send_response(502); self._cors(); self.end_headers()
            try:
                self.wfile.write(("流式代理失败：" + (headers or "")).encode("utf-8"))
            except Exception:
                pass
            return
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

    def _handle_square_list(self):
        if not (_PSYCOPG2_OK and DATABASE_URL):
            return self._json(200, {"ok": True, "list": []})
        try:
            return self._json(200, {"ok": True, "list": _square_list()})
        except Exception as e:
            print("[square] 读取列表失败：", e)
            return self._json(200, {"ok": True, "list": []})

    def _handle_square_submit(self, data):
        if not (_PSYCOPG2_OK and DATABASE_URL):
            return self._json(500, {"ok": False, "error": "未配置数据库（DATABASE_URL）"})
        if not (data.get("id") and data.get("title")):
            return self._json(400, {"ok": False, "error": "缺少必填字段"})
        try:
            _square_submit(data)
            return self._json(200, {"ok": True})
        except Exception as e:
            return self._json(500, {"ok": False, "error": "保存失败：" + str(e)})

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
