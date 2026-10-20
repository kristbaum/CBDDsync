"""
building_candidates.py

Bulk candidate search for CbDD buildings: for every building, the Wikidata
items within 300 m of the CbDD coordinates plus the items carrying the CbDD
GND (P227) or Bildindex (P2092) number, with the statements needed to decide
(label, description, type, street address, part-of, existing P10626, GND).
Prints one compact block per building, best candidates first, with flags:

    ID      the item carries the CbDD GND or Bildindex number
    ADR     the item's street address (P6375) or label equals the CbDD address
    CBDD=…  the item already has a deckenmalerei.eu ID (possible CbDD duplicate)
    ↑Q…     the item is a numbered component of a listed monument
            ("… (D-1-23-456-7#2)"); the parent (P361) is usually the item to match

Run from the repository root (reads sources/*.json and sources/query.csv):

    python3 agentic-reconcile/scripts/building_candidates.py \
        --csv missing/missing_buildings.csv [--offset 0] [--limit 600] [--skip-done]

All Wikidata/GND responses are cached in agentic-reconcile/.cache/, so an
interrupted run resumes and re-printing a slice costs nothing. The first run
over ~500 buildings takes about 15–20 minutes (one WDQS query per building,
then the statements of ~10 000 nearby items); progress goes to stderr.
"""

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from cbdd_context import done_ids

SOURCES = Path("sources")
CACHE = Path("agentic-reconcile/.cache")
UA = "CBDDsync-agentic-reconcile/0.2 (https://github.com/kristbaum/CBDDsync)"
WDQS = "https://query.wikidata.org/sparql"
WD_API = "https://www.wikidata.org/w/api.php"
RADIUS_KM = 0.3
# Statements are fetched only for the nearest items: in old towns 300 m hold
# hundreds of items (Stolpersteine, monument components), and matches beyond
# 150 m were rare in practice. Identifier hits are always fetched.
DETAIL_M = 150
DETAIL_MAX = 60
PROPS = ["P31", "P131", "P6375", "P361", "P10626", "P227", "P2092", "P4244"]

# Item types that are never the building itself (by German P31 label).
NOT_A_BUILDING = re.compile(
    r"Bodendenkmal|Stolper|Naturdenkmal|Innerortsstraße|Ortsteil|Gemälde|Skulptur"
    r"|Grab|Brunnen|Kriegerdenkmal|Wegkreuz|Bildstock|Baum|Friedhof|Einfriedung"
    r"|Gartentor|mauer|Straße|Gemeinde|Stadt$|Dorf|Weiler|Haltestelle|Gedenktafel"
    r"|Epitaph|Glocke|Orgel|Altar|Statue|Marterl|Kruzifix|kreuz|Unternehmen"
    r"|Organisation|Verein|Kirchengemeinde|Pfarrei|Fußgängerzone|Platz|Park|Kanzel"
    r"|Taufbecken|Ausstellung|Kunstwerk|Befund"
)
COMPONENT = re.compile(r"\(D-\d-\d+-\d+-\d+#\d+\)")


