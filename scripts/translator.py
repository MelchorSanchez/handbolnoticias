import hashlib
import logging
import os
import re
import time
from pathlib import Path

import httpx
import yaml
from langdetect import LangDetectException, detect

from audit_articles import GARBAGE_RE

logger = logging.getLogger(__name__)

# Translations go through the official DeepL API. The free Google endpoint
# scraped by deep_translator started redirecting every request to Google's
# /sorry captcha page in late Sept 2026, so titles stopped being translated.
# The key comes from the DEEPL_API_KEY env var (GitHub secret in the Action)
# or, for local runs, from a DEEPL_API_KEY=... line in the repo's .env file.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Throttle to stay well below DeepL's rate limit; back off on 429 and, once
# retries are exhausted (or the monthly quota is used up, HTTP 456), trip a
# circuit breaker so the rest of the run fails fast (fallback to untranslated
# text) instead of hammering the API.
_MIN_INTERVAL = 0.5
_last_call_ts = 0.0
_RATE_LIMIT_RETRIES = 2
_RATE_LIMIT_BACKOFF = (5, 15)
_CIRCUIT_COOLDOWN = 120
_circuit_open_until = 0.0
_api_key = None


class _RateLimited(Exception):
    pass


class _QuotaExceeded(Exception):
    pass


def _get_api_key():
    global _api_key
    if _api_key is None:
        _api_key = os.environ.get("DEEPL_API_KEY", "").strip()
        if not _api_key and _ENV_FILE.exists():
            m = re.search(r'^DEEPL_API_KEY=\s*["\']?([^"\'\s]+)', _ENV_FILE.read_text(), re.M)
            _api_key = m.group(1) if m else ""
    return _api_key


def _deepl_translate(text):
    key = _get_api_key()
    if not key:
        raise RuntimeError("DEEPL_API_KEY no configurada")
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    resp = httpx.post(
        f"https://{host}/v2/translate",
        headers={"Authorization": f"DeepL-Auth-Key {key}"},
        json={"text": [text], "target_lang": "ES"},
        timeout=20,
    )
    if resp.status_code == 429:
        raise _RateLimited("DeepL: too many requests (HTTP 429)")
    if resp.status_code == 456:
        raise _QuotaExceeded("DeepL: cuota mensual agotada (HTTP 456)")
    resp.raise_for_status()
    result = resp.json()["translations"][0]
    return result["text"], result.get("detected_source_language", "").lower()


def _throttled_translate(target):
    global _last_call_ts, _circuit_open_until
    if time.monotonic() < _circuit_open_until:
        raise RuntimeError("Translator circuit breaker open (rate-limited recently)")
    for attempt in range(_RATE_LIMIT_RETRIES + 1):
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()
        try:
            result = _deepl_translate(target)
            _circuit_open_until = 0.0
            return result
        except _QuotaExceeded:
            # Won't recover until next month: stop translating for this run.
            _circuit_open_until = float("inf")
            logger.error("Cuota de DeepL agotada, se desactiva el traductor en esta ejecución")
            raise
        except _RateLimited:
            if attempt == _RATE_LIMIT_RETRIES:
                _circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN
                logger.error("Rate limit persistente, pausando el traductor %ds", _CIRCUIT_COOLDOWN)
                raise
            delay = _RATE_LIMIT_BACKOFF[min(attempt, len(_RATE_LIMIT_BACKOFF) - 1)]
            logger.warning("Rate limit del traductor, reintentando en %ds (intento %d)", delay, attempt + 1)
            time.sleep(delay)

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


# Language of each source, taken from the section it is configured with in
# sources.yaml. Better than the article's own section: a French site writing
# about the Champions League is stored under "europe/champions", which has no
# language, but its source is still configured as "france".
_SOURCES_FILE = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"
_source_langs = None


def _source_lang_hint(source_name):
    global _source_langs
    if _source_langs is None:
        try:
            sources = yaml.safe_load(_SOURCES_FILE.read_text())["sources"]
            _source_langs = {s["name"]: _section_lang_hint(s.get("section")) for s in sources}
        except Exception as exc:
            logger.error("No se pudo leer sources.yaml para el idioma de las fuentes: %s", exc)
            _source_langs = {}
    return _source_langs.get(source_name)


def _lang_hint(source_name, section):
    return _source_lang_hint(source_name) or _section_lang_hint(section)

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

    untranslated = (prefix_es + core) if prefix_es else text

    # Everything that isn't Spanish gets translated, English included.
    # langdetect is unreliable on short headlines (it reads Polish or French
    # titles as "en"/"es"), so it is skipped when the source's language is
    # known; otherwise it only decides which titles are clearly Spanish and
    # need no API call. DeepL reports the language it detected, so a Spanish
    # title that langdetect misread is kept as is.
    if source_lang_hint and source_lang_hint != "es":
        lang = source_lang_hint
    else:
        detect_text = core if (prefix_es and core) else text
        try:
            lang = detect(detect_text)
        except LangDetectException:
            return text, None
        if lang == "es":
            return untranslated, lang

    cached = _get_cached(conn, text)
    if cached:
        return cached, lang

    translate_target = core if prefix_es else text
    try:
        translated, detected = _throttled_translate(translate_target)
        if detected == "es":
            _cache(conn, text, untranslated, "es")
            return untranslated, "es"
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
    hint = _lang_hint(article.get("source_name"), article.get("section"))
    translated_title, _ = translate_text(conn, article["title_orig"], hint)
    article["title"] = translated_title
    if article.get("summary"):
        translated_summary, _ = translate_text(conn, article["summary"][:300], hint)
        article["summary"] = translated_summary
    return article


def retranslate_pending(conn, max_translations=400):
    """Retry titles stored untranslated (title == title_orig) in non-Spanish sections.

    Covers articles inserted while the translator was down (e.g. the Sept–Oct
    2026 Google block) or that hit a transient error. Capped per run to spread
    the DeepL quota; titles langdetect reads as Spanish are skipped without an
    API call, and those DeepL found to be Spanish are cached as such.
    """
    rows = conn.execute("""
        SELECT id, title_orig, section, source_name FROM articles
        WHERE title = title_orig
          AND section NOT LIKE 'spain%' AND section NOT LIKE 'argentina%'
          AND section <> 'southamerica'
        ORDER BY fetched_at DESC
    """).fetchall()
    translated = 0
    for row in rows:
        if translated >= max_translations or time.monotonic() < _circuit_open_until:
            break
        title, _ = translate_text(conn, row["title_orig"],
                                  _lang_hint(row["source_name"], row["section"]))
        if title != row["title_orig"]:
            conn.execute("UPDATE articles SET title = ? WHERE id = ?", (title, row["id"]))
            conn.commit()
            translated += 1
    logger.info("Títulos pendientes retraducidos: %d", translated)
    return translated
