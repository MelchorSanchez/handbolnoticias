import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
_rules = None
_teams = None

# Hashtags from CatHandbol that mark purely regional Catalan competitions.
# When present, team-name matches must not pull the article into Spanish national sections.
_CATALAN_ONLY = re.compile(
    r'#?(1acathfem|2acathfem|3acathfem|3acath|2acath|lligacatargm|lligacatorm|lligacatorf)',
    re.IGNORECASE,
)
_SPAIN_NATIONAL = frozenset({
    "spain/asobal", "spain/dhp", "spain/primera-nacional-masc",
    "spain/guerreras", "spain/dho-fem", "spain/dhp-fem",
    "spain/seleccion-masc", "spain/seleccion-fem",
})

# Base sections exclude domestic adult leagues (but can coexist with European/world sections)
_BASE_SECTIONS = frozenset({"spain/base-masc", "spain/base-fem"})
_DOMESTIC_ADULT = frozenset({
    "spain/asobal", "spain/guerreras", "spain/dhp",
    "spain/dho-fem", "spain/dhp-fem", "spain/primera-nacional-masc",
    "germany/bundesliga", "germany/zweite-liga", "germany",
    "france/starligue", "france/pro-d2", "france",
})

# Within each group, if multiple sections are present keep only the highest-priority one.
# Order = priority (first = highest). Cross-group sections can coexist normally.
_PRIORITY_GROUPS = [
    ["spain/asobal", "spain/dhp", "spain/primera-nacional-masc"],
    ["spain/guerreras", "spain/dho-fem", "spain/dhp-fem"],
    ["germany/bundesliga", "germany/zweite-liga", "germany"],
    ["france/starligue", "france/pro-d2", "france"],
]

# Specific EHF sections suppress the catch-all europe/other
_SPECIFIC_EHF = frozenset({
    "europe/champions", "europe/champions-women",
    "europe/european-league", "europe/european-league-women",
    "europe/cup-men", "europe/cup-women",
    "europe/euro-men", "europe/euro-women",
})

# Gender signal patterns for Spanish handball text
_MALE_WORDS = re.compile(
    r'\bjugadores?\b|\bporteros?\b|\bmasculinos?\b|\bentrenadores?\b'
    r'|\bpivots? masc|\bel jugador\b|\bun jugador\b|\bel portero\b|\bel pivot\b'
    r'|\bel lateral\b|\bel central\b|\bel extremo\b|\bel entrenador\b'
)
_FEMALE_WORDS = re.compile(
    r'\bjugadoras?\b|\bporteras?\b|\bfemenin[ao]s?\b|\bentrenadoras?\b'
    r'|\bla jugadora\b|\buna jugadora\b|\bla portera\b|\bla pivot\b'
    r'|\bla lateral\b|\bla entrenadora\b'
)

# Common unambiguously male/female Spanish & Basque first names in handball context
# Used only when no positional vocabulary is found (e.g. empty summary)
_MALE_NAMES = re.compile(
    r'\b(?:Pablo|Carlos|Sergio|Antonio|Mario|Luis|Javier|David|Miguel|Angel'
    r'|Manuel|Roberto|Fernando|Rafael|Alejandro|Alberto|Pedro|Jorge|Raul'
    r'|Ivan|Ruben|Adrian|Daniel|Victor|Eduardo|Gonzalo'
    r'|Rodrigo|Alvaro|Diego|Juan|Tomas|Dani|Juanin'
    r'|Iker|Mikel|Jon|Ander|Unai|Julen|Aitor|Gorka|Joseba|Eneko|Xabi'
    r'|Xavier|Alex|Ferran|Marc|Pau|Arnau|Jordi|Josep|Carles|Joan)\b',
    re.IGNORECASE,
)
_FEMALE_NAMES = re.compile(
    r'\b(?:Maria|Ana|Laura|Carmen|Marta|Sara|Elena|Cristina|Isabel'
    r'|Patricia|Rosa|Lucia|Silvia|Nerea|Itziar|Almudena|Rocio'
    r'|Amaia|Ane|Leire|Miren|Ainhoa|Uxue|Eider|Maite|Miriam|Sandra|Raquel'
    r'|Noelia|Beatriz|Bea|Estela|Irene|Clara|Paula|Sheila|Jennifer|Darly'
    r'|Mireya|Aileen|Alexandrina|Yuliya|Katarina|Eduarda|Bruna)\b',
    re.IGNORECASE,
)


