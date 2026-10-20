"""
write_batch.py

Turn a decisions file (JSON, written while reviewing candidates) into the
three outputs of a reconcile run in agentic-reconcile/to_match/:

    <type>_<date>.qs         P10626 additions, high matches only
    <type>_<date>_repair.qs  fixes for errors found on Wikidata (only if any)
    <type>_<date>.md         report covering every entity, every repair,
                             CbDD-side corrections and notes

and run the self-checks: QuickStatements line format, no QID or CbDD ID twice,
every entity decided once, and (unless --offline) a live check that no matched
item has gained a P10626 meanwhile and that every repair still applies.

    python3 agentic-reconcile/scripts/write_batch.py decisions.json [--offline]

Decisions file:

    {
      "type": "buildings",                      # or "people"
      "input": "`missing/missing_buildings.csv`, rows 0–564",
      "method": "optional sentence on how candidates were found",
      "entities": [
        {"id": "<CbDD UUID>", "decision": "high" | "medium" | "no",
         "qid": "Q…",                           # high: the match; medium: best candidate
         "evidence": "…",                       # Markdown; may be a table
         "rejected": "Q… (why), …"}             # optional
      ],
      "repairs": [
        {"entity": "Q…", "prop": "P227", "value": "\\"4821135-7\\"",
         "prefix": "" | "-",                    # "-" removes a statement
         "cbdd": "<CbDD UUID>",                 # adds the CbDD reference
         "why": "…"}
      ],
      "cbdd_corrections": ["…"],                # errors only CbDD can fix
      "notes": ["…"]
    }
"""

import argparse
import datetime
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SOURCES = Path("sources")
TO_MATCH = Path("agentic-reconcile/to_match")
UA = "CBDDsync-agentic-reconcile/0.2 (https://github.com/kristbaum/CBDDsync)"
CBDD_SOURCE_QID = "Q107174967"  # same constants as src/config.py
CBDD_ID_PID = "P10626"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
QS_LINE = re.compile(rf'Q\d+\t{CBDD_ID_PID}\t"{UUID}"')


def claims(qids: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(qids), 50):
        url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(qids[i : i + 50]),
                "props": "claims",
                "format": "json",
            }
        )
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            for q, e in json.load(r)["entities"].items():
                out[q] = e
    return out


def values(entity: dict, prop: str) -> list[str]:
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        v = c["mainsnak"].get("datavalue", {}).get("value")
        if isinstance(v, dict):
            v = v.get("id") or v.get("text") or json.dumps(v)
        out.append(
            f'"{v}"' if isinstance(v, str) and not re.fullmatch(r"Q\d+", v) else v
        )
    return out


def repair_line(r: dict) -> str:
    parts = [f"{r.get('prefix', '')}{r['entity']}", r["prop"], r["value"]]
    if r.get("cbdd") and r.get("prefix", "") != "-":
        parts += ["S248", CBDD_SOURCE_QID, f"S{CBDD_ID_PID[1:]}", f'"{r["cbdd"]}"']
    return "\t".join(parts)


