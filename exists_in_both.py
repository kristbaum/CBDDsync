#!/usr/bin/env python3
"""
exists_in_both.py

Reads inputs from the current directory:
  - query.csv (columns: item, deckenmalerei_eu_ID)
  - entities.json (list of entity dicts)

Writes three CSV files with entities missing in query.csv, by sType:
  - missing_people.csv        (ACTOR_PERSON)
  - missing_buildings.csv     (OBJECT_BUILDING)
  - missing_paintings.csv     (OBJECT_PAINTING)

Each output CSV has headers: appellation,ID
Also prints a brief summary.
"""

import csv
import json
import re


# sType -> output suffix
CATEGORIES = {
    "ACTOR_PERSON": "people",
    "OBJECT_BUILDING": "buildings",
    "OBJECT_PAINTING": "paintings",
}

# Columns to export per sType (order matters for CSV header)
COLUMNS = {
    "ACTOR_PERSON": ["url", "appellation", "gender", "ID"],
    "OBJECT_BUILDING": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "addressState",
        "addressLocality",
        "addressZip",
        "addressStreet",
        "wikishootme",
        "locationLng",
        "locationLat",
        "ID",
    ],
    "OBJECT_PAINTING": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "primaryIconography",
        "iconography",
        "productionMethods_wd",
        "productionMaterials_wd",
        "position",
        "normdata",
        "commissioner",
        "painter",
        "width",
        "length",
        "height",
        "diameter",
        "ID",
    ],
}


PRODUCTION_METHOD_MAP = {
    # technique -> Wikidata Q id
    "FRESCO_PAINTING_TECHNIQUE": "Q134194",
    "OIL_PAINTING_TECHNIQUE": "Q174705",
}

PRODUCTION_MATERIAL_MAP = {
    # material -> Wikidata Q id
    "CANVAS_TEXTILE_MATERIAL": "Q12321255",
    "OIL_PAINT_PAINT": "Q296955",
    "PLASTER_COMPOSITE_COATING": "Q572879",
}

POSITION_MAP = {
    "ceiling": "Q1181933",
    "wall": "Q3305213",
    "equipment": "Q3305213",
}


def _map_position_to_wd(pos):
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


def _join_list_field(value):
    if value is None:
        return ""
    if isinstance(value, list):
        # join list values into a semicolon-separated string
        return ";".join(str(x) for x in value)
    return str(value)


def _map_and_join(items, mapping):
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


def build_internal_to_q() -> dict:
    d = {}
    with open("sources/query.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item = (row.get("item") or "").strip()
            internal = (row.get("deckenmalerei_eu_ID") or "").strip()
            if item and internal:
                # item is a Wikidata URL like http://www.wikidata.org/entity/Q12345
                q = item.rsplit("/", 1)[-1]
                d[internal] = q
    return d


def _extract_bildindex(normdata):
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


def _process_verbaleDating(val: object) -> str:
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


def load_query_ids() -> set[str]:
    ids: set[str] = set()
    with open("sources/query.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            internal_id = (row.get("deckenmalerei_eu_ID") or "").strip()
            if internal_id:
                ids.add(internal_id)
    return ids


def load_entities() -> list[dict]:
    with open("sources/entities.json", encoding="utf-8") as f:
        data = json.load(f)
    # Expect a list of dicts
    return [e for e in data if isinstance(e, dict)]


def filter_missing(
    entities: list[dict], present_ids: set[str], stype: str
) -> list[dict]:
    return [
        e
        for e in entities
        if e.get("sType") == stype and e.get("ID") not in present_ids
    ]


def write_missing_csv(
    stype: str,
    entities: list[dict],
    filename: str,
    relations_by_source: dict | None = None,
    internal_to_q: dict | None = None,
) -> None:
    cols = COLUMNS.get(stype, ["appellation", "ID"])
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for e in entities:
            row = []
            for c in cols:
                if c == "url":
                    entity_id = e.get("ID", "")
                    row.append(f"https://www.deckenmalerei.eu/{entity_id}")
                elif c == "wikishootme":
                    lat = e.get("locationLat", "")
                    lng = e.get("locationLng", "")
                    row.append(
                        f"https://wikishootme.toolforge.org/#lat={lat}&lng={lng}&zoom=18"
                    )

                # Special handling for painting fields that need mapping/formatting
                elif c == "processedDating":
                    row.append(_process_verbaleDating(e.get("verbaleDating")))
                elif stype == "OBJECT_PAINTING":
                    if c == "productionMethods_wd":
                        row.append(
                            _map_and_join(
                                e.get("productionMethods"), PRODUCTION_METHOD_MAP
                            )
                        )
                    elif c == "productionMaterials_wd":
                        row.append(
                            _map_and_join(
                                e.get("productionMaterials"), PRODUCTION_MATERIAL_MAP
                            )
                        )
                    elif c == "normdata":
                        row.append(_extract_bildindex(e.get("normdata")))
                    elif c == "position":
                        row.append(_map_position_to_wd(e.get("position")))
                    elif c == "commissioner":
                        qids = []
                        rels = (relations_by_source or {}).get(e.get("ID"), [])
                        for r in rels:
                            if (
                                r.get("relDir") == "->"
                                and r.get("sType", "").upper() == "COMMISSIONERS"
                            ):
                                q = (internal_to_q or {}).get(r.get("relTar"))
                                if q:
                                    qids.append(q)
                        row.append(";".join(qids))
                    elif c == "painter":
                        qids = []
                        rels = (relations_by_source or {}).get(e.get("ID"), [])
                        for r in rels:
                            if (
                                r.get("relDir") == "->"
                                and r.get("sType", "").upper() == "PAINTERS"
                            ):
                                q = (internal_to_q or {}).get(r.get("relTar"))
                                if q:
                                    qids.append(q)
                        row.append(";".join(qids))
                    elif c == "iconography":
                        row.append(_join_list_field(e.get("iconography")))
                    elif c in ("width", "length", "height", "diameter"):
                        dim = e.get("dimension") or {}
                        val = dim.get(c)
                        row.append(val if val is not None else "")
                    else:
                        row.append(e.get(c, ""))

                else:
                    row.append(e.get(c))
            w.writerow(row)


def main() -> None:
    present_ids = load_query_ids()
    entities = load_entities()

    with open("sources/relations.json", encoding="utf-8") as f:
        relations = json.load(f)
    relations_by_source: dict[str, list[dict]] = {}
    for r in relations:
        src = r.get("ID")
        if src:
            relations_by_source.setdefault(src, []).append(r)

    internal_to_q = build_internal_to_q()

    results: dict[str, list[dict]] = {}
    for stype, label in CATEGORIES.items():
        missing = filter_missing(entities, present_ids, stype)
        results[label] = missing
        write_missing_csv(
            stype,
            missing,
            f"missing/missing_{label}.csv",
            relations_by_source=relations_by_source,
            internal_to_q=internal_to_q,
        )

    print("Summary of missing entities (not in query.csv):")
    total = 0
    for label, ents in results.items():
        print(f"  {label:10s}: {len(ents)}")
        total += len(ents)
    print(f"  {'total':10s}: {total}")


if __name__ == "__main__":
    main()
