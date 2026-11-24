"""
cbdd_ingest.py

Start a reconcile run: write an ingest file (the format of the
wikibase-ingest pipeline, `scripts/wikibase-ingest schema ingest`) for CbDD
people or buildings that missing/missing_<type>.csv lists without a Wikidata
item, to agentic-reconcile/to_match/<type>_<date>[_n]/ingest.json.

Each CbDD entity becomes a reconciliation entity `_:cbdd:<UUID>`:

  labels          the CbDD name in natural order ("Given Surname")
  aliases         the CbDD alternative names, in natural order
  search_names    spelling variants (first given name only, "von" forms,
                  Joseph/Josef …): searched and compared, never uploaded
  descriptions    roles and activity period (people); class and locality
                  (buildings); fit for Wikidata, because --create uploads them
  hint            places of work (people), the CbDD parent (buildings)
  facts           P10626 (the CbDD ID itself: a candidate carrying another
                  value is ruled out), GND (P227), Bildindex (P2092),
                  coordinates (P625), life dates written into the name
                  ("Kopp, Gottfried (1652–1723)": P569/P570)
  types           human (people); built structure, cultural heritage
                  ensemble, museum (buildings)
  on_no_match     curator; create with --create

and gets the claims that go out once it is matched:

  <UUID>:P10626   the link itself, route direct (no reference, like the
                  earlier match batches)
  <UUID>:P227     the CbDD GND, route curator, with the CbDD reference
  <UUID>:P2092    the CbDD Bildindex number (buildings), route curator

With --create, an entity no item fits becomes a new item (CREATE block in the
curator batch, once `route`, a game or `decide` says so). Its statements come
from the same mapping the sync tool uses for linked items
(src/config.py STATEMENT_CHECKS: gender; inception, postal code,
coordinates), plus a class (P31: human; a building class from the CbDD
functions) and, for artists, an occupation (P106). All are marked
only_if_created and carry the CbDD reference.

Run from the repository root:

    uv run python agentic-reconcile/scripts/cbdd_ingest.py \
        --csv missing/missing_people.csv --limit 50 [--offset 0] [--skip-done]
    uv run python agentic-reconcile/scripts/cbdd_ingest.py <ID> [<ID> ...] [--create]

One entity type per run (the routing policies differ). Prints the ingest file path.
"""

import argparse
import csv
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from cbdd_context import (
    NON_CONTEMPORARY_ROLES,
    TO_MATCH,
    done_ids,
    first_year,
    host_building,
    load,
    place,
)

from src.config import CBDD_ID_PID, CBDD_SOURCE_QID, STATEMENT_CHECKS
from src.utils import process_verbal_dating

HUMAN = "Q5"
# P31 classes of the CbDD buildings already linked on Wikidata: built
# structure covers 1094 of 1120, heritage ensemble and museum most of the rest.
BUILDING_TYPES = ["Q811979", "Q1516079", "Q33506"]
TYPES = {"ACTOR_PERSON": "people", "OBJECT_BUILDING": "buildings"}
KIND = {"people": "person", "buildings": "building"}

