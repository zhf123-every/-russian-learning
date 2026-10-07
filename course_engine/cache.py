import hashlib
import json
import os
import pymysql
from urllib.parse import urlparse


def _get_conn():
    """获取MySQL连接，和server.py用同一个DATABASE_URL"""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise Exception("DATABASE_URL 未配置")
    
    # 解析MySQL URL
    url = urlparse(db_url)
    params = {
        "host": url.hostname,
        "port": url.port or 3306,
        "user": url.username,
        "password": url.password,
        "database": url.path.lstrip("/"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }
    return pymysql.connect(**params)


def get_cache_key(ru_sentence):
    """生成缓存键：句子 ru 的 md5"""
    return hashlib.md5(ru_sentence.strip().encode("utf-8")).hexdigest()


def get_cached_classification(ru_sentence):
    """查缓存，返回 classification JSON，没有就返回 None"""
    key = get_cache_key(ru_sentence)
    conn = None
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT classification FROM sentence_classification_cache WHERE ru_hash = %s", (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row["classification"])
    except Exception as e:
        print(f"[cache] 查询失败: {e}", flush=True)
    finally:
        if conn:
            conn.close()
    return None


def save_classification_to_cache(ru_sentence, classification):
    """写入缓存"""
    key = get_cache_key(ru_sentence)
    conn = None
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sentence_classification_cache (ru_hash, ru, classification, created_at)
            VALUES (%s, %s, %s, UNIX_TIMESTAMP())
            ON DUPLICATE KEY UPDATE classification = VALUES(classification)
        """, (key, ru_sentence, json.dumps(classification, ensure_ascii=False)))
        conn.commit()
    except Exception as e:
        print(f"[cache] 写入失败: {e}", flush=True)
    finally:
        if conn:
            conn.close()
