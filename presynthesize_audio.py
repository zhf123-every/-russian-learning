"""
预合成所有题目和单词的俄语发音（Yandex SpeechKit）
用法：python presynthesize_audio.py
"""
import os
import sys
import time
import hashlib
import urllib.request
import urllib.parse

# 加载 .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.isfile(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import pymysql

YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "")
YANDEX_TTS_VOICE = os.environ.get("YANDEX_TTS_VOICE", "alena")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), "audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)


def parse_db_url(url):
    """解析 mysql://user:pass@host:port/db"""
    url = url.replace("mysql://", "")
    user_pass, host_port_db = url.split("@", 1)
    user, password = user_pass.split(":", 1)
    host_port, db = host_port_db.rsplit("/", 1)
    host, port = host_port.split(":", 1)
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "database": db,
    }


def synthesize_yandex(text, voice=None):
    """调用 Yandex SpeechKit 合成音频，返回本地文件路径"""
    if not YANDEX_API_KEY:
        print("  [跳过] 未配置 YANDEX_API_KEY")
        return None
    if not text or not text.strip():
        return None
    voice = voice or YANDEX_TTS_VOICE

    cache_key = hashlib.md5(f"yandex_{text}_{voice}".encode("utf-8")).hexdigest()
    cache_file = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.mp3")

    if os.path.isfile(cache_file):
        return cache_file

    try:
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
                print(f"  [失败] API返回异常: {audio_data[:200]}")
                return None
            with open(cache_file, "wb") as f:
                f.write(audio_data)
            return cache_file
    except Exception as e:
        print(f"  [失败] {e}")
        return None


def main():
    if not DATABASE_URL:
        print("错误：未配置 DATABASE_URL")
        sys.exit(1)
    if not YANDEX_API_KEY:
        print("错误：未配置 YANDEX_API_KEY")
        sys.exit(1)

    db_config = parse_db_url(DATABASE_URL)
    print(f"连接数据库: {db_config['host']}:{db_config['port']}/{db_config['database']}")

    conn = pymysql.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        ssl={"ssl": {"ca": None}},
        charset="utf8mb4",
    )

    try:
        with conn.cursor() as cur:
            # 1. 预合成所有句子
            cur.execute("SELECT id, russian FROM quest_statements WHERE russian IS NOT NULL AND russian != ''")
            statements = cur.fetchall()
            print(f"\n=== 预合成句子（共 {len(statements)} 条）===")

            stmt_ok = 0
            for i, (stmt_id, russian) in enumerate(statements, 1):
                # 去掉末尾标点用于发音（Yandex 会自动处理）
                text = russian.strip()
                print(f"[{i}/{len(statements)}] {text[:50]}...", end=" ")

                cache_file = synthesize_yandex(text)
                if cache_file:
                    audio_url = f"/audio_cache/{os.path.basename(cache_file)}"
                    cur.execute("UPDATE quest_statements SET audio_url=%s WHERE id=%s", (audio_url, stmt_id))
                    stmt_ok += 1
                    print("✓")
                else:
                    print("✗")
                time.sleep(0.2)  # 避免请求过快

            conn.commit()
            print(f"句子合成完成：{stmt_ok}/{len(statements)} 成功")

            # 2. 预合成所有单词
            cur.execute("SELECT id, form, lemma FROM quest_words WHERE (form IS NOT NULL AND form != '') OR (lemma IS NOT NULL AND lemma != '')")
            words = cur.fetchall()
            print(f"\n=== 预合成单词（共 {len(words)} 个）===")

            word_ok = 0
            for i, (word_id, form, lemma) in enumerate(words, 1):
                # 优先用 form（带重音），其次 lemma
                text = (form or lemma or "").strip()
                # 去掉重音符号用于发音（Yandex 自动处理重音）
                text_clean = text.replace("́", "").replace("̀", "")
                if not text_clean:
                    continue
                print(f"[{i}/{len(words)}] {text_clean}", end=" ")

                cache_file = synthesize_yandex(text_clean)
                if cache_file:
                    audio_url = f"/audio_cache/{os.path.basename(cache_file)}"
                    cur.execute("UPDATE quest_words SET audio_url=%s WHERE id=%s", (audio_url, word_id))
                    word_ok += 1
                    print("✓")
                else:
                    print("✗")
                time.sleep(0.15)

            conn.commit()
            print(f"单词合成完成：{word_ok}/{len(words)} 成功")

            print(f"\n=== 全部完成 ===")
            print(f"句子：{stmt_ok}/{len(statements)}")
            print(f"单词：{word_ok}/{len(words)}")
            print(f"音频缓存目录：{AUDIO_CACHE_DIR}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