def _gender_signal(text):
    """Return 'masc', 'fem', or None based on gendered handball vocabulary in the text.
    Falls back to first-name detection when no positional vocabulary is present."""
    masc = len(_MALE_WORDS.findall(text))
    fem = len(_FEMALE_WORDS.findall(text))
    if masc != fem:
        return 'masc' if masc > fem else 'fem'
    # Fall back to first-name detection
    masc_names = len(_MALE_NAMES.findall(text))
    fem_names = len(_FEMALE_NAMES.findall(text))
    if masc_names > fem_names:
        return 'masc'
    if fem_names > masc_names:
        return 'fem'
    return None


def _load_rules():
    global _rules
    if _rules is None:
        with open(CONFIG_DIR / "classifier_rules.yaml") as f:
            _rules = yaml.safe_load(f)["rules"]
    return _rules


def _load_teams():
    global _teams
    if _teams is None:
        path = CONFIG_DIR / "teams.yaml"
        if path.exists():
            with open(path) as f:
                _teams = yaml.safe_load(f).get("teams", {})
        else:
            _teams = {}
    return _teams


def _extract_tags(article):
    raw = article.get("_raw_tags", [])
    return [t.lower().strip() for t in raw if t]


def _text(article):
    return (
        (article.get("title_orig") or "")
        + " "
        + (article.get("summary") or "")
    ).lower()


def _matches_rule(rule, text, tags):
    excludes = [e.lower() for e in rule.get("exclude", [])]

    # Tag match (RSS tags — very specific, bypass require_any)
    rule_tags = [t.lower() for t in rule.get("tags", [])]
    if any(rt in tag for tag in tags for rt in rule_tags):
        return not any(ex in text for ex in excludes)

    # Keyword match
    keywords = [k.lower() for k in rule.get("keywords", [])]
    if not any(kw in text for kw in keywords):
        return False

    if any(ex in text for ex in excludes):
        return False

    require_any = [r.lower() for r in rule.get("require_any", [])]
    if require_any and not any(r in text for r in require_any):
        return False

    return True


# Sections with many short city-name entries: require longer names to avoid false positives
_MIN_NAME_LEN = {
    "spain/primera-nacional-masc": 8,
    "spain/dhp-fem": 7,
}
_DEFAULT_MIN_NAME_LEN = 5


def _sections_from_teams(text):
    """Return sections matched by team names (ordered, no duplicates)."""
    teams = _load_teams()
    matched = []
    for section, team_list in teams.items():
        min_len = _MIN_NAME_LEN.get(section, _DEFAULT_MIN_NAME_LEN)
        for team in team_list:
            if team and len(team) >= min_len and team.lower() in text:
                if section not in matched:
                    matched.append(section)
                break
    return matched


