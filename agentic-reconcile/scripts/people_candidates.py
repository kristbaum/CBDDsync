"""
people_candidates.py

Bulk candidate search for CbDD people: for every person, the Wikidata humans
found by name (full-text search over labels and aliases, several name
variants), the items carrying the CbDD GND (P227), and the Wikidata item the
GND record itself links to (lobid sameAs), with the statements needed to
decide (dates, occupation, gender, places, offices, existing P10626). Prints
one compact block per person, best candidates first, with flags:

    GND     the item carries the CbDD GND; GND(lobid,no-P227): only the GND
            record links to it (a P227 repair candidate)
    NAME    all name tokens of a CbDD name variant occur in the item's label/aliases
    LIFE+   the lifetime fits the CbDD works (see the rules in SKILL.md)
    LIFE-   the lifetime contradicts most CbDD works with their own dating
    LIFE~   the lifetime fits most works, but not all (check the datings)
    SEX-    the gender differs
    CBDD=…  the item already has a deckenmalerei.eu ID (possible CbDD duplicate)

Run from the repository root (reads sources/*.json and sources/query.csv):

    python3 agentic-reconcile/scripts/people_candidates.py \
        --csv missing/missing_people.csv [--offset 0] [--limit 2000] [--skip-done]

All Wikidata/GND responses are cached in agentic-reconcile/.cache/, so an
interrupted run resumes; progress goes to stderr.
"""

import argparse
import csv
import re
import sys
import time
import unicodedata
import urllib.parse

from building_candidates import WD_API, cached, get_json, sparql
from cbdd_context import (
    NON_CONTEMPORARY_ROLES,
    done_ids,
    first_year,
    host_building,
    load,
    place,
)

PROPS = [
    "P31", "P21", "P569", "P570", "P1317", "P2031", "P2032", "P106",
    "P19", "P20", "P937", "P39", "P10626", "P227", "P53",
]  # fmt: skip
LABELLED = ("P106", "P19", "P20", "P937", "P39", "P53")
TITLES = re.compile(
    r"^(Abt|Äbtissin|Fürstäbtissin|Fürstabt|Propst|Pröpstin|Prior|Priorin|Freiherr"
    r"|Freifrau|Freiin|Graf|Gräfin|Reichsgraf|Reichsgräfin|Fürst|Fürstin|Herzog"
    r"|Herzogin|Markgraf|Markgräfin|Landgraf|Landgräfin|Kurfürst|Kurfürstin|König"
    r"|Königin|Kaiser|Kaiserin|Prinz|Prinzessin|Bischof|Fürstbischof|Erzbischof"
    r"|Kardinal|Pfalzgraf|Pfalzgräfin|Edler|Ritter|Pater|P\.|Frater|geb\..*|Dr\.?"
    r"|[IVX]+\.?|d\. ?[ÄÄJ]\.|der Ältere|der Jüngere)$"
)
PARTICLE = re.compile(
    r"\s+(von und zu|von der|von dem|von|zu|vom|de|di|da|del|van|van der)$"
)
GENDER = {"MALE": "Q6581097", "FEMALE": "Q6581072"}
LATE = NON_CONTEMPORARY_ROLES | {"ORIGINATORS"}
LENIENT = {"COMMISSIONERS", "OWNERS", "RESIDENTS", "MEMBERS", "ASSOCIATION", "CITIZENS",
           "RIGHTS_HOLDERS"}  # fmt: skip
UNDATED = {"AUTHORS", "ORIGINATORS"}  # CbDD text authors, photographers
ARTISAN = {"ARCHITECTS", "BUILDERS", "MASTER_BUILDERS", "CONSTRUCTION_MANAGERS"}
NAME_SWAPS = [("Joseph", "Josef"), ("Carl", "Karl"), ("Christoph", "Christof"),
              ("Franz", "Frantz"), ("Jakob", "Jacob"), ("Caspar", "Kaspar"),
              ("Conrad", "Konrad"), ("Matthias", "Mathias")]  # fmt: skip


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ß", "ss"))
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", norm(s)) if len(t) > 1}


