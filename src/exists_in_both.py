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

from .config import (
    CATEGORIES,
    COLUMNS,
    PRODUCTION_MATERIAL_MAP,
    PRODUCTION_METHOD_MAP,
)
from .utils import (
    extract_bildindex,
    join_list_field,
    map_and_join,
    map_position_to_wd,
    process_verbal_dating,
)


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
                    row.append(process_verbal_dating(e.get("verbaleDating")))
                elif stype == "OBJECT_PAINTING":
                    if c == "productionMethods_wd":
                        row.append(
                            map_and_join(
                                e.get("productionMethods"), PRODUCTION_METHOD_MAP
                            )
                        )
                    elif c == "productionMaterials_wd":
                        row.append(
                            map_and_join(
                                e.get("productionMaterials"), PRODUCTION_MATERIAL_MAP
                            )
                        )
                    elif c == "normdata":
                        row.append(extract_bildindex(e.get("normdata")))
                    elif c == "position":
                        row.append(map_position_to_wd(e.get("position")))
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
                        row.append(join_list_field(e.get("iconography")))
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