PROPERTIES = {
    "P10626": {"label": "deckenmalerei.eu-ID", "datatype": "external-id"},
    "P227": {"label": "GND-ID", "datatype": "external-id"},
    "P2092": {"label": "Bildindex-ID", "datatype": "external-id"},
    "P625": {"label": "Koordinaten", "datatype": "globe-coordinate"},
    "P569": {"label": "Geburtsdatum", "datatype": "time"},
    "P570": {"label": "Sterbedatum", "datatype": "time"},
    "P248": {"label": "Fundstelle", "datatype": "wikibase-item"},
    "P31": {"label": "ist ein(e)", "datatype": "wikibase-item"},
    "P21": {"label": "Geschlecht", "datatype": "wikibase-item"},
    "P106": {"label": "Tätigkeit", "datatype": "wikibase-item"},
    "P571": {"label": "Gründung, Erstellung bzw. Entstehung", "datatype": "time"},
    "P281": {"label": "Postleitzahl", "datatype": "string"},
}
# Classes for new building items, from the CbDD functions (first that maps
# wins; QIDs looked up on Wikidata 2026-11). Anything else: building.
BUILDING_CLASS = [
    ("PARISH_CHURCHES_BUILDINGS", "Q317557", "Pfarrkirche"),
    ("CHURCHES_BUILDINGS", "Q16970", "Kirchengebäude"),
    ("MONASTIC_CHURCHES_BUILDINGS", "Q16970", "Kirchengebäude"),
    ("ROYAL_CHURCHES", "Q16970", "Kirchengebäude"),
    ("CHAPELS_BUILDINGS", "Q108325", "Kapelle"),
    ("ROYAL_CHAPELS", "Q108325", "Kapelle"),
    ("HUNTING_LODGES", "Q1424449", "Jagdschloss"),
    ("ROYAL_PALACES", "Q751876", "Schloss"),
    ("PLEASURE_PALACES", "Q751876", "Schloss"),
    ("PALATIAL_MANSIONS", "Q751876", "Schloss"),
    ("TOWN_HOUSES", "Q1021106", "Bürgerhaus"),
    ("HOMES", "Q3947", "Haus"),
]
BUILDING = ("Q41176", "Gebäude")
# Occupations for new person items, from CbDD roles of artists.
OCCUPATION = {
    "PAINTERS": "Q1028181",  # painter
    "ILLUSIONISTIC_CEILING_PAINTERS": "Q1028181",
    "PLASTERERS": "Q15284879",  # plasterer (stuccoist)
    "ARCHITECTS": "Q42973",  # architect
    "BUILDERS": "Q1340643",  # master builder
    "SCULPTORS": "Q1281618",  # sculptor
}
# Wikidata's format constraint of P227; a value that fails it is a CbDD error.
GND_FORMAT = re.compile(
    r"^(1[0123]?\d{7}[0-9X]|[47]\d{6}-\d|[1-9]\d{0,7}-[0-9X]|3\d{7}[0-9X])$"
)

ROLE_DE = {
    "PAINTERS": "Maler",
    "ILLUSIONISTIC_CEILING_PAINTERS": "Quadraturmaler",
    "PLASTERERS": "Stuckateur",
    "ARCHITECTS": "Architekt",
    "BUILDERS": "Baumeister",
    "CONSTRUCTION_MANAGERS": "Bauleiter",
    "SCULPTORS": "Bildhauer",
    "IMAGE_CARVERS": "Bildschnitzer",
    "CABINETMAKERS": "Kunstschreiner",
    "CARPENTERS": "Zimmermann",
    "DESIGNERS": "Entwerfer",
    "ARTISTS": "Künstler",
    "POLYCHROMERS": "Fassmaler",
    "COMMISSIONERS": "Auftraggeber",
    "TEMPLATE_PROVIDERS": "Vorlagengeber",
    "REFERENCE_PERSONS": "Bezugsperson",
    "DONORS": "Stifter",
    "OWNERS": "Eigentümer",
    "RESIDENTS": "Bewohner",
    "AUTHORS": "Autor",
    "ORIGINATORS": "Fotograf",
}

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
NAME_SWAPS = [("Joseph", "Josef"), ("Carl", "Karl"), ("Christoph", "Christof"),
              ("Franz", "Frantz"), ("Jakob", "Jacob"), ("Caspar", "Kaspar"),
              ("Conrad", "Konrad"), ("Matthias", "Mathias")]  # fmt: skip
MAX_TERM = 250


LIFE_IN_NAME = re.compile(r"\(\s*(?:\*\s*)?(\d{4})?\s*[–-]\s*(?:†\s*)?(\d{4})?\s*\)")


def life_in_name(names: list[str]) -> tuple[int | None, int | None]:
    """Life dates written into a CbDD name: "Kopp, Gottfried (1652–1723)"."""
    for n in names:
        m = LIFE_IN_NAME.search(n)
        if m and (m.group(1) or m.group(2)):
            return (
                int(m.group(1)) if m.group(1) else None,
                int(m.group(2)) if m.group(2) else None,
            )
    return None, None


def variants(name: str) -> list[str]:
    """'Surname, Given, Title' → names in natural order, best first."""
    name = re.sub(r"\s*\([^)]*\)", "", name)
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
    out = [re.sub(r"\s+", " ", b).strip() for b in base]
    for b in base[:2]:
        for a, c in NAME_SWAPS:
            if re.search(rf"\b{a}\b", b):
                out.append(re.sub(rf"\b{a}\b", c, b))
            elif re.search(rf"\b{c}\b", b):
                out.append(re.sub(rf"\b{c}\b", a, b))
    return list(dict.fromkeys(o for o in out if len(o) > 2))


def term(text: str) -> str:
    """A label/description/alias Wikidata accepts: one line, ≤250 characters."""
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= MAX_TERM else text[: MAX_TERM - 1] + "…"