def get_json(url: str, retries: int = 4):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as ex:  # noqa: BLE001 — WDQS throws 429/502/timeouts
            print(f"  retry {attempt + 1}: {ex}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


def sparql(query: str):
    data = get_json(WDQS + "?" + urllib.parse.urlencode({"query": query}))
    return None if data is None else data["results"]["bindings"]


def cached(name: str, fetch):
    path = CACHE / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = fetch()
    if value is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value


def around(b) -> list[tuple[str, int]]:
    """(QID, distance in m) of all items with coordinates near the building."""

    def fetch():
        rows = sparql(
            "SELECT ?item ?dist WHERE { SERVICE wikibase:around { "
            "?item wdt:P625 ?loc. bd:serviceParam wikibase:center "
            f'"Point({b["locationLng"]} {b["locationLat"]})"^^geo:wktLiteral; '
            f'wikibase:radius "{RADIUS_KM}"; wikibase:distance ?dist. }} }}'
        )
        time.sleep(0.3)
        if rows is None:
            return None
        return [
            [
                r["item"]["value"].rsplit("/", 1)[-1],
                round(float(r["dist"]["value"]) * 1000),
            ]
            for r in rows
        ]

    return [tuple(x) for x in cached(f"around/{b['ID']}.json", fetch) or []]


def id_hits(values: list[str]) -> dict[str, list[str]]:
    """GND/Bildindex value → QIDs carrying it as P227/P2092."""
    out: dict[str, list[str]] = {}
    for i in range(0, len(values), 200):
        chunk = values[i : i + 200]
        rows = sparql(
            "SELECT ?item ?v WHERE { VALUES ?v { "
            + " ".join(json.dumps(v) for v in chunk)
            + " } { ?item wdt:P227 ?v } UNION { ?item wdt:P2092 ?v } }"
        )
        for r in rows or []:
            out.setdefault(r["v"]["value"], []).append(
                r["item"]["value"].rsplit("/", 1)[-1]
            )
    return out


def entities(qids: set[str]) -> dict[str, dict]:
    """Compact statements for QIDs, cached per item."""
    out, todo = {}, []
    for q in sorted(qids):
        p = CACHE / "items" / f"{q}.json"
        if p.exists():
            out[q] = json.loads(p.read_text(encoding="utf-8"))
        else:
            todo.append(q)
    for i in range(0, len(todo), 50):
        if i % 1000 == 0:
            print(f"  items: {i}/{len(todo)}", file=sys.stderr)
        data = get_json(
            WD_API
            + "?"
            + urllib.parse.urlencode(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(todo[i : i + 50]),
                    "props": "labels|descriptions|claims|sitelinks",
                    "languages": "de|mul|en",
                    "format": "json",
                }
            )
        )
        for q, e in (data or {}).get("entities", {}).items():
            if "missing" in e:
                continue

            def lang(key, e=e):
                d = e.get(key, {})
                return (d.get("de") or d.get("mul") or d.get("en") or {}).get("value")

            item = {
                "label": lang("labels") or "",
                "desc": lang("descriptions") or "",
                "dewiki": e.get("sitelinks", {}).get("dewiki", {}).get("title"),
            }
            for prop in PROPS:
                vals = []
                for c in e.get("claims", {}).get(prop, []):
                    v = c["mainsnak"].get("datavalue", {}).get("value")
                    if isinstance(v, dict):
                        v = v.get("id") or v.get("text")
                    if v:
                        vals.append(v)
                item[prop] = vals
            out[q] = item
            path = CACHE / "items" / f"{q}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.2)
    return out


def gnd_name(gnd: str) -> str:
    data = cached(
        f"gnd/{gnd}.json",
        # Malformed GNDs make lobid answer 500 forever: one try, cache the miss.
        lambda: (
            get_json(f"https://lobid.org/gnd/{urllib.parse.quote(gnd)}.json", 1) or {}
        ),
    )
    return (data or {}).get("preferredName", "?")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ß", "ss"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"str\.?(?=\s|\d|$)", "strasse", s)
    return re.sub(r"[^a-z0-9]", "", s)