def variants(name: str) -> list[str]:
    """'Surname, Given, Title' → search strings in natural order, best first."""
    parts = [p.strip() for p in name.split(",") if p.strip()]
    titled = any(TITLES.match(p) for p in parts[1:])
    if len(parts) < 2:
        base = [name.strip()]
    else:
        surname, rest = parts[0], [p for p in parts[1:] if not TITLES.match(p)]
        given = re.sub(r"\s+[IVX]+\.?$", "", rest[0]) if rest else ""
        m = PARTICLE.search(given)
        particle = ""
        if m:
            particle, given = m.group(1), given[: m.start()]
        base = [" ".join(x for x in (given, particle, surname) if x)]
        if given and " " in given:
            base.append(" ".join(x for x in (given.split()[0], particle, surname) if x))
        if given and not particle and titled:
            base.append(f"{given} von {surname}")
            # "Albertina Friederike, Baden-Durlach, Markgräfin": given name first
            base.append(f"{surname} von {given}")
        if given and " " in given:
            base.append(
                " ".join(x for x in (given.split()[-1], particle, surname) if x)
            )
    out = []
    for b in base:
        out.append(re.sub(r"\s+", " ", b).strip())
    for b in base[:2]:
        for a, c in NAME_SWAPS:
            if re.search(rf"\b{a}\b", b):
                out.append(re.sub(rf"\b{a}\b", c, b))
            elif re.search(rf"\b{c}\b", b):
                out.append(re.sub(rf"\b{c}\b", a, b))
    return list(dict.fromkeys(o for o in out if len(o) > 2))


def search(text: str) -> list[str]:
    def fetch():
        data = get_json(
            WD_API
            + "?"
            + urllib.parse.urlencode(
                {
                    "action": "query",
                    "list": "search",
                    "srlimit": 12,
                    "format": "json",
                    "srsearch": f"{text} haswbstatement:P31=Q5",
                }
            )
        )
        time.sleep(0.1)
        if data is None:
            return None
        return [h["title"] for h in data.get("query", {}).get("search", [])]

    key = re.sub(r"[^\w-]+", "_", norm(text))[:120]
    return cached(f"psearch/{key}.json", fetch) or []


def year(v: str) -> int | None:
    m = re.match(r"([+-])(\d+)-", v or "")
    return (int(m.group(2)) * (-1 if m.group(1) == "-" else 1)) if m else None


def entities(qids: set[str]) -> dict[str, dict]:
    out, todo = {}, []
    for q in sorted(qids):
        p = cached(f"pitems/{q}.json", lambda: None)
        if p is not None:
            out[q] = p
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
                    "props": "labels|aliases|descriptions|claims|sitelinks",
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
                "aliases": sorted(
                    {a["value"] for v in e.get("aliases", {}).values() for a in v}
                    | {v["value"] for v in e.get("labels", {}).values()}
                ),
                "dewiki": e.get("sitelinks", {}).get("dewiki", {}).get("title"),
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
            cached(f"pitems/{q}.json", lambda item=item: item)
        time.sleep(0.2)
    return out


def labels(qids: set[str]) -> dict[str, str]:
    out, todo = {}, []
    for q in sorted(qids):
        v = cached(f"labels/{q}.json", lambda: None)
        if v is not None:
            out[q] = v
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
                    "props": "labels",
                    "languages": "de|mul|en",
                    "format": "json",
                }
            )
        )
        for q, e in (data or {}).get("entities", {}).items():
            d = e.get("labels", {})
            lab = (d.get("de") or d.get("mul") or d.get("en") or {}).get("value", q)
            out[q] = lab
            cached(f"labels/{q}.json", lambda lab=lab: lab)
    return out


