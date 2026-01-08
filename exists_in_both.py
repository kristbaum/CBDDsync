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
    "ACTOR_PERSON": ["appellation", "gender", "ID"],
    "OBJECT_BUILDING": [
        "appellation",
        "verbaleDating",
        "addressState",
        "addressLocality",
        "addressZip",
        "addressStreet",
        "locationLng",
        "locationLat",
        "ID",
    ],
    "OBJECT_PAINTING": ["appellation", "verbaleDating", "ID"],
}


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
            w.writerow([e.get(c) for c in cols])


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
