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
        "primaryIconography",
        "iconography",
        "productionMethods_wd",
        "productionMaterials_wd",
        "width",
        "length",
        "height",
        "ID",
    ],
}


# Partial Wikidata mappings (as far as available). Unknown keys fall back to original value.
PRODUCTION_METHOD_MAP = {
    # technique -> Wikidata Q id
    "FRESCO_PAINTING_TECHNIQUE": "Q134194",
}

PRODUCTION_MATERIAL_MAP = {
    # material -> Wikidata Q id
    "CANVAS_TEXTILE_MATERIAL": "Q12321255",
    "OIL_PAINT_PAINT": "Q296955",
}


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
        mapped.append(mapping.get(it, str(it)))
    return ";".join(mapped)


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


def write_missing_csv(stype: str, entities: list[dict], filename: str) -> None:
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
                    elif c == "iconography":
                        row.append(_join_list_field(e.get("iconography")))
                    elif c in ("width", "length", "height"):
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

    results: dict[str, list[dict]] = {}
    for stype, label in CATEGORIES.items():
        missing = filter_missing(entities, present_ids, stype)
        results[label] = missing
        write_missing_csv(stype, missing, f"missing/missing_{label}.csv")

    print("Summary of missing entities (not in query.csv):")
    total = 0
    for label, ents in results.items():
        print(f"  {label:10s}: {len(ents)}")
        total += len(ents)
    print(f"  {'total':10s}: {total}")


if __name__ == "__main__":
    main()