def base_name(kind: str) -> Path:
    stem = f"{kind}_{datetime.date.today().isoformat()}"
    n, name = 1, stem
    while (TO_MATCH / f"{name}.qs").exists() or (TO_MATCH / f"{name}.md").exists():
        n += 1
        name = f"{stem}_{n}"
    return TO_MATCH / name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("decisions")
    ap.add_argument("--offline", action="store_true", help="skip live Wikidata checks")
    args = ap.parse_args()

    d = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    names = {
        e["ID"]: e.get("appellation", "")
        for e in json.loads((SOURCES / "entities.json").read_text(encoding="utf-8"))
        if isinstance(e, dict) and e.get("ID")
    }
    ents, repairs = d["entities"], d.get("repairs", [])
    errors = []

    seen = [e["id"] for e in ents]
    if len(seen) != len(set(seen)):
        errors.append("an entity is decided more than once")
    for e in ents:
        if e["decision"] not in ("high", "medium", "no"):
            errors.append(f"{e['id']}: unknown decision {e['decision']!r}")
        if e["decision"] == "high" and not re.fullmatch(r"Q\d+", e.get("qid", "")):
            errors.append(f"{e['id']}: high without a QID")
    high = [e for e in ents if e["decision"] == "high"]
    for key in ("qid", "id"):
        vals = [e[key] for e in high]
        dup = {v for v in vals if vals.count(v) > 1}
        if dup:
            errors.append(
                f"in the batch twice ({key}): {sorted(dup)} — downgrade to medium"
            )
    qs = [f'{e["qid"]}\t{CBDD_ID_PID}\t"{e["id"]}"' for e in high]
    errors += [f"bad line: {line!r}" for line in qs if not QS_LINE.fullmatch(line)]
    rep = [repair_line(r) for r in repairs]

    if not args.offline:
        live = claims(sorted({e["qid"] for e in high} | {r["entity"] for r in repairs}))
        for e in high:
            item = live.get(e["qid"], {})
            if "missing" in item or item.get("id", e["qid"]) != e["qid"]:
                errors.append(f"{e['qid']}: missing or redirected")
            elif values(item, CBDD_ID_PID):
                errors.append(
                    f"{e['qid']} already has P10626 {values(item, CBDD_ID_PID)}"
                )
        for r, line in zip(repairs, rep, strict=True):
            present = r["value"] in values(live.get(r["entity"], {}), r["prop"])
            if r.get("prefix") == "-" and not present:
                errors.append(f"repair no longer applies (value gone): {line!r}")
            if r.get("prefix", "") == "" and present:
                print(f"note: already present, kept for the reference: {line!r}")
    if errors:
        sys.exit("NOT WRITTEN:\n- " + "\n- ".join(errors))

    base = base_name(d["type"])
    base.with_suffix(".qs").write_text("\n".join(qs) + "\n", encoding="utf-8")
    if rep:
        Path(f"{base}_repair.qs").write_text("\n".join(rep) + "\n", encoding="utf-8")

    by = {k: [e for e in ents if e["decision"] == k] for k in ("high", "medium", "no")}
    md = [
        f"# CbDD → Wikidata matches: {d['type']}, {datetime.date.today().isoformat()}",
        "",
        f"Input: {d['input']}.",
        f"Batch: `{base.name}.qs`, {len(qs)} commands. High: {len(by['high'])}, "
        f"medium: {len(by['medium'])}, no match: {len(by['no'])}."
        + (f" Repairs: `{base.name}_repair.qs`, {len(rep)} commands." if rep else ""),
        "",
    ]
    if d.get("method"):
        md += [d["method"], ""]

    def link(e):
        return f"https://www.deckenmalerei.eu/{e['id']}"

    if by["high"]:
        md += ["## Matched (high)", ""]
        for e in by["high"]:
            md += [
                f"### {names.get(e['id'], e['id']).strip()} → {e.get('label', e['qid'])} ({e['qid']})",
                "",
                f"CbDD: {link(e)} · Wikidata: https://www.wikidata.org/wiki/{e['qid']}",
                "",
                e["evidence"],
                "",
            ]
            if e.get("rejected"):
                md += [f"Rejected candidates: {e['rejected']}", ""]
    if by["medium"]:
        md += ["## Uncertain (medium), not in the batch", ""]
        for e in by["medium"]:
            cand = (
                f" · candidate: https://www.wikidata.org/wiki/{e['qid']}"
                if e.get("qid")
                else ""
            )
            md += [
                f"### {names.get(e['id'], e['id']).strip()}",
                "",
                f"CbDD: {link(e)}{cand}",
                "",
            ]
            md += [e["evidence"], ""]
    if by["no"]:
        md += ["## No match", ""]
        md += [
            f"- {names.get(e['id'], e['id']).strip()} ({e['id']}): {e['evidence']}"
            for e in by["no"]
        ]
        md += [""]
    if rep:
        md += [f"## Repairs (`{base.name}_repair.qs`)", ""]
        for n, (r, line) in enumerate(zip(repairs, rep, strict=True), 1):
            md += [f"{n}. `{line.replace(chr(9), ' ⇥ ')}` — {r['why']}"]
        md += [""]
    if d.get("cbdd_corrections"):
        md += ["## CbDD corrections (not fixable via QuickStatements)", ""]
        md += [f"- {c}" for c in d["cbdd_corrections"]] + [""]
    if d.get("notes"):
        md += ["## Notes", ""] + [f"- {n}" for n in d["notes"]] + [""]
    base.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")

    print(f"{base}.qs: {len(qs)} lines")
    if rep:
        print(f"{base}_repair.qs: {len(rep)} lines")
    print(
        f"{base}.md: high {len(by['high'])}, medium {len(by['medium'])}, no {len(by['no'])}"
    )


if __name__ == "__main__":
    main()
