import re

_PAREN_RE = re.compile(r"\([^)]*\)")
_WHITESPACE_RE = re.compile(r"\s+")

# Deliberately a short, explicit alias list rather than general stemming or
# fuzzy/embedding matching - see ADR-0008. Extend this as real mismatches
# turn up in practice.
_SYNONYMS: dict[str, str] = {
    "onions": "onion",
    "scallion": "green onion",
    "scallions": "green onion",
    "spring onion": "green onion",
    "spring onions": "green onion",
    "cilantro": "coriander",
    "garbanzo bean": "chickpea",
    "garbanzo beans": "chickpea",
    "chickpeas": "chickpea",
    "aubergine": "eggplant",
    "capsicum": "bell pepper",
    "courgette": "zucchini",
}


def normalize_ingredient_name(name: str) -> str:
    """Canonicalize an ingredient name for comparison and dedup.

    Strips parenthetical prep notes (e.g. "onion (for cooking)" -> "onion")
    and maps a small set of known synonyms to one canonical spelling.
    """
    text = name.strip().lower()
    text = _PAREN_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return _SYNONYMS.get(text, text)
