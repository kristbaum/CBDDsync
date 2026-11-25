"""
cbdd_preflight.py

Preflight hook of the CbDD adapter (adapter.toml), run by
`wikibase-ingest preflight --adapter agentic-reconcile --pipeline <type>` after
the generic checks. It checks what only the CbDD dump knows:

  CbDD duplicates  another CbDD record of the same type has the matched
                   entity's GND ("Bys" and "Byss, Johann Rudolf"): both would
                   want the same item. Fix it in CbDD, or name the other UUID in
                   <run>/notes.json "cbdd_corrections" if both may link to it.

Exit 1 with one line per problem, 0 if there is none. Run from the
repository root:

    uv run python agentic-reconcile/scripts/cbdd_preflight.py <run>/ingest.json
"""

import json
import sys
from pathlib import Path

STYPE = {"person": "ACTOR_PERSON", "building": "OBJECT_BUILDING"}


def matched(ingest: dict, state: dict) -> dict[str, str]:
    out = {}
    for eid, e in ingest["source_entities"].items():
        st = state.get("source_entities", {}).get(eid, {})
        status = st.get("status") or e.get("status")
        qid = state.get("ids", {}).get(eid) or st.get("qid") or e.get("qid")
        if status == "match" and qid:
            out[eid] = qid
    return out


def duplicates(ingest: dict, state: dict, dump: list[dict], noted: str) -> list[str]:
    same_gnd: dict[tuple[str, str], list[str]] = {}
    for x in dump:
        g = (
            isinstance(x, dict)
            and str((x.get("normdata") or {}).get("gnd") or "").strip()
        )
        if g:
            same_gnd.setdefault((x.get("sType", ""), g), []).append(
                f"{x['ID']} ({x.get('appellation', '')})"
            )
    problems = []
    for eid, q in matched(ingest, state).items():
        e = ingest["source_entities"][eid]
        g = next(
            (
                f["value"]["value"]
                for f in e.get("attributes", [])
                if f.get("property") == "P227"
            ),
            None,
        )
        uuid = eid.removeprefix("_:cbdd:")
        others = [
            o
            for o in same_gnd.get((STYPE.get(e.get("kind", ""), ""), g or ""), [])
            if not o.startswith(uuid) and o[:36] not in noted
        ]
        if g and others:
            problems.append(
                f"{eid} → {q}: CbDD has another record with GND {g}: {'; '.join(others)}. A CbDD duplicate: "
                "`decide <id>=reconcile` and add it to cbdd_corrections, or name the other UUID in "
                "cbdd_corrections if both may link to the item"
            )
    return problems


def main() -> None:
    path = Path(sys.argv[1])
    ingest = json.loads(path.read_text(encoding="utf-8"))
    state_path = path.with_name(path.stem + ".state.json")
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {}
    )
    notes_path = path.parent / "notes.json"
    notes = (
        json.loads(notes_path.read_text(encoding="utf-8"))
        if notes_path.exists()
        else {}
    )
    dump = json.loads(Path("sources/entities.json").read_text(encoding="utf-8"))
    problems = duplicates(
        ingest, state, dump, " ".join(notes.get("cbdd_corrections", []))
    )
    for line in problems:
        print(f"ERROR {line}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
