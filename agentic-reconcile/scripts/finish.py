"""
finish.py

End a CbDD reconcile session: run wikibase-ingest's preflight with this
adapter, write the batches, and write the CbDD evidence report.

    uv run python agentic-reconcile/scripts/finish.py <run>/ingest.json [--no-next]

1. `wikibase-ingest preflight --adapter agentic-reconcile --pipeline <type>
   --write`: the generic live checks (missing or redirected items, an item
   matched twice, an item already carrying another CbDD ID, one GND onto
   several items; statements already there become skips) and the CbDD hook
   (scripts/cbdd_preflight.py: duplicate records in CbDD). Any error stops
   here; nothing is written.
2. `<run>/notes.json` (optional, written by the agent):

       {"uncertain": {"<CbDD UUID>": "what would settle it"},
        "removals": [{"line": "-Q1\\tP10626\\t\\"cbdd10059\\"", "why": "…"}],
        "cbdd_corrections": ["…"], "notes": ["…"]}

   Removals are statements to delete on Wikidata (an ingest file only adds);
   they go to `<run>/removals.qs` when they still apply.
3. `wikibase-ingest next`: batches/direct_NNN.qs (the P10626 links),
   batches/curator_NNN.qs (GND/Bildindex, and CREATE blocks of new items
   with --create) plus review sheets.
4. `<run>/report.md`: every entity with its evidence, repairs, CbDD
   corrections and notes.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADAPTER = HERE.parent
WIKIBASE_INGEST = HERE / "wikibase-ingest"
UA = "CBDDsync-agentic-reconcile/0.4 (https://github.com/kristbaum/CBDDsync)"
REMOVAL = re.compile(r"^-Q\d+\tP\d+\t\S.*$")
MARK = {"+": "✓", "-": "✗", "0": "~"}
PIPELINE = {"person": "people", "building": "buildings"}


def wikibase_ingest(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(WIKIBASE_INGEST), *args], capture_output=True, text=True, check=False
    )


def live_values(qid: str, prop: str) -> list[str]:
    """Values of prop on the item as V1 text (strings quoted)."""
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"}
    )
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60
    ) as r:
        item = json.load(r).get("entities", {}).get(qid, {})
    out = []
    for c in item.get("claims", {}).get(prop, []):
        v = c["mainsnak"].get("datavalue", {}).get("value")
        if isinstance(v, dict):
            v = v.get("id") or v.get("text")
        if v is not None:
            out.append(v if re.fullmatch(r"Q\d+", str(v)) else f'"{v}"')
    return out


class Run:
    def __init__(self, path: Path):
        self.path = path
        self.dir = path.parent
        self.ingest = json.loads(path.read_text(encoding="utf-8"))
        state = path.with_name(path.stem + ".state.json")
        self.state = (
            json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
        )
        notes = self.dir / "notes.json"
        self.notes = (
            json.loads(notes.read_text(encoding="utf-8")) if notes.exists() else {}
        )

    def entity(self, eid: str) -> dict:
        merged = dict(self.ingest["source_entities"][eid])
        merged.update(
            {
                k: v
                for k, v in self.state.get("source_entities", {}).get(eid, {}).items()
                if v is not None
            }
        )
        return merged

    def qid(self, eid: str) -> str | None:
        e = self.entity(eid)
        if eid in self.state.get("ids", {}):
            return self.state["ids"][eid]
        return e.get("qid") if e.get("status") == "match" else None

    def claim_status(self, cid: str) -> str:
        return self.state.get("claims", {}).get(cid, {}).get("status", "new")

    def pipeline(self) -> str:
        kinds = {e.get("kind") for e in self.ingest["source_entities"].values()}
        if len(kinds) != 1 or next(iter(kinds)) not in PIPELINE:
            sys.exit(f"cannot tell the adapter pipeline from the entity kinds {kinds}")
        return PIPELINE[next(iter(kinds))]


def removals_that_apply(run: Run) -> list[dict]:
    kept = []
    for r in run.notes.get("removals", []):
        line = r.get("line", "")
        if not REMOVAL.match(line):
            sys.exit(f"NOT FINISHED: removal is not a V1 '-' line: {line!r}")
        subject, prop, value = line[1:].split("\t")[:3]
        if value in live_values(subject, prop):
            kept.append(r)
        else:
            print(f"note: removal no longer applies, left out: {line!r}")
    return kept


def evidence_rows(c: dict) -> list[str]:
    rows = []
    for x in c.get("evidence") or []:
        if x.get("status") == "failed":
            continue
        who = "" if x.get("status") == "verified" else " (asserted)"
        prop = f" {x['property']}" if x.get("property") else ""
        rows.append(
            f"| {x.get('type')}{prop} | {x.get('summary', '')}{who} | {MARK.get(x.get('polarity', '+'), '')} |"
        )
    return rows


def candidate_line(c: dict) -> str:
    ev = "; ".join(
        f"{MARK.get(x.get('polarity', '+'), '')} {x.get('summary', '')}"
        for x in c.get("evidence") or []
        if x.get("status") == "verified"
    )
    hidden = f" — left out: {c['hidden']}" if c.get("hidden") else ""
    return f"- {c['id']} {c.get('name', '')} ({c.get('description', '')}), score {c.get('score', '–')}: {ev}{hidden}"


def shown_value(v: object) -> str:
    if isinstance(v, dict):
        if v.get("type") == "coordinate":
            return f"{v['lat']:.5f}/{v['lon']:.5f}"
        return str(v.get("value") or v.get("time", "")[1:5] or v.get("id") or v)
    return str(v)


def report(run: Run, batches: list[Path], removals: list[dict]) -> str:
    ents = run.ingest["source_entities"]
    groups: dict[str, list[str]] = {
        "match": [],
        "create": [],
        "reconcile": [],
        "drop": [],
    }
    for eid in ents:
        groups[run.entity(eid)["status"]].append(eid)
    uncertain = run.notes.get("uncertain", {})
    md = [
        f"# {run.ingest['project']}",
        "",
        (
            f"Ingest file: `{run.path.name}` ({len(ents)} entities). Matched: {len(groups['match'])}, "
            f"new items: {len(groups['create'])}, uncertain: {len(groups['reconcile'])}, "
            f"no match: {len(groups['drop'])}."
        ),
        "",
    ]
    if batches or removals:
        md += [
            "Batches (QuickStatements 3, V1 commands; upload, then `wikibase-ingest resolve` the report):",
            "",
        ]
        md += [f"- `{b.relative_to(run.dir)}`" for b in batches]
        if removals:
            md += [f"- `removals.qs` ({len(removals)} removals, see Repairs)"]
        md += [""]

    def head(eid: str) -> str:
        e = ents[eid]
        return f"CbDD: {e.get('url')} · {e['descriptions'].get('de', '')}"

    if groups["match"]:
        md += ["## Matched", ""]
        for eid in groups["match"]:
            e, q = run.entity(eid), run.qid(eid)
            cand = next(
                (c for c in ents[eid].get("candidates") or [] if c["id"] == q), {}
            )
            linked = re.search(r"\((.*)\) carries P10626", e.get("route_reason", ""))
            name = cand.get("name") or (linked.group(1) if linked else q)
            md += [f"### {e['labels']['de']} → {name} ({q})", ""]
            md += [head(eid) + f" · Wikidata: https://www.wikidata.org/wiki/{q}", ""]
            md += [
                f"Decision: {e.get('decision_reason') or e.get('route_reason') or ''}",
                "",
            ]
            rows = evidence_rows(cand)
            if rows:
                md += ["| Evidence | Result | |", "|---|---|---|", *rows, ""]
            others = [c for c in ents[eid].get("candidates") or [] if c["id"] != q]
            if others:
                md += [
                    "Other candidates: "
                    + "; ".join(
                        f"{c['id']} ({c.get('hidden') or 'not chosen'})"
                        for c in others[:6]
                    ),
                    "",
                ]
    if groups["create"]:
        md += ["## New items (CREATE blocks in the curator batch)", ""]
        for eid in groups["create"]:
            e = run.entity(eid)
            stmts = [
                f"{c['property']} {shown_value(c['value'])}"
                for c in run.ingest["claims"]
                if c["subject"] == eid
                and run.claim_status(c["id"]) not in ("skip", "rejected")
            ]
            made = f" → created as {run.qid(eid)}" if run.qid(eid) else ""
            md += [
                (
                    f"- {e['labels']['de']} – {e['descriptions'].get('de', '')}{made} ({ents[eid].get('url')}): "
                    f"{'; '.join(stmts)}. {e.get('decision_reason') or e.get('route_reason', '')}"
                )
            ]
        md += [""]
    if groups["reconcile"]:
        md += ["## Uncertain, not in the batch", ""]
        for eid in groups["reconcile"]:
            e = run.entity(eid)
            md += [f"### {e['labels']['de']}", "", head(eid), ""]
            if e.get("hint"):
                md += [f"Hint: {e['hint']}", ""]
            md += [f"Route: {e.get('route')} — {e.get('route_reason', '')}", ""]
            md += [candidate_line(c) for c in (ents[eid].get("candidates") or [])[:6]]
            if uncertain.get(eid.removeprefix("_:cbdd:")):
                md += ["", f"Would settle it: {uncertain[eid.removeprefix('_:cbdd:')]}"]
            md += [""]
    if groups["drop"]:
        md += ["## No match", ""]
        for eid in groups["drop"]:
            e = run.entity(eid)
            searches = ", ".join(
                f"{s.get('method')} “{s.get('query', '')[:60]}” ({s.get('results', 0)})"
                for s in ents[eid].get("searches") or []
            )
            md += [
                (
                    f"- {e['labels']['de']} ({eid.removeprefix('_:cbdd:')}): "
                    f"{e.get('decision_reason') or e.get('route_reason', '')} Searched: {searches or '–'}."
                )
            ]
        md += [""]
    repairs = [
        c
        for c in run.ingest["claims"]
        if c["property"] in ("P227", "P2092")
        and run.entity(c["subject"]).get("status") == "match"
        and run.claim_status(c["id"]) not in ("skip", "rejected")
    ]
    if repairs or removals:
        md += ["## Repairs", ""]
        for c in repairs:
            md += [
                (
                    f'- {run.qid(c["subject"])} {c["property"]} "{c["value"]["value"]}" (curator batch) — '
                    f"{c.get('route_reason', '')}"
                )
            ]
        for r in removals:
            md += [
                f"- `{r['line'].replace(chr(9), ' ⇥ ')}` (removals.qs) — {r.get('why', '')}"
            ]
        md += [""]
    if run.notes.get("cbdd_corrections"):
        md += ["## CbDD corrections (not fixable via QuickStatements)", ""]
        md += [f"- {c}" for c in run.notes["cbdd_corrections"]] + [""]
    if run.notes.get("notes"):
        md += ["## Notes", ""] + [f"- {n}" for n in run.notes["notes"]] + [""]
    md += [
        f"_Written {datetime.date.today().isoformat()} by agentic-reconcile/scripts/finish.py._",
        "",
    ]
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("ingest", type=Path)
    ap.add_argument(
        "--no-next", action="store_true", help="only preflight and report, no batches"
    )
    args = ap.parse_args()
    run = Run(args.ingest)

    pre = wikibase_ingest(
        "preflight",
        str(args.ingest),
        "--adapter",
        str(ADAPTER),
        "--pipeline",
        run.pipeline(),
        "--write",
    )
    print(pre.stdout.strip())
    if pre.returncode != 0:
        sys.exit(
            "NOT FINISHED: fix the errors above (decide …), then run finish.py again\n"
            + pre.stderr.strip()
        )
    removals = removals_that_apply(run)
    if not args.no_next:
        nxt = wikibase_ingest("next", str(args.ingest))
        if nxt.returncode not in (0, 1):
            sys.exit(f"wikibase-ingest next failed:\n{nxt.stderr or nxt.stdout}")
        print(nxt.stdout.strip())
    run = Run(args.ingest)  # reload: preflight and next changed the state
    if removals:
        (run.dir / "removals.qs").write_text(
            "\n".join(r["line"] for r in removals) + "\n", encoding="utf-8"
        )
    batches = sorted(
        p for p in (run.dir / "batches").glob("*.qs") if not p.stem.endswith("_pending")
    )
    (run.dir / "report.md").write_text(report(run, batches, removals), encoding="utf-8")
    print(run.dir / "report.md")


if __name__ == "__main__":
    main()
