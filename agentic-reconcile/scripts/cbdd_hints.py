"""
cbdd_hints.py

CbDD-specific evidence for a run's ingest file, the part wikibase-ingest's generic
`verify` cannot compute. Run it after `wikibase-ingest candidates` and before
`wikibase-ingest verify`:

  people     - the Wikidata item the CbDD GND record links to (lobid sameAs)
               becomes a candidate, also when it lacks P227 (a repair);
             - lifetime against the CbDD works, role by role (date, P569):
               + fits, - contradicts most works with their own dating,
               0 fits most but not all (datings list a building's phases);
             - gender differs from CbDD (custom, P21, -)
  buildings  - the CbDD street address equals the item's P6375 or label
               (custom, P6375, +);
             - the item is a numbered component of a Bavarian monument
               ("… (D-1-81-122-26#1)"): custom P361 -, and the monument
               it is part of becomes a candidate (custom P361 +)
  both       - the entity's hint names what the CbDD GND record is
               ("GND 4821135-7 (lobid): 'Sankt Jakobus der Ältere
               (Mammendorf)'"), so a GND of the parish or the town shows

Evidence is written as verified, by "cbdd_hints"; the routing policies in
policy/ hide candidates with a verified contradiction ("custom", "date"). A
matching address is shown, never matched on (parts of a complex share it). Wikidata items and lobid records are cached in
agentic-reconcile/.cache/ (items for a week).

    uv run python agentic-reconcile/scripts/cbdd_hints.py <run>/ingest.json [--write]
"""

import argparse
import datetime
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from cbdd_context import NON_CONTEMPORARY_ROLES, host_building, load

BY = "cbdd_hints 1.0"
CACHE = Path("agentic-reconcile/.cache")
ITEM_DAYS = 7
UA = "CBDDsync-agentic-reconcile/0.3 (https://github.com/kristbaum/CBDDsync)"
WD_API = "https://www.wikidata.org/w/api.php"
PROPS = ["P31", "P21", "P569", "P570", "P1317", "P2031", "P2032", "P6375", "P361"]
GENDER = {"MALE": "Q6581097", "FEMALE": "Q6581072"}
COMPONENT = re.compile(r"\(D-\d-\d+-\d+-\d+#\d+\)")

# Lifetime rules per role.
LATE = NON_CONTEMPORARY_ROLES | {"ORIGINATORS"}  # must only have lived before the work
LENIENT = {"COMMISSIONERS", "OWNERS", "RESIDENTS", "MEMBERS", "ASSOCIATION", "CITIZENS",
           "RIGHTS_HOLDERS"}  # fmt: skip
