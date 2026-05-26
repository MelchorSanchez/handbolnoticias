import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
_rules = None


def _load_rules():
    global _rules
    if _rules is None:
        with open(CONFIG_DIR / "classifier_rules.yaml") as f:
            _rules = yaml.safe_load(f)["rules"]
    return _rules


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
    # Check tag match first (priority B)
    rule_tags = [t.lower() for t in rule.get("tags", [])]
    if any(rt in tag for tag in tags for rt in rule_tags):
        return True

    # Keyword match (priority A)
    keywords = [k.lower() for k in rule.get("keywords", [])]
    if not any(kw in text for kw in keywords):
        return False

    # Exclusion check
    excludes = [e.lower() for e in rule.get("exclude", [])]
    if any(ex in text for ex in excludes):
        return False

    # require_any check
    require_any = [r.lower() for r in rule.get("require_any", [])]
    if require_any and not any(r in text for r in require_any):
        return False

    return True


def classify(article):
    """Return the best section slug for the article, or None to keep default."""
    text = _text(article)
    tags = _extract_tags(article)
    rules = _load_rules()

    for rule in rules:
        if _matches_rule(rule, text, tags):
            logger.debug(
                "Classified '%s' → %s", article.get("title_orig", "")[:60], rule["section"]
            )
            return rule["section"]

    return None
