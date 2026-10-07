import hashlib
import json
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "russian_learning.db")


def get_cache_key(ru_sentence):
    """生成缓存键：句子 ru 的 md5"""
    return hashlib.md5(ru_sentence.strip().encode("utf-8")).hexdigest()


def get_cached_classification(ru_sentence):
    """查缓存，返回 classification JSON，没有就返回 None"""
    key = get_cache_key(ru_sentence)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT classification FROM sentence_classification_cache WHERE ru_hash = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception as e:
        print(f"[cache] 查询失败: {e}", flush=True)
    return None


def save_classification_to_cache(ru_sentence, classification):
    """写入缓存"""
    key = get_cache_key(ru_sentence)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sentence_classification_cache (ru_hash, ru, classification, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (key, ru_sentence, json.dumps(classification, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[cache] 写入失败: {e}", flush=True)
