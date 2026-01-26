"""
utils.py

Helper functions
"""

import re
from src.config import POSITION_MAP


def map_position_to_wd(pos):
    """Map a position dict (or list/str) to semicolon-separated Q ids."""
    if not pos:
        return ""
    keys = []
    if isinstance(pos, dict):
        for k, v in pos.items():
            if v:
                keys.append(k)
    elif isinstance(pos, list):
        keys = [str(x) for x in pos]
    else:
        keys = [str(pos)]

    # Return only the first mapped/true position (these values are exclusive)
    for k in keys:
        key_normal = str(k).strip().lower()
        q = POSITION_MAP.get(key_normal)
        if q:
            return f"{q}"
        return key_normal
    return ""


def join_list_field(value):
    """Join list values into a semicolon-separated string."""
    if value is None:
        return ""
    if isinstance(value, list):
        # join list values into a semicolon-separated string
        return ";".join(str(x) for x in value)
    return str(value)


def map_and_join(items, mapping):
    """Map items using a mapping dict and join with semicolons."""
    if not items:
        return ""
    if isinstance(items, str):
        items = [items]
    mapped = []
    for it in items:
        q = mapping.get(it)
        if q:
            mapped.append(q)
    if not mapped:
        return ""
    return ";".join(mapped)


def extract_bildindex(normdata):
    """Extract numeric bildindex from normdata['bildindex'].

    Handles values like 'obj23829038?part=3' and returns '23829038'.
    Returns empty string if missing or malformed.
    """
    if not normdata or not isinstance(normdata, dict):
        return ""
    val = normdata.get("bildindex")
    if not val:
        return ""
    s = str(val)
    # Explicit 'obj' prefix followed by digits
    m = re.search(r"(?i)obj(\d+)", s)
    if m:
        return m.group(1)
    # fallback: first run of digits (will ignore '?part=..')
    m2 = re.search(r"(\d+)", s)
    if m2:
        return m2.group(1)
    return ""


def process_verbal_dating(val: object) -> str:
    """Validate and normalize `verbaleDating`.

    Accepts:
      - exact four-digit year: "1820" -> "1820"
      - approximate forms like "ca. 1820" (case-insensitive) -> "ca. 1820"

    Returns empty string for anything else.
    """
    if val is None:
        return ""
    s = str(val).strip()
    if re.match(r"^\d{4}$", s):
        return s
    m = re.match(r"^(?:ca\.?|c\.?|circa|um\.?)\s*(\d{4})$", s, re.I)
    if m:
        return m.group(1)
    return ""