def gnd(e: dict) -> str | None:
    value = str((e.get("normdata") or {}).get("gnd") or "").strip()
    return value or None


def bildindex(e: dict) -> str | None:
    m = re.search(r"\d+", str((e.get("normdata") or {}).get("bildindex") or ""))
    return m.group(0) if m else None


def string(value: str) -> dict:
    return {"type": "string", "value": value}


def building_class(b: dict) -> tuple[str, str]:
    functions = set(b.get("functions") or [])
    for fn, qid, label in BUILDING_CLASS:
        if fn in functions:
            return qid, label
    return BUILDING


def roles_of(pid: str, incoming) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in incoming.get(pid, []):
        out[r.get("sType", "")] = out.get(r.get("sType", ""), 0) + 1
    return out


def person_entity(p: dict, entities, incoming, parent) -> dict:
    names = [p.get("appellation", "")] + list(p.get("alternativeNames", []))
    natural = list(dict.fromkeys(term(variants(n)[0]) for n in names if variants(n)))
    all_names = list(dict.fromkeys(term(v) for n in names for v in variants(n)))
    roles: dict[str, int] = {}
    years: list[int] = []
    places: dict[str, int] = {}
    for r in incoming.get(p["ID"], []):
        w = entities.get(r["ID"])
        if not w:
            continue
        role = r.get("sType", "")
        roles[role] = roles.get(role, 0) + 1
        b = (
            w
            if w.get("sType") == "OBJECT_BUILDING"
            else host_building(w["ID"], entities, parent)
        )
        y = first_year(w.get("verbaleDating") or (b or {}).get("verbaleDating", ""))
        if y and role not in NON_CONTEMPORARY_ROLES:
            years.append(y)
        if b and place(b):
            places[place(b).split(",")[0]] = places.get(place(b).split(",")[0], 0) + 1
    role_text = ", ".join(
        ROLE_DE.get(k, k.lower())
        for k, _ in sorted(roles.items(), key=lambda x: -x[1])[:3]
    )
    desc = role_text or "Person"
    if years:
        span = (
            f"{min(years)}–{max(years)}" if min(years) != max(years) else str(years[0])
        )
        desc += f", tätig {span}"
    top = [k for k, _ in sorted(places.items(), key=lambda x: -x[1])[:3]]
    label = natural[0] if natural else term(p.get("appellation", ""))
    e = {
        "kind": "person",
        "status": "reconcile",
        "on_no_match": "curator",
        "labels": {"de": label},
        "descriptions": {"de": term(desc if desc != label else f"Person, {desc}")},
        "facts": [{"property": CBDD_ID_PID, "value": string(p["ID"])}],
        "types": [HUMAN],
        "source": "src:cbdd",
        "url": f"https://www.deckenmalerei.eu/{p['ID']}",
    }
    if natural[1:]:
        e["aliases"] = {"de": natural[1:]}
    extra = [n for n in all_names if n not in natural]
    if extra:
        e["search_names"] = {"de": extra}
    if top:
        e["hint"] = "CbDD: Werke in " + ", ".join(top)
    for prop, y in zip(("P569", "P570"), life_in_name(names), strict=True):
        if y:
            e["facts"].append(
                {
                    "property": prop,
                    "value": {
                        "type": "time",
                        "time": f"+{y}-00-00T00:00:00Z",
                        "precision": 9,
                    },
                }
            )
    return e


def building_entity(b: dict, entities, parent) -> dict:
    where = ", ".join(
        x for x in (b.get("addressStreet"), b.get("addressLocality")) if x
    )
    dating = re.sub(
        r"1000\s*-\s*2020,?\s*", "", str(b.get("verbaleDating") or "")
    ).strip(", ")
    cls = building_class(b)[1]
    desc = f"{cls} in {b['addressLocality']}" if b.get("addressLocality") else cls
    e = {
        "kind": "building",
        "status": "reconcile",
        "on_no_match": "curator",
        "labels": {"de": term(b.get("appellation", ""))},
        "descriptions": {"de": term(desc)},
        "facts": [{"property": CBDD_ID_PID, "value": string(b["ID"])}],
        "types": list(BUILDING_TYPES),
        "source": "src:cbdd",
        "url": f"https://www.deckenmalerei.eu/{b['ID']}",
    }
    alt = [
        term(a) for a in b.get("alternativeNames", []) if term(a) != e["labels"]["de"]
    ]
    if alt:
        e["aliases"] = {"de": list(dict.fromkeys(alt))}
    try:
        lat, lon = float(b["locationLat"]), float(b["locationLng"])
        e["facts"].append(
            {
                "property": "P625",
                "value": {"type": "coordinate", "lat": lat, "lon": lon},
            }
        )
    except (KeyError, TypeError, ValueError):
        pass
    hint = (
        [f"CbDD: {where}" + (f", {dating}" if dating else "")]
        if where or dating
        else []
    )
    if b["ID"] in parent:
        pe = entities.get(parent[b["ID"]], {})
        hint.append(f"CbDD: Teil von {pe.get('appellation', parent[b['ID']])}")
    if hint:
        e["hint"] = " · ".join(hint)
    return e


