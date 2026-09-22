import hashlib
import logging
import re

from deep_translator import GoogleTranslator
from langdetect import LangDetectException, detect

from audit_articles import GARBAGE_RE

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

# Native language of each top-level site section, used to override langdetect
# when it misreads a short foreign-language title as "es"/"en" (very common
# with short headlines in Icelandic, Polish, Swedish, etc.). Sections not
# listed here (e.g. "europe", "ihf") are left to langdetect alone.
_SECTION_LANG = {
    "france": "fr",
    "germany": "de",
    "portugal": "pt",
    "sweden": "sv",
    "norway": "no",
    "denmark": "da",
    "italy": "it",
    "croatia": "hr",
    "slovenia": "sl",
    "brazil": "pt",
    "poland": "pl",
    "austria": "de",
    "iceland": "is",
    "turkey": "tr",
    "czech-republic": "cs",
}


def _section_lang_hint(section):
    if not section:
        return None
    return _SECTION_LANG.get(section.split("/")[0])

# Known section/column names that are proper nouns and should not be translated.
# These appear as prefixes in article titles from certain sources.
_PRESERVE_PREFIXES = [
    "Proffskollen Dam",
    "Proffskollen Herr",
    "Proffskollen",
    "Proligue",
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


def translate_text(conn, text, source_lang_hint=None):
    if not text or not text.strip():
        return text, None

    prefix_es, core = _preprocess(text)

    detect_text = core if (prefix_es and core) else text
    try:
        lang = detect(detect_text)
    except LangDetectException:
        return text, None

    # langdetect is unreliable on short headlines: it often misreads a
    # foreign-language title as "es"/"en". If the source's known language
    # disagrees, don't trust the "es"/"en" verdict — attempt translation.
    trust_detection = not (
        lang in ("es", "en")
        and source_lang_hint
        and source_lang_hint not in ("es", "en")
    )

    if lang in ("es", "en") and trust_detection:
        if prefix_es:
            return prefix_es + core, lang
        return text, lang

    cached = _get_cached(conn, text)
    if cached:
        return cached, lang

    translate_target = core if prefix_es else text
    try:
        translated = GoogleTranslator(source="auto", target="es").translate(translate_target)
        if not translated or GARBAGE_RE.search(translated):
            logger.error("Translator devolvió una página de error, se descarta: %r", translate_target[:80])
            return text, lang
        result = (prefix_es + translated) if prefix_es else translated
        _cache(conn, text, result, lang)
        return result, lang
    except Exception as exc:
        logger.error("Translation error: %s", exc)
        return text, lang


def translate_article(conn, article):
    hint = _section_lang_hint(article.get("section"))
    translated_title, _ = translate_text(conn, article["title_orig"], hint)
    article["title"] = translated_title
    if article.get("summary"):
        translated_summary, _ = translate_text(conn, article["summary"][:300], hint)
        article["summary"] = translated_summary
    return article
