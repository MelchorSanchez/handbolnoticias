import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
_rules = None
_teams = None

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
    "spain/dhp-fem": 8,
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


def _apply_priority_rules(sections, keyword_sections=frozenset()):
    """Post-process section list:
    1. Base articles must not appear alongside adult domestic leagues.
    2. Within each domestic group, keep only the highest-priority level.
    3. Specific EHF sections suppress the europe/other catch-all.
    """
    s = set(sections)

    # Rule 1: base vs adult domestic
    if s & _BASE_SECTIONS:
        sections = [x for x in sections if x not in _DOMESTIC_ADULT]
        s = set(sections)

    # Rule 2: domestic league hierarchy (higher division wins within same gender/country group)
    # Exception: if the article explicitly named a lower division (keyword match), trust that over
    # a team-name match to a higher division (e.g. "Primera Nacional" in title beats asobal team match)
    for group in _PRIORITY_GROUPS:
        in_group = [sec for sec in sections if sec in group]
        if len(in_group) > 1:
            kw_in_group = [sec for sec in in_group if sec in keyword_sections]
            if kw_in_group:
                best = min(kw_in_group, key=lambda sec: group.index(sec))
            else:
                best = min(in_group, key=lambda sec: group.index(sec))
            sections = [sec for sec in sections if sec not in in_group or sec == best]
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
                # masc from keyword (possibly false), fem from team name (precise) → drop masc
                sections = [sec for sec in sections if sec != masc_sec]
                s = set(sections)
            elif fem_kw and not masc_kw:
                sections = [sec for sec in sections if sec != fem_sec]
                s = set(sections)

    # Rule 4: cross-gender domestic incompatibility for Spanish club sections.
    # Selecciones can coexist; club sections cannot (different genders → different events).
    # Preference order: keyword-matched > team-matched (keyword knows the competition explicitly).
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
            # Both (or neither) from keywords → use priority within group
            masc_best = min(
                (_PRIORITY_GROUPS[0].index(sec) for sec in s & _SPAIN_CLUB_MASC),
                default=99,
            )
            fem_best = min(
                (_PRIORITY_GROUPS[1].index(sec) for sec in s & _SPAIN_CLUB_FEM),
                default=99,
            )
            if fem_best <= masc_best:
                sections = [sec for sec in sections if sec not in _SPAIN_CLUB_MASC]
            else:
                sections = [sec for sec in sections if sec not in _SPAIN_CLUB_FEM]

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
            s = rule["section"]
            if s not in keyword_sections:
                keyword_sections.append(s)
                logger.debug("Rule '%s' → %s", article.get("title_orig", "")[:60], s)

    team_sections = []
    for s in _sections_from_teams(text):
        if s not in keyword_sections and s not in team_sections:
            team_sections.append(s)
            logger.debug("Team '%s' → %s", article.get("title_orig", "")[:60], s)

    sections = keyword_sections + team_sections
    return _apply_priority_rules(sections, frozenset(keyword_sections))