def value_for(pid: str, raw: str) -> dict | str | None:
    """A sync-tool value (src/config.py conventions) as an ingest file value."""
    dtype = PROPERTIES[pid]["datatype"]
    if dtype == "wikibase-item":
        return raw if re.fullmatch(r"Q\d+", raw) else None
    if dtype == "time":
        return (
            {"type": "time", "time": f"+{raw}-00-00T00:00:00Z", "precision": 9}
            if re.fullmatch(r"\d{4}", raw)
            else None
        )
    return string(raw)


def creation_claims(eid: str, e: dict, kind: str, incoming) -> list[dict]:
    """Statements of a new item: class, the sync tool's statements, occupation."""
    uuid = e["ID"]
    check: dict[str, Any] = STATEMENT_CHECKS[kind]
    value_maps: dict[str, dict[str, str]] = check.get("value_maps", {})
    values: list[tuple[str, dict | str]] = []
    if kind == "people":
        values.append(("P31", HUMAN))
        roles = roles_of(uuid, incoming)
        for occ in dict.fromkeys(OCCUPATION[r] for r in roles if r in OCCUPATION):
            values.append(("P106", occ))
    else:
        values.append(("P31", building_class(e)[0]))
    row = {**e, "processedDating": process_verbal_dating(e.get("verbaleDating"))}
    for col, pid in check["column_to_pid"].items():
        raw = str(row.get(col) or "").strip()
        if pid in value_maps:
            raw = value_maps[pid].get(
                raw, ""
            )  # unmapped values are skipped, as in sync
        v = value_for(pid, raw) if raw else None
        if v is not None:
            values.append((pid, v))
    coord = check.get("coordinate")
    if coord:
        try:
            lat, lon = float(e[coord["lat"]]), float(e[coord["lng"]])
            values.append(
                (coord["pid"], {"type": "coordinate", "lat": lat, "lon": lon})
            )
        except (KeyError, TypeError, ValueError):
            pass
    ref = {
        "source": "src:cbdd",
        "snaks": [{"property": CBDD_ID_PID, "value": string(uuid)}],
    }
    out = []
    for n, (pid, value) in enumerate(values):
        out.append(
            {
                "id": f"{uuid}:new:{pid}:{n}",
                "subject": eid,
                "property": pid,
                "value": value,
                "reference": ref,
                "route": "curator",
                "route_reason": "Statement of the new item, from the CbDD record (sync-tool mapping).",
                "extraction": "field",
                "only_if_created": True,
                "hint": f"https://www.deckenmalerei.eu/{uuid}",
            }
        )
    return out


def claims_for(eid: str, e: dict, ent: dict, kind: str) -> list[dict]:
    uuid = e["ID"]
    out = [
        {
            "id": f"{uuid}:P10626",
            "subject": eid,
            "property": CBDD_ID_PID,
            "value": string(uuid),
            "route": "direct",
            "route_reason": "The link itself: written once the entity is matched.",
            "extraction": "field",
            "hint": f"https://www.deckenmalerei.eu/{uuid}",
        }
    ]
    ref = {
        "source": "src:cbdd",
        "snaks": [{"property": CBDD_ID_PID, "value": string(uuid)}],
    }
    g = gnd(e)
    if g:
        ent["facts"].append({"property": "P227", "value": string(g)})
        if GND_FORMAT.match(g):
            out.append(
                {
                    "id": f"{uuid}:P227",
                    "subject": eid,
                    "property": "P227",
                    "value": string(g),
                    "reference": ref,
                    "route": "curator",
                    "route_reason": "GND from the CbDD normdata; check that it names this "
                    f"{'person' if kind == 'people' else 'building'} (lobid name in the hint).",
                    "extraction": "field",
                    "hint": f"CbDD normdata of https://www.deckenmalerei.eu/{uuid}",
                }
            )
        else:
            ent["hint"] = (
                ent.get("hint", "") + f" · GND {g!r} is malformed (CbDD correction)"
            ).lstrip(" ·")
    bi = bildindex(e) if kind == "buildings" else None
    if bi:
        ent["facts"].append({"property": "P2092", "value": string(bi)})
        out.append(
            {
                "id": f"{uuid}:P2092",
                "subject": eid,
                "property": "P2092",
                "value": string(bi),
                "reference": ref,
                "route": "curator",
                "route_reason": "Bildindex object number from the CbDD normdata.",
                "extraction": "field",
                "hint": f"CbDD normdata of https://www.deckenmalerei.eu/{uuid}",
            }
        )
    return out


