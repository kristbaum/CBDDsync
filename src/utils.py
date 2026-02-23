"""
utils.py

Helper functions for data processing and transformation.
"""

import re
from typing import Any

from src.config import POSITION_MAP


def map_position_to_wd(pos: Any) -> str:
    """
    Map a position dict (or list/str) to semicolon-separated Q IDs.

    Args:
        pos: Position data, can be dict, list, or string

    Returns:
        Wikidata Q ID string or empty string if no mapping found
    """
    if not pos:
        return "Q3305213"  # Everything is painting by default
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


def join_list_field(value: Any) -> str:
    """
    Join list values into a semicolon-separated string.

    Args:
        value: Value to join, can be None, list, or other type

    Returns:
        Semicolon-separated string or string representation of value
    """
    if value is None:
        return ""
    if isinstance(value, list):
        # join list values into a semicolon-separated string
        return ";".join(str(x) for x in value)
    return str(value)


def map_and_join(items: Any, mapping: dict[str, str]) -> str:
    """
    Map items using a mapping dict and join with semicolons.

    Args:
        items: Items to map, can be string, list, or None
        mapping: Dictionary mapping items to their values

    Returns:
        Semicolon-separated string of mapped values
    """
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


def extract_bildindex(normdata: Any) -> str:
    """
    Extract numeric bildindex from normdata['bildindex'].

    Handles values like 'obj23829038?part=3' and returns '23829038'.

    Args:
        normdata: Dictionary containing bildindex data or None

    Returns:
        Numeric bildindex string or empty string if missing or malformed
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


def process_verbal_dating(val: Any) -> str:
    """
    Validate and normalize verbaleDating field.

    Accepts:
      - exact four-digit year: "1820" -> "1820"
      - approximate forms like "ca. 1820" (case-insensitive) -> "ca. 1820"

    Args:
        val: Dating value to process

    Returns:
        Normalized dating string or empty string for invalid formats
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