def address_match(street: str, item: dict) -> bool:
    """CbDD street + number equals an item address or appears in its label."""
    key = norm(street)
    if not re.search(r"\d", key):
        return False  # "Kirchplatz" alone matches half the village
    for adr in item["P6375"]:
        for part in re.split(r"[;,]", adr):
            if norm(part) == key or re.fullmatch(
                re.escape(key) + r"[a-z]?", norm(part)
            ):
                return True
    return bool(re.search(re.escape(key) + r"(?![0-9])", norm(item["label"])))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("ids", nargs="*", help="CbDD building IDs")
    ap.add_argument("--csv", help="missing_buildings.csv")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--skip-done", action="store_true")
    ap.add_argument("--top", type=int, default=3, help="candidates per building")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # ty: ignore[unresolved-attribute]

    ids = list(args.ids)
    if args.csv:
        with open(args.csv, newline="", encoding="utf-8") as f:
            ids += [r["ID"] for r in csv.DictReader(f) if r.get("ID")]
    if args.skip_done:
        done = done_ids()
        ids = [i for i in ids if i not in done]
    if args.csv:
        ids = ids[args.offset : args.offset + args.limit]
    if not ids:
        sys.exit("no IDs to process")

    all_ents = {
        e["ID"]: e
        for e in json.loads((SOURCES / "entities.json").read_text(encoding="utf-8"))
        if isinstance(e, dict) and e.get("ID")
    }
    buildings = [all_ents[i] for i in ids if i in all_ents]

    ident = []
    for b in buildings:
        nd = b.get("normdata") or {}
        ident += [nd.get("gnd"), re.sub(r"\D", "", str(nd.get("bildindex", "")))]
    hits = id_hits(sorted({v for v in ident if v}))

    near = {}
    for n, b in enumerate(buildings):
        if b.get("locationLat") and b.get("locationLng"):
            near[b["ID"]] = around(b)
        if n % 25 == 0:
            print(f"  around: {n}/{len(buildings)}", file=sys.stderr)

    qids = {
        q
        for v in near.values()
        for q, d in sorted(v, key=lambda x: x[1])[:DETAIL_MAX]
        if d <= DETAIL_M
    } | {q for v in hits.values() for q in v}
    items = entities(qids)
    refs = {
        v
        for it in items.values()
        for p in ("P31", "P361")
        for v in it[p]
        if v.startswith("Q")
    }
    labels = entities(refs - set(items)) | items

    def lab(q):
        return labels.get(q, {}).get("label") or q

    for i, b in enumerate(buildings):
        nd = b.get("normdata") or {}
        bi = re.sub(r"\D", "", str(nd.get("bildindex", "")))
        head = [
            f"#{args.offset + i} {b.get('appellation')} | {b['ID']}",
            f"   CbDD: {b.get('addressStreet', '')}, {b.get('addressLocality', '')}"
            f" | {b.get('verbaleDating', '')} | {','.join(b.get('functions', []))}"
            + (
                f" | {','.join(k for k, v in b['condition'].items() if v)}"
                if b.get("condition")
                else ""
            ),
        ]
        if nd.get("gnd"):
            head.append(f"   GND {nd['gnd']} = {gnd_name(nd['gnd'])!r}")
        if bi:
            head.append(f"   Bildindex {bi}")
        if b.get("alternativeNames"):
            head.append(f"   alt: {'; '.join(b['alternativeNames'])}")
        print("\n".join(head))

        dist = dict(near.get(b["ID"], []))
        for v in (nd.get("gnd"), bi):
            for q in hits.get(v or "-", []):
                dist.setdefault(q, -1)  # -1: identifier hit outside the radius
        cands = []
        for q, d in dist.items():
            it = items.get(q)
            if not it:
                continue
            idm = nd.get("gnd") in it["P227"] or (bi and bi in it["P2092"])
            adr = address_match(b.get("addressStreet", ""), it)
            types = [lab(t) for t in it["P31"]]
            if (
                not (idm or adr)
                and types
                and all(NOT_A_BUILDING.search(t) for t in types)
            ):
                continue
            cands.append(
                (not idm, not adr, d if d >= 0 else 9999, q, it, types, idm, adr)
            )
        cands.sort()
        for _, _, d, q, it, types, idm, adr in cands[: args.top]:
            flags = ("ID " if idm else "") + ("ADR " if adr else "")
            if it["P10626"]:
                flags += "CBDD=" + ",".join(x[:8] for x in it["P10626"]) + " "
            parent = ""
            if COMPONENT.search(it["label"]) and it["P361"]:
                parent = f" ↑{it['P361'][0]} {lab(it['P361'][0])!r}"
            print(
                f"   {flags}{q} {it['label'][:70]!r} [{it['desc'][:50]}] "
                f"{'far' if d == 9999 else f'{d}m'} {','.join(types)[:40]}"
                f" adr={';'.join(it['P6375'])[:40]}{' dw' if it['dewiki'] else ''}{parent}"
            )
        if not cands:
            print("   (no building-like item nearby)")


if __name__ == "__main__":
    main()