def run_dir(kind: str) -> Path:
    stem = f"{kind}_{datetime.date.today().isoformat()}"
    n, name = 1, stem
    while (TO_MATCH / name).exists() or (TO_MATCH / f"{name}.qs").exists():
        n += 1
        name = f"{stem}_{n}"
    return TO_MATCH / name


def build(
    ids: list[str], entities, incoming, parent, qids, label: str, create: bool = False
) -> tuple[dict, str]:
    chosen = [entities[i] for i in ids if i in entities]
    unknown = [i for i in ids if i not in entities]
    if unknown:
        print(
            f"not in sources/entities.json, skipped: {', '.join(unknown)}",
            file=sys.stderr,
        )
    linked = [e["ID"] for e in chosen if e["ID"] in qids]
    if linked:
        print(
            f"already linked in query.csv, skipped: {', '.join(linked)}",
            file=sys.stderr,
        )
    chosen = [e for e in chosen if e["ID"] not in qids]
    if any(e.get("sType") not in TYPES for e in chosen):
        sys.exit("only ACTOR_PERSON and OBJECT_BUILDING entities are supported")
    kinds = {TYPES[e["sType"]] for e in chosen}
    if len(kinds) != 1:
        sys.exit("one entity type per run: people or buildings")
    (kind,) = kinds
    bundle_entities, claims = {}, []
    for e in chosen:
        eid = f"_:cbdd:{e['ID']}"
        ent = (
            person_entity(e, entities, incoming, parent)
            if kind == "people"
            else building_entity(e, entities, parent)
        )
        claims += claims_for(eid, e, ent, kind)
        if create:
            ent["on_no_match"] = "create"
            claims += creation_claims(eid, e, kind, incoming)
        bundle_entities[eid] = ent
    today = datetime.date.today().isoformat()
    return {
        "format": "wikibase-ingest",
        "version": 2,
        "id": "",
        "project": f"CbDD → Wikidata: {kind}, {today} ({label})",
        "origin": "dem Datenexport von deckenmalerei.eu",
        "language": "de",
        "create_requires": ["P31"],
        "sources": {
            "src:cbdd": {
                "label": "Corpus der barocken Deckenmalerei in Deutschland (deckenmalerei.eu)",
                "url": "https://www.deckenmalerei.eu/",
                "snaks": [{"property": "P248", "value": CBDD_SOURCE_QID}],
            }
        },
        "properties": PROPERTIES,
        "entities": bundle_entities,
        "claims": claims,
    }, kind


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("ids", nargs="*", help="CbDD entity IDs")
    ap.add_argument("--csv", help="missing_*.csv to take IDs from (column ID)")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument(
        "--skip-done", action="store_true", help="leave out IDs of earlier runs"
    )
    ap.add_argument(
        "--out", type=Path, help="run folder (default: to_match/<type>_<date>)"
    )
    ap.add_argument(
        "--create",
        action="store_true",
        help="create items for entities no item fits (on_no_match create)",
    )
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
        label = f"`{args.csv}`, rows {args.offset}–{args.offset + len(ids) - 1}" + (
            " after skipping earlier runs" if args.skip_done else ""
        )
    else:
        label = "IDs given by the user"
    if not ids:
        sys.exit("no IDs to process")

    entities, _, incoming, parent, qids = load()
    bundle, kind = build(ids, entities, incoming, parent, qids, label, args.create)
    folder = args.out or run_dir(kind)
    bundle["id"] = f"cbdd-{folder.name}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "ingest.json"
    if path.exists():
        sys.exit(f"{path} exists; pick another --out")
    path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(path)
    print(
        f"{len(bundle['entities'])} {kind}, {len(bundle['claims'])} claims",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
