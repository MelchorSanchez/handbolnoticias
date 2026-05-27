import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
_rules = None
_teams = None


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

    # Tag match (RSS tags — very specific, skip require_any)
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


def _sections_from_teams(text):
    """Return sections matched by team names (ordered, no duplicates)."""
    teams = _load_teams()
    matched = []
    for section, team_list in teams.items():
        for team in team_list:
            if team and team.lower() in text:
                if section not in matched:
                    matched.append(section)
                break
    return matched


def classify(article):
    """Return list of matching section slugs (empty = keep source default).
    First element is the primary section; the article appears in all of them."""
    text = _text(article)
    tags = _extract_tags(article)
    rules = _load_rules()

    sections = []

    # Keyword / tag rules first (ordered by specificity)
    for rule in rules:
        if _matches_rule(rule, text, tags):
            s = rule["section"]
            if s not in sections:
                sections.append(s)
                logger.debug("Rule '%s' → %s", article.get("title_orig", "")[:60], s)

    # Team-name matches add extra sections
    for s in _sections_from_teams(text):
        if s not in sections:
            sections.append(s)
            logger.debug("Team '%s' → %s", article.get("title_orig", "")[:60], s)

    return sections
