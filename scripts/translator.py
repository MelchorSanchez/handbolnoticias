import hashlib
import logging
import re

from deep_translator import GoogleTranslator
from langdetect import LangDetectException, detect

logger = logging.getLogger(__name__)

# IHF/EHF country codes used in French handball media (handnews.fr, etc.)
# Format: "HON | Club name..." where HON = Hongrie (French for Hungary)
_COUNTRY_CODES = {
    "HON": "Hungría", "HUN": "Hungría",
    "GER": "Alemania", "ALL": "Alemania",
    "FRA": "Francia",
    "SPA": "España", "ESP": "España",
    "POL": "Polonia",
    "CRO": "Croacia",
    "SLO": "Eslovenia",
    "DEN": "Dinamarca",
    "NOR": "Noruega",
    "SWE": "Suecia",
    "AUT": "Austria",
    "POR": "Portugal",
    "ROU": "Rumanía", "ROM": "Rumanía",
    "BIH": "Bosnia",
    "MKD": "Macedonia del Norte",
    "RUS": "Rusia",
    "BLR": "Bielorrusia",
    "UKR": "Ucrania",
    "NED": "Países Bajos",
    "BEL": "Bélgica",
    "SUI": "Suiza",
    "CZE": "República Checa",
    "SVK": "Eslovaquia",
    "SRB": "Serbia",
    "MNE": "Montenegro",
    "ISL": "Islandia",
    "TUN": "Túnez",
    "EGY": "Egipto",
    "MAR": "Marruecos",
    "QAT": "Catar",
    "BRN": "Baréin",
    "KSA": "Arabia Saudita",
    "ARG": "Argentina",
    "BRA": "Brasil",
    "CHI": "Chile",
    "URU": "Uruguay",
    "JPN": "Japón", "JAP": "Japón",
    "KOR": "Corea del Sur",
    "AUS": "Australia",
    "USA": "Estados Unidos",
    "CAN": "Canadá",
    "IRI": "Irán", "IRN": "Irán",
    "GRE": "Grecia",
    "ITA": "Italia",
    "TUR": "Turquía",
    "NIG": "Nigeria",
    "AGO": "Angola",
    "CPV": "Cabo Verde",
}

# Pattern: "HON | " or "Hon | " or "HON: " at start of title (handnews.fr style)
_COUNTRY_PREFIX_RE = re.compile(r"^([A-Za-z]{2,4})\s*[|:]\s*")

# Known section/column names that are proper nouns and should not be translated.
# These appear as prefixes in article titles from certain sources.
_PRESERVE_PREFIXES = [
    "Proffskollen Dam",
    "Proffskollen Herr",
    "Proffskollen",
]


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


def _preprocess(text):
    """Extract parts of the title that must survive translation unchanged.

    Returns (prefix_es, core_text) where prefix_es is the already-Spanish
    prefix to prepend to the translated core, or None if there is no prefix.
    """
    # 1. Country code prefix: "HON | Ferencvaros..." → "Hungría | Ferencvaros..."
    m = _COUNTRY_PREFIX_RE.match(text)
    if m:
        code = m.group(1).upper()
        country = _COUNTRY_CODES.get(code, code)
        return f"{country} | ", text[m.end():]

    # 2. Known proper-noun section names at start of title
    text_lower = text.lower()
    for prefix in _PRESERVE_PREFIXES:
        if text_lower.startswith(prefix.lower()):
            rest = text[len(prefix):].lstrip(" :-–")
            return f"{prefix}: ", rest if rest else ""

    return None, text


def translate_text(conn, text):
    if not text or not text.strip():
        return text, None

    prefix_es, core = _preprocess(text)

    detect_text = core if (prefix_es and core) else text
    try:
        lang = detect(detect_text)
    except LangDetectException:
        return text, None

    if lang in ("es", "en"):
        if prefix_es:
            return prefix_es + core, lang
        return text, lang

    cached = _get_cached(conn, text)
    if cached:
        return cached, lang

    translate_target = core if prefix_es else text
    try:
        translated = GoogleTranslator(source="auto", target="es").translate(translate_target)
        result = (prefix_es + translated) if prefix_es else translated
        _cache(conn, text, result, lang)
        return result, lang
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