def lobid(gnd: str) -> dict:
    data = cached(
        f"gnd/{gnd}.json",
        lambda: (
            get_json(f"https://lobid.org/gnd/{urllib.parse.quote(gnd)}.json", 1) or {}
        ),
    )
    return data or {}


def gnd_wikidata(rec: dict) -> list[str]:
    return [
        s["id"].rsplit("/", 1)[-1]
        for s in rec.get("sameAs", [])
        if "wikidata.org/entity/" in s.get("id", "")
    ]


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


def lifetime_check(it: dict, works: list[tuple[str, list[int], bool]]) -> str:
    """
    '+' fits, '-' contradicts, '?' undecidable.

    works: (role, years of the dating, own dating?) per related work. A work
    fits if any year of its dating lies in the window the person could do
    that role in (datings list phases: "1584, Umbau 1748"). Only works with
    their own dating can contradict; a dating borrowed from the host building
    (often its foundation) cannot.
    """
    b = min((y for v in it["P569"] if (y := year(v))), default=None)
    d = max((y for v in it["P570"] if (y := year(v))), default=None)
    fl = [y for p in ("P1317", "P2031", "P2032") for v in it[p] if (y := year(v))]
    if b is None and d is None:
        if not fl:
            return "?"
        b, d = min(fl) - 40, max(fl) + 40
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
        return "-"
    if bad:
        return "~"  # mostly fits; the misfits are usually imprecise datings
    return "+" if good else "?"