UNDATED = {"AUTHORS", "ORIGINATORS"}  # CbDD text authors, photographers
ARTISAN = {"ARCHITECTS", "BUILDERS", "MASTER_BUILDERS", "CONSTRUCTION_MANAGERS"}


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def get_json(url: str, retries: int = 3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as ex:  # noqa: BLE001 — 429/502/timeouts
            print(f"  retry {attempt + 1}: {ex}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    return None


def cache_file(*parts: str) -> Path:
    return CACHE.joinpath(*parts)


def lobid(gnd: str) -> dict:
    path = cache_file("gnd", f"{gnd}.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")) or {}
    # Malformed GNDs make lobid answer 500 forever: one try, cache the miss.
    data = get_json(f"https://lobid.org/gnd/{urllib.parse.quote(gnd)}.json", 1) or {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def gnd_wikidata(rec: dict) -> list[str]:
    return [
        s["id"].rsplit("/", 1)[-1]
        for s in rec.get("sameAs", [])
        if "wikidata.org/entity/" in s.get("id", "")
    ]


def gnd_hint(gnd: str, rec: dict) -> str:
    if not rec:
        return f"GND {gnd}: no lobid record (malformed or withdrawn?)"
    life = "–".join(
        "/".join(rec.get(k, [])) for k in ("dateOfBirth", "dateOfDeath")
    ).strip("–")
    jobs = "; ".join(
        x.get("label", "") for x in rec.get("professionOrOccupation", [])[:3]
    )
    return f"GND {gnd} (lobid): {rec.get('preferredName', '?')!r}" + "".join(
        f", {x}" for x in (life, jobs) if x
    )


def items(qids: set[str]) -> dict[str, dict]:
    """Label, aliases and the statements in PROPS per QID, cached for a week."""
    out, todo = {}, []
    for q in sorted(qids):
        path = cache_file("hints", f"{q}.json")
        if path.exists() and time.time() - path.stat().st_mtime < ITEM_DAYS * 86400:
            out[q] = json.loads(path.read_text(encoding="utf-8"))
        else:
            todo.append(q)
    for i in range(0, len(todo), 50):
        data = get_json(
            WD_API
            + "?"
            + urllib.parse.urlencode(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(todo[i : i + 50]),
                    "props": "labels|claims",
                    "languages": "de|mul|en",
                    "format": "json",
                }
            )
        )
        for q, e in (data or {}).get("entities", {}).items():
            if "missing" in e:
                continue
            labels = e.get("labels", {})
            item = {
                "label": (
                    labels.get("de") or labels.get("mul") or labels.get("en") or {}
                ).get("value", "")
            }
            for prop in PROPS:
                vals = []
                for c in e.get("claims", {}).get(prop, []):
                    v = c["mainsnak"].get("datavalue", {}).get("value")
                    if isinstance(v, dict):
                        v = v.get("id") or v.get("time") or v.get("text")
                    if v:
                        vals.append(v)
                item[prop] = vals
            out[q] = item
            path = cache_file("hints", f"{q}.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.2)
    return out


def year(v: str) -> int | None:
    m = re.match(r"([+-])(\d+)-", v or "")
    return (int(m.group(2)) * (-1 if m.group(1) == "-" else 1)) if m else None


def all_years(dating) -> list[int]:
    """Every year a dating covers; ranges ("1668-72", "1385-1835") are spans."""
    dating = re.sub(r"1000\s*-\s*2020", "", str(dating or ""))
    out = []
    for m in re.finditer(
        r"(?<!\d)(1\d{3}|20[0-2]\d)(?:\s*[-–]\s*(\d{2,4}))?(?!\d)", dating
    ):
        start, suffix = int(m.group(1)), m.group(2)
        end = int(m.group(1)[: 4 - len(suffix)] + suffix) if suffix else start
        out += list(range(start, end + 1)) if start < end < start + 600 else [start]
    return out


def works_of(pid: str, entities, incoming, parent) -> list[tuple[str, list[int], bool]]:
    """(role, years of the dating, own dating?) for every work of a person;
    a work without its own dating borrows its host building's."""
    out = []
    for r in incoming.get(pid, []):
        w = entities.get(r["ID"])
        if not w:
            continue
        own = bool(all_years(w.get("verbaleDating")))
        if own:
            dating = w.get("verbaleDating")
        else:
            b = (
                w
                if w.get("sType") == "OBJECT_BUILDING"
                else host_building(w["ID"], entities, parent)
            )
            dating = (b or {}).get("verbaleDating")
        out.append((r.get("sType", ""), all_years(dating), own))
    return out


def lifetime(it: dict, works: list[tuple[str, list[int], bool]]) -> tuple[str, str]:
    """('+' fits | '-' contradicts | '~' mostly fits | '?' undecidable, life span).

    A work fits if any year of its dating lies in the window the person could
    do that role in (datings list phases: "1584, Umbau 1748"). Only works
    with their own dating can contradict.
    """
    b = min((y for v in it["P569"] if (y := year(v))), default=None)
    d = max((y for v in it["P570"] if (y := year(v))), default=None)
    span = f"{b or '?'}–{d or '?'}"
    fl = [y for p in ("P1317", "P2031", "P2032") for v in it[p] if (y := year(v))]
    if b is None and d is None:
        if not fl:
            return "?", span
        b, d = min(fl) - 40, max(fl) + 40
        span = f"tätig {min(fl)}–{max(fl)}"
    verdicts = []
    for role, ys, own in works:
        if not ys or role in UNDATED:
            continue
        if role in LATE:
            ok = b is None or any(b <= y for y in ys)
        else:
            lenient = role in LENIENT
            gap = -5 if lenient else (20 if role in ARTISAN else 12)
            lo = None if b is None else b + gap
            hi = None if d is None else d + (10 if lenient else 2)
            ok = any((lo is None or y >= lo) and (hi is None or y <= hi) for y in ys)
        verdicts.append((ok, own))
    bad = sum(1 for ok, own in verdicts if not ok and own)
    good = sum(1 for ok, _ in verdicts if ok)
    if bad and bad >= good:
        return "-", span
    if bad:
        return "~", span
    return ("+" if good else "?"), span


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


def evidence(type_: str, polarity: str, summary: str, prop: str, **kw) -> dict:
    return {
        "type": type_,
        "polarity": polarity,
        "status": "verified",
        "summary": summary[:200],
        "property": prop,
        **{k: v for k, v in kw.items() if v is not None},
        "by": BY,
        "at": now(),
    }


def rejected(e: dict) -> set[str]:
    return {r.get("id") if isinstance(r, dict) else r for r in e.get("rejected") or []}


def add_candidate(e: dict, qid: str, ev: dict) -> bool:
    """Add qid as a candidate carrying ev (or add ev to it); False if ruled out."""
    if qid in rejected(e):
        return False
    for c in e.setdefault("candidates", []):
        if c["id"] == qid:
            c.setdefault("evidence", []).append(ev)
            return True
    e["candidates"].append(
        {"id": qid, "name": qid, "description": "", "evidence": [ev]}
    )
    return True


def fact(e: dict, prop: str) -> str | None:
    for f in e.get("facts") or []:
        if f.get("property") == prop and isinstance(f.get("value"), dict):
            return f["value"].get("value")
    return None


def hint(e: dict, text: str) -> None:
    """Add text to the entity's hint; a GND line replaces the earlier one."""
    keep = (
        (lambda p: not p.startswith("GND "))
        if text.startswith("GND ")
        else (lambda p: True)
    )
    parts = [p for p in (e.get("hint") or "").split(" · ") if p and keep(p)]
    e["hint"] = " · ".join(dict.fromkeys(parts + [text]))


def run(bundle: dict) -> dict[str, int]:
    entities, _, incoming, parent, _ = load()
    todo = {
        k: e for k, e in bundle["entities"].items() if e.get("status") == "reconcile"
    }
    counts: dict[str, int] = {}

    def count(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    # Forget evidence of an earlier run of this script.
    for e in todo.values():
        for c in e.get("candidates") or []:
            c["evidence"] = [
                x
                for x in c.get("evidence") or []
                if not str(x.get("by", "")).startswith("cbdd_hints")
            ]

    for e in todo.values():
        g = fact(e, "P227")
        if not g:
            continue
        rec = lobid(g)
        hint(e, gnd_hint(g, rec))
        if e.get("kind") == "person":
            found = [
                q
                for q in gnd_wikidata(rec)
                if add_candidate(
                    e,
                    q,
                    evidence(
                        "custom",
                        "+",
                        f"Der GND-Datensatz {g} verweist auf dieses Objekt",
                        "P227",
                        entity_value=g,
                    ),
                )
            ]
            e.setdefault("searches", []).append(
                {
                    "method": "lobid",
                    "query": f"GND {g} sameAs",
                    "results": len(found),
                    "by": BY,
                    "at": now(),
                }
            )
            count(f"lobid candidates {len(found)}")

    # Already linked on Wikidata (sources/query.csv is older than the item):
    # the identifier generator found the CbDD ID itself. Nothing to decide.
    for eid, e in list(todo.items()):
        linked = [
            c
            for c in e.get("candidates") or []
            if any(
                x.get("type") == "identifier"
                and x.get("property") == "P10626"
                and x.get("polarity") == "+"
                and x.get("status") == "verified"
                for x in c.get("evidence") or []
            )
        ]
        if len(linked) == 1:
            c = linked[0]
            e.update(
                status="match",
                qid=c["id"],
                route_reason=f"Already linked: {c['id']} ({c.get('name') or '?'}) carries P10626 = "
                f"{eid.removeprefix('_:cbdd:')} (sources/query.csv is older).",
            )
            e.pop("route", None)
            e.pop("candidates", None)
            del todo[eid]
            count("already linked")
        elif linked:
            hint(
                e,
                f"P10626 on several items: {', '.join(c['id'] for c in linked)} (Wikidata duplicates?)",
            )
            count("P10626 on several items")

    data = items({c["id"] for e in todo.values() for c in e.get("candidates") or []})
    for eid, e in todo.items():
        uuid = eid.removeprefix("_:cbdd:")
        src = entities.get(uuid, {})
        if e.get("kind") == "person":
            works = works_of(uuid, entities, incoming, parent)
            sex = GENDER.get(src.get("gender", ""))
            for c in e.get("candidates") or []:
                it = data.get(c["id"])
                if not it:
                    continue
                verdict, span = lifetime(it, works)
                if verdict != "?":
                    pol, text = {
                        "+": ("+", f"Lebensdaten {span} passen zu den CbDD-Werken"),
                        "~": (
                            "0",
                            f"Lebensdaten {span} passen zu den meisten CbDD-Werken",
                        ),
                        "-": (
                            "-",
                            f"Lebensdaten {span} passen nicht zu den CbDD-Werken",
                        ),
                    }[verdict]
                    c.setdefault("evidence", []).append(
                        evidence("date", pol, text, "P569", candidate_value=span)
                    )
                    count(f"lifetime {verdict}")
                if sex and it["P21"] and sex not in it["P21"]:
                    c.setdefault("evidence", []).append(
                        evidence(
                            "custom",
                            "-",
                            "Geschlecht weicht von CbDD ab",
                            "P21",
                            entity_value=sex,
                            candidate_value=it["P21"],
                        )
                    )
                    count("gender -")
        elif e.get("kind") == "building":
            street = src.get("addressStreet", "")
            parents: dict[str, str] = {}
            for c in list(e.get("candidates") or []):
                it = data.get(c["id"])
                if not it:
                    continue
                if street and address_match(street, it):
                    c.setdefault("evidence", []).append(
                        evidence(
                            "custom",
                            "+",
                            f"Adresse {street} stimmt überein",
                            "P6375",
                            entity_value=street,
                            candidate_value=it["P6375"] or it["label"],
                        )
                    )
                    count("address +")
                if COMPONENT.search(it["label"]) and it["P361"]:
                    monument = it["P361"][0]
                    c.setdefault("evidence", []).append(
                        evidence(
                            "custom",
                            "-",
                            f"nur ein Bestandteil des Baudenkmals {monument}",
                            "P361",
                            candidate_value=monument,
                        )
                    )
                    parents.setdefault(monument, c["id"])
                    count("component -")
            for monument, part in parents.items():
                add_candidate(
                    e,
                    monument,
                    evidence(
                        "custom",
                        "+",
                        f"Baudenkmal, zu dem {part} gehört",
                        "P361",
                        entity_value=part,
                    ),
                )
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("bundle", type=Path)
    ap.add_argument(
        "--write", action="store_true", help="write the evidence into the ingest file"
    )
    args = ap.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    counts = run(bundle)
    print(", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "nothing found")
    if args.write:
        args.bundle.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    else:
        print("(dry run: add --write to save)")


if __name__ == "__main__":
    main()
