import hashlib
import logging

from deep_translator import GoogleTranslator
from langdetect import LangDetectException, detect

logger = logging.getLogger(__name__)


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _get_cached(conn, text):
    row = conn.execute(
        "SELECT translated FROM translations WHERE text_hash = ?",
        (_hash(text),),
    ).fetchone()
    return row["translated"] if row else None


def _cache(conn, original, translated, lang_from):
    conn.execute(
        "INSERT OR IGNORE INTO translations (text_hash, original, translated, lang_from) VALUES (?, ?, ?, ?)",
        (_hash(original), original, translated, lang_from),
    )
    conn.commit()


def translate_text(conn, text):
    if not text or not text.strip():
        return text, None
    try:
        lang = detect(text)
    except LangDetectException:
        return text, None
    if lang in ("es", "en"):
        return text, lang
    cached = _get_cached(conn, text)
    if cached:
        return cached, lang
    try:
        translated = GoogleTranslator(source="auto", target="es").translate(text)
        _cache(conn, text, translated, lang)
        return translated, lang
    except Exception as exc:
        logger.error("Translation error: %s", exc)
        return text, lang


def translate_article(conn, article):
    translated_title, _ = translate_text(conn, article["title_orig"])
    article["title"] = translated_title
    if article.get("summary"):
        translated_summary, _ = translate_text(conn, article["summary"][:300])
        article["summary"] = translated_summary
    return article