def short_date(vals: list[str]) -> str:
    return "/".join(str(year(v)) for v in vals[:2]) or "?"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--csv")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--skip-done", action="store_true")
    ap.add_argument("--top", type=int, default=4)
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
    ents, _, incoming, parent, _ = load()
    people = [ents[i] for i in ids if i in ents]

    gnds = sorted({g for p in people if (g := (p.get("normdata") or {}).get("gnd"))})
    hits: dict[str, list[str]] = {}
    for i in range(0, len(gnds), 200):
        rows = sparql(
            "SELECT ?item ?v WHERE { VALUES ?v { "
            + " ".join(f'"{g}"' for g in gnds[i : i + 200])
            + " } ?item wdt:P227 ?v }"
        )
        for r in rows or []:
            hits.setdefault(r["v"]["value"], []).append(
                r["item"]["value"].rsplit("/", 1)[-1]
            )
    recs = {}
    for n, g in enumerate(gnds):
        recs[g] = lobid(g)
        if n % 100 == 0:
            print(f"  gnd: {n}/{len(gnds)}", file=sys.stderr)

    found: dict[str, dict[str, set[str]]] = {}
    for n, p in enumerate(people):
        names = [p.get("appellation", "")] + list(p.get("alternativeNames", []))
        vs = list(dict.fromkeys(v for nm in names for v in variants(nm)))
        f: dict[str, set[str]] = {}
        for v in vs[:8]:
            for q in search(v):
                f.setdefault(q, set()).add(v)
        g = (p.get("normdata") or {}).get("gnd")
        for q in hits.get(g or "-", []) + gnd_wikidata(recs.get(g or "-", {})):
            f.setdefault(q, set()).add("GND")
        found[p["ID"]] = f
        if n % 50 == 0:
            print(f"  search: {n}/{len(people)}", file=sys.stderr)

    items = entities({q for f in found.values() for q in f})
    labs = labels(
        {
            v
            for it in items.values()
            for pr in LABELLED
            for v in it[pr]
            if v.startswith("Q")
        }
    )

    for i, p in enumerate(people):
        g = (p.get("normdata") or {}).get("gnd")
        roles, years, late, places, works = set(), [], [], {}, []
        for r in incoming.get(p["ID"], []):
            w = ents.get(r["ID"])
            if not w:
                continue
            roles.add(r.get("sType", ""))
            b = (
                w
                if w.get("sType") == "OBJECT_BUILDING"
                else host_building(w["ID"], ents, parent)
            )
            own = bool(all_years(w.get("verbaleDating")))
            dating = w.get("verbaleDating") if own else (b or {}).get("verbaleDating")
            works.append((r.get("sType", ""), all_years(dating), own))
            y = first_year(dating) if own else None
            if y and r.get("sType") not in UNDATED:
                (late if r.get("sType") in LATE else years).append(y)
            if b:
                places[place(b)] = places.get(place(b), 0) + 1
        names = [p.get("appellation", "")] + list(p.get("alternativeNames", []))
        vs = [v for nm in names for v in variants(nm)]
        head = (
            f"#{args.offset + i} {p.get('appellation')} | {p['ID']} | {p.get('gender', '')[:1]}"
            f" | {','.join(sorted(roles)) or '-'}"
            f" | {f'{min(years)}-{max(years)}' if years else '-'}"
            f"{f' late:{min(late)}-{max(late)}' if late else ''}"
            f" | {'; '.join(k for k, _ in sorted(places.items(), key=lambda x: -x[1])[:3])}"
        )
        print(head)
        if p.get("alternativeNames"):
            print(f"   alt: {'; '.join(p['alternativeNames'])}")
        if g:
            rec = recs.get(g, {})
            print(
                f"   GND {g} = {rec.get('preferredName', '?')!r} "
                f"{'/'.join(rec.get('dateOfBirth', []))}–{'/'.join(rec.get('dateOfDeath', []))} "
                f"{'; '.join(x.get('label', '') for x in rec.get('professionOrOccupation', [])[:3])}"
                f" wd={','.join(gnd_wikidata(rec)) or '-'}"
            )
        cands = []
        for q, via in found[p["ID"]].items():
            it = items.get(q)
            if not it or "Q5" not in it["P31"]:
                continue
            gm = "GND" in via or (g and g in it["P227"])
            alias_tokens = [tokens(a) for a in it["aliases"] + [it["label"]]]
            nm = any(
                tokens(v) and any(tokens(v) <= at for at in alias_tokens) for v in vs
            )
            sur = tokens(names[0].split(",")[0])
            surm = bool(sur) and any(sur <= at for at in alias_tokens)
            if not (gm or nm or surm):
                continue
            life = lifetime_check(it, works)
            sex = GENDER.get(p.get("gender", ""))
            sexbad = bool(sex and it["P21"] and sex not in it["P21"])
            score = (not gm, not nm, life == "-", sexbad, life != "+")
            cands.append((score, q, it, gm, nm, life, sexbad))
        cands.sort(key=lambda c: c[0])
        for _, q, it, gm, nm, life, sexbad in cands[: args.top]:
            if gm:
                flags = "GND " if g in it["P227"] else "GND(lobid,no-P227) "
            else:
                flags = ""
            flags += ("NAME " if nm else "") + f"LIFE{life} "
            flags += "SEX- " if sexbad else ""
            if it["P10626"]:
                flags += "CBDD=" + ",".join(x[:8] for x in it["P10626"]) + " "
            if g and it["P227"] and g not in it["P227"]:
                flags += f"gnd={it['P227'][0]} "
            occ = ",".join(labs.get(o, o) for o in it["P106"][:3])
            plc = ",".join(labs.get(o, o) for pr in ("P19", "P20") for o in it[pr][:1])
            off = ",".join(labs.get(o, o) for o in it["P39"][:2])
            print(
                f"   {flags}{q} {it['label'][:50]!r} [{it['desc'][:60]}] "
                f"{short_date(it['P569'])}–{short_date(it['P570'])}"
                f"{' fl' + short_date(it['P1317'] + it['P2031']) if it['P1317'] or it['P2031'] else ''}"
                f" | {occ[:50]} | {plc[:40]}{' | ' + off[:50] if off else ''}"
                f"{' dw' if it['dewiki'] else ''}"
            )
        if not cands:
            print("   (no candidate)")


if __name__ == "__main__":
    main()