def _apply_priority_rules(sections, keyword_sections=frozenset(), text=""):
    """Post-process section list:
    1. Base articles must not appear alongside adult domestic leagues.
    2. Within each domestic group:
       - Keyword-matched sections are always kept.
       - If keyword + team sections coexist in the same group, keep both the
         keyword-matched one(s) and the best team-matched one (promotion articles).
       - If only team matches, keep the highest-priority one.
    3. Specific EHF sections suppress the europe/other catch-all.
    4. Cross-gender Spanish club resolution uses keyword source priority, then
       gender vocabulary signals, then falls back to keeping both sections.
    """
    s = set(sections)

    # Rule 1: base vs adult domestic
    if s & _BASE_SECTIONS:
        sections = [x for x in sections if x not in _DOMESTIC_ADULT]
        s = set(sections)

    # Rule 2: domestic league hierarchy within same gender/country group.
    for group in _PRIORITY_GROUPS:
        in_group = [sec for sec in sections if sec in group]
        if len(in_group) > 1:
            kw_in_group = [sec for sec in in_group if sec in keyword_sections]
            team_in_group = [sec for sec in in_group if sec not in keyword_sections]

            if kw_in_group and team_in_group:
                # Article explicitly names a competition (keyword) AND a team from a
                # different level (e.g. "Anaitasuna quiere subir a Asobal").
                # Keep keyword-matched + team-matched only if it's at most 1 step below
                # the best keyword section (direct promotion context).
                # This prevents city-name coincidences 2+ levels away from firing.
                best_kw_idx = min(group.index(sec) for sec in kw_in_group)
                adjacent_team = [sec for sec in team_in_group
                                 if group.index(sec) <= best_kw_idx + 1]
                keep = set(kw_in_group)
                if adjacent_team:
                    keep.add(min(adjacent_team, key=lambda sec: group.index(sec)))
                sections = [sec for sec in sections if sec not in in_group or sec in keep]
            elif len(team_in_group) > 1:
                # Multiple team-only matches → keep highest priority (lowest index)
                best = min(team_in_group, key=lambda sec: group.index(sec))
                sections = [sec for sec in sections if sec not in team_in_group or sec == best]
            # Single section or only keyword matches → keep as-is
        s = set(sections)

    # Rule 3: specific EHF section suppresses europe/other
    if s & _SPECIFIC_EHF and "europe/other" in s:
        sections = [sec for sec in sections if sec != "europe/other"]
        s = set(sections)

    # Rule 3b: EHF gendered-pair resolution.
    # When a section was keyword-matched (gender ambiguous) AND the opposing-gender
    # version was team-matched (gender precise), trust the team signal.
    _EHF_PAIRS = [
        ("europe/cup-men", "europe/cup-women"),
        ("europe/european-league", "europe/european-league-women"),
        ("europe/champions", "europe/champions-women"),
        ("europe/euro-men", "europe/euro-women"),
    ]
    for masc_sec, fem_sec in _EHF_PAIRS:
        if masc_sec in s and fem_sec in s:
            masc_kw = masc_sec in keyword_sections
            fem_kw = fem_sec in keyword_sections
            if masc_kw and not fem_kw:
                sections = [sec for sec in sections if sec != masc_sec]
                s = set(sections)
            elif fem_kw and not masc_kw:
                sections = [sec for sec in sections if sec != fem_sec]
                s = set(sections)

    # Rule 4a: Suppress European club sections that come only from team-name matching
    # when any Spanish domestic section is present (keyword OR team matched).
    # Logic: an article about a Spanish club belongs to Spanish sections by default;
    # it only goes to a European section if the article explicitly uses European
    # competition keywords (Champions League, European League, etc.).
    _EUROPE_CLUB = frozenset({
        "europe/champions", "europe/champions-women",
        "europe/european-league", "europe/european-league-women",
        "europe/cup-men", "europe/cup-women",
    })
    _DOMESTIC_ANY = _SPAIN_NATIONAL | frozenset({
        "france/starligue", "france/pro-d2", "france",
        "germany/bundesliga", "germany/zweite-liga", "germany",
        "portugal", "denmark", "sweden", "norway",
    })
    domestic_present = s & _DOMESTIC_ANY
    europe_team_only = (s & _EUROPE_CLUB) - keyword_sections
    if domestic_present and europe_team_only:
        sections = [sec for sec in sections if sec not in europe_team_only]
        s = set(sections)

    # Rule 4: cross-gender domestic incompatibility for Spanish club sections.
    # Priority: (a) keyword source, (b) gender vocabulary signals, (c) keep both.
    _SPAIN_CLUB_MASC = {"spain/asobal", "spain/dhp", "spain/primera-nacional-masc"}
    _SPAIN_CLUB_FEM = {"spain/guerreras", "spain/dho-fem", "spain/dhp-fem"}
    has_fem = bool(s & _SPAIN_CLUB_FEM)
    has_masc = bool(s & _SPAIN_CLUB_MASC)
    if has_fem and has_masc:
        masc_from_kw = s & _SPAIN_CLUB_MASC & keyword_sections
        fem_from_kw = s & _SPAIN_CLUB_FEM & keyword_sections
        if masc_from_kw and not fem_from_kw:
            sections = [sec for sec in sections if sec not in _SPAIN_CLUB_FEM]
        elif fem_from_kw and not masc_from_kw:
            sections = [sec for sec in sections if sec not in _SPAIN_CLUB_MASC]
        else:
            # Neither (or both) from keywords: use gender vocabulary signals
            gender = _gender_signal(text)
            if gender == 'masc':
                sections = [sec for sec in sections if sec not in _SPAIN_CLUB_FEM]
            elif gender == 'fem':
                sections = [sec for sec in sections if sec not in _SPAIN_CLUB_MASC]
            # If truly ambiguous, keep both genders so the article appears in both pages

    return sections


def classify(article):
    """Return list of matching section slugs (empty = keep source default).
    First element is the primary section; the article appears in all of them."""
    text = _text(article)
    tags = _extract_tags(article)
    rules = _load_rules()

    keyword_sections = []
    for rule in rules:
        if _matches_rule(rule, text, tags):
            sec = rule["section"]
            if sec not in keyword_sections:
                keyword_sections.append(sec)
                logger.debug("Rule '%s' → %s", article.get("title_orig", "")[:60], sec)

    team_sections = []
    for sec in _sections_from_teams(text):
        if sec not in keyword_sections and sec not in team_sections:
            team_sections.append(sec)
            logger.debug("Team '%s' → %s", article.get("title_orig", "")[:60], sec)

    sections = keyword_sections + team_sections

    # If a Catalan-only competition hashtag is present, drop any Spanish national sections
    # that crept in via team-name matching (e.g. a B-team from a national-level club).
    if _CATALAN_ONLY.search(text):
        sections = [s for s in sections if s not in _SPAIN_NATIONAL]

    return _apply_priority_rules(sections, frozenset(keyword_sections), text)
