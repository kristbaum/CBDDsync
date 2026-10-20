"""
cbdd_context.py

Print a Markdown dossier for deckenmalerei.eu (CbDD) entities, collecting the
hints an agent needs to match them against Wikidata: the entity's own fields,
every related entity (role, dating, host building, place, Wikidata QID if
linked), co-workers, a derived activity period, and text passages from the
CbDD articles that mention the entity.

Run from the repository root (reads sources/*.json and sources/query.csv):

    python3 agentic-reconcile/scripts/cbdd_context.py <ID> [<ID> ...]
    python3 agentic-reconcile/scripts/cbdd_context.py \
        --csv missing/missing_people.csv --limit 10 [--offset 0] [--skip-done]

--skip-done leaves out IDs that already appear in agentic-reconcile/to_match/.
"""

import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

SOURCES = Path("sources")
TO_MATCH = Path("agentic-reconcile/to_match")

# Roles whose person need not have been alive when the work was made
# (engravings used as templates, depicted/referenced persons, donors).
NON_CONTEMPORARY_ROLES = {"TEMPLATE_PROVIDERS", "REFERENCE_PERSONS", "DONORS"}

MAX_WORKS = 40
MAX_TEXT_HITS = 6
SNIPPET = 220


def load():
    entities = {
        e["ID"]: e
        for e in json.loads((SOURCES / "entities.json").read_text(encoding="utf-8"))
        if isinstance(e, dict) and e.get("ID")
    }
    relations = json.loads((SOURCES / "relations.json").read_text(encoding="utf-8"))
    qids = {}
    with open(SOURCES / "query.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("deckenmalerei_eu_ID") and row.get("item"):
                qids[row["deckenmalerei_eu_ID"]] = row["item"].rsplit("/", 1)[-1]

    # Relations are stored in both directions; index only the "->" form.
    outgoing: dict[str, list[dict]] = {}
    incoming: dict[str, list[dict]] = {}
    parent: dict[str, str] = {}
    for r in relations:
        if r.get("relDir") != "->":
            continue
        outgoing.setdefault(r["ID"], []).append(r)
        incoming.setdefault(r["relTar"], []).append(r)
        if r.get("sType") == "PART":
            parent.setdefault(r["relTar"], r["ID"])
    return entities, outgoing, incoming, parent, qids


def first_year(dating) -> int | None:
    """
    First year in a verbaleDating string, usually the creation phase.

    Datings often list later phases too ("Datierung: 1730, Zerstörung: 1943,
    Rekonstruktion: 1955-1961"), so only the first year is used. The source
    uses "1000-2020" as an "unknown" placeholder; it is skipped.
    """
    dating = re.sub(r"1000\s*-\s*2020", "", str(dating))
    m = re.search(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)", dating)
    return int(m.group(1)) if m else None


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def host_building(eid, entities, parent):
    seen = set()
    while eid in parent and eid not in seen:
        seen.add(eid)
        eid = parent[eid]
        if entities.get(eid, {}).get("sType") == "OBJECT_BUILDING":
            return entities[eid]
    return None


def place(building) -> str:
    if not building:
        return ""
    return ", ".join(
        p for p in (building.get("addressLocality"), building.get("addressState")) if p
    )


def qid_label(eid, qids) -> str:
    return qids.get(eid, "–")


def name_keys(person) -> list[str]:
    """Search keys for text mentions: the surname(s) of 'Surname, Given' names."""
    names = [person.get("appellation", "")] + list(person.get("alternativeNames", []))
    keys = set()
    for n in names:
        surname = n.split(",")[0].strip()
        if len(surname) >= 4:
            keys.add(surname)
    return sorted(keys)


def text_hits(target_ids, keys, entities, incoming, limit=MAX_TEXT_HITS):
    """Passages from texts documenting target_ids that mention any of keys."""
    hits = []
    if not keys:
        return hits
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    seen = set()
    for tid in target_ids:
        for r in incoming.get(tid, []):
            if r.get("sType") != "DOCUMENTS" or r["ID"] in seen:
                continue
            seen.add(r["ID"])
            t = entities.get(r["ID"], {})
            body = strip_html(t.get("text", "") or t.get("shortText", ""))
            m = pattern.search(body)
            if m:
                a = max(0, m.start() - SNIPPET // 2)
                hits.append(
                    (t.get("appellation", ""), "…" + body[a : a + SNIPPET] + "…")
                )
            if len(hits) >= limit:
                return hits
    return hits


def person_dossier(p, entities, outgoing, incoming, parent, qids) -> list[str]:
    out = [
        f"## {p.get('appellation')} (person)",
        "",
        f"- CbDD ID: `{p['ID']}` — https://www.deckenmalerei.eu/{p['ID']}",
        f"- Gender: {p.get('gender', '–')}",
        f"- GND: {(p.get('normdata') or {}).get('gnd', '–')}",
    ]
    if p.get("alternativeNames"):
        out.append(f"- Alternative names: {'; '.join(p['alternativeNames'])}")

    works = incoming.get(p["ID"], [])
    contemporary_years, all_places, roles = [], {}, {}
    co_workers: dict[str, set] = {}
    rows = []
    for r in works:
        w = entities.get(r["ID"])
        role = r.get("sType", "")
        roles[role] = roles.get(role, 0) + 1
        if not w:
            rows.append(f"| {role} | (resource {r['ID']}) | | | | |")
            continue
        b = (
            w
            if w.get("sType") == "OBJECT_BUILDING"
            else host_building(w["ID"], entities, parent)
        )
        dating = w.get("verbaleDating") or (b or {}).get("verbaleDating", "")
        year = first_year(dating)
        if role not in NON_CONTEMPORARY_ROLES and year:
            contemporary_years.append(year)
        if b:
            all_places[place(b)] = all_places.get(place(b), 0) + 1
        for cr in outgoing.get(w["ID"], []):
            other = entities.get(cr["relTar"], {})
            if other.get("sType") == "ACTOR_PERSON" and cr["relTar"] != p["ID"]:
                key = f"{other.get('appellation')} ({qid_label(cr['relTar'], qids)})"
                co_workers.setdefault(key, set()).add(cr["sType"])
        rows.append(
            f"| {role} | {w.get('sType', '').removeprefix('OBJECT_').lower()}: "
            f"{w.get('appellation', '')} ({qid_label(w['ID'], qids)}) | {dating} | "
            f"{(b or {}).get('appellation', '')} ({qid_label((b or {}).get('ID'), qids)}) "
            f"| {place(b)} |"
        )

    out.append(
        "- Roles: "
        + (", ".join(f"{k} ×{v}" for k, v in sorted(roles.items())) or "none")
    )
    if contemporary_years:
        out.append(
            f"- Approx. activity period (first year of each work's dating, excl. "
            f"{', '.join(sorted(NON_CONTEMPORARY_ROLES))}): "
            f"{min(contemporary_years)}–{max(contemporary_years)} — "
            f"check the Works table, datings can be phases or uncertain"
        )
    else:
        out.append("- Activity period: no dated works")
    if all_places:
        out.append(
            "- Places of work: "
            + "; ".join(
                f"{k} ×{v}" for k, v in sorted(all_places.items(), key=lambda x: -x[1])
            )
        )
    if co_workers:
        out.append(
            "- Co-workers on the same works: "
            + "; ".join(
                f"{k} [{', '.join(sorted(v))}]" for k, v in sorted(co_workers.items())
            )[:1500]
        )

    if rows:
        out += [
            "",
            f"### Works ({len(rows)}{', first ' + str(MAX_WORKS) if len(rows) > MAX_WORKS else ''})",
            "",
            "| Role | Work (QID) | Dating | Building (QID) | Place |",
            "|---|---|---|---|---|",
            *rows[:MAX_WORKS],
        ]

    hits = text_hits(
        [r["ID"] for r in works], name_keys(p), entities, incoming, MAX_TEXT_HITS
    )
    if hits:
        out += ["", "### Mentions in CbDD texts", ""]
        out += [f"- *{title}*: {snip}" for title, snip in hits]
    return out


def building_dossier(b, entities, outgoing, incoming, parent, qids) -> list[str]:
    nd = b.get("normdata") or {}
    bildindex = re.search(r"\d+", str(nd.get("bildindex", "")))
    out = [
        f"## {b.get('appellation')} (building)",
        "",
        f"- CbDD ID: `{b['ID']}` — https://www.deckenmalerei.eu/{b['ID']}",
        (
            f"- Address: {b.get('addressStreet', '')}, {b.get('addressZip', '')} "
            f"{b.get('addressLocality', '')}, {b.get('addressState', '')}"
        ),
        f"- Coordinates: {b.get('locationLat')}, {b.get('locationLng')}",
        f"- Dating: {b.get('verbaleDating', '–')}",
        f"- Functions: {', '.join(b.get('functions', [])) or '–'}",
        f"- Condition: {', '.join(k for k, v in (b.get('condition') or {}).items() if v) or '–'}",
        f"- GND: {nd.get('gnd', '–')}",
        f"- Bildindex object (P2092): {bildindex.group(0) if bildindex else '–'}",
    ]
    if b.get("alternativeNames"):
        out.append(f"- Alternative names: {'; '.join(b['alternativeNames'])}")
    if b["ID"] in parent:
        pe = entities.get(parent[b["ID"]], {})
        out.append(
            f"- Part of: {pe.get('appellation')} ({qid_label(pe.get('ID'), qids)})"
        )

    parts, people = [], []
    for r in outgoing.get(b["ID"], []):
        t = entities.get(r["relTar"], {})
        if r["sType"] == "PART":
            parts.append(f"{t.get('appellation')} ({qid_label(r['relTar'], qids)})")
        elif t.get("sType") in ("ACTOR_PERSON", "ACTOR_SOCIETY"):
            people.append(
                f"{r['sType']}: {t.get('appellation')} ({qid_label(r['relTar'], qids)})"
            )
    if parts:
        out.append(f"- Parts ({len(parts)}): " + "; ".join(parts[:25]))
    if people:
        out.append("- People and bodies: " + "; ".join(people))

    texts = [
        strip_html(entities[r["ID"]].get("shortText", ""))
        for r in incoming.get(b["ID"], [])
        if r.get("sType") == "DOCUMENTS" and entities.get(r["ID"], {}).get("shortText")
    ]
    if texts:
        out += ["", "### CbDD summary", "", *[f"> {t}" for t in texts[:2]]]
    return out


def done_ids() -> set[str]:
    ids: set[str] = set()
    for f in TO_MATCH.glob("*"):
        if f.suffix in (".qs", ".md"):
            ids |= set(
                re.findall(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                    f.read_text(encoding="utf-8"),
                )
            )
    return ids


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("ids", nargs="*", help="CbDD entity IDs")
    ap.add_argument("--csv", help="missing_*.csv to take IDs from (column ID)")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--skip-done", action="store_true")
    args = ap.parse_args()

    ids = list(args.ids)
    if args.csv:
        with open(args.csv, newline="", encoding="utf-8") as f:
            ids += [row["ID"] for row in csv.DictReader(f) if row.get("ID")]
    if args.skip_done:
        done = done_ids()
        ids = [i for i in ids if i not in done]
    if args.csv:
        ids = ids[args.offset : args.offset + args.limit]
    if not ids:
        sys.exit("no IDs to process")

    entities, outgoing, incoming, parent, qids = load()
    for eid in ids:
        e = entities.get(eid)
        if not e:
            print(f"## {eid}\n\nnot found in sources/entities.json\n")
            continue
        if eid in qids:
            print(f"> NOTE: {eid} is already linked to {qids[eid]} in query.csv\n")
        fn = {"ACTOR_PERSON": person_dossier, "OBJECT_BUILDING": building_dossier}.get(
            e.get("sType", "")
        )
        if not fn:
            print(
                f"## {e.get('appellation')}\n\nsType {e.get('sType')} not supported\n"
            )
            continue
        print("\n".join(fn(e, entities, outgoing, incoming, parent, qids)) + "\n")


if __name__ == "__main__":
    main()
