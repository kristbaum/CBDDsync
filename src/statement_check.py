"""
statement_check.py

Compares statements from existing_paintings.csv (derived from deckenmalerei.eu)
against statements already in Wikidata (from query_painting_statements.json).

Outputs missing_painting_statements.csv in QuickStatements CSV format.
"""

import csv
import json
from pathlib import Path

from src.config import PAINTING_COLUMN_TO_PID, WD_QUERY_KEY_TO_PID


def extract_qid(url: str) -> str:
    """Extract QID from a Wikidata entity URL."""
    return url.rsplit("/", 1)[-1] if url else ""


def unify_wikidata_results(data: list[dict]) -> dict[str, dict]:
    """
    Unify duplicate rows from Wikidata query results by item.

    SPARQL results duplicate rows when multiple values exist for a property.
    This merges them into sets per property.
    """
    unified: dict[str, dict[str, set]] = {}

    for row in data:
        item = extract_qid(row.get("item", ""))
        if not item:
            continue

        if item not in unified:
            unified[item] = {}

        for key, pid in WD_QUERY_KEY_TO_PID.items():
            val = row.get(key, "")
            if not val:
                continue
            # Normalize entity URLs to QIDs
            if val.startswith("http"):
                val = extract_qid(val)
            # Strip datetime suffixes for inception dates
            if key == "inception" and "T" in val:
                val = val.split("T")[0]
            unified[item].setdefault(pid, set()).add(val)

        # Also store labels (not statements, but useful context)
        for label_key in ("itemLabel_de", "itemLabel_en"):
            val = row.get(label_key, "")
            if val:
                unified[item].setdefault(label_key, set()).add(val)

    return unified


def format_qs_value(pid: str, val: str) -> str:
    """
    Format a value for QuickStatements CSV.

    - Q-items stay as-is
    - Dates get formatted with precision
    - Quantities get formatted
    - Strings get quoted
    """
    if pid in ("Den", "Dde"):
        # Descriptions are plain strings
        return val
    if val.startswith("Q"):
        return val
    # Dates: 4-digit year
    if pid == "P571" and len(val) == 4 and val.isdigit():
        return f"+{val}-00-00T00:00:00Z/9"
    if pid == "P571" and len(val) == 10:
        # Full date like 2024-01-15
        return f"+{val}T00:00:00Z/11"
    # Numeric values (dimensions)
    if pid in ("P2049", "P2043", "P2048", "P2386"):
        try:
            float(val)
            return f"{val}U174728"  # U174728 = centimetre
        except ValueError:
            return val
    # Plain string (normdata/bildindex, iconclass)
    if pid in ("P2092", "P1256"):
        return f'"{val}"'
    return val


def build_potential_statements(csv_path: str) -> dict[str, dict[str, set]]:
    """
    Read existing_paintings.csv and build potential statements per QID.

    Returns {qid: {pid: {value, ...}}}
    """
    potential: dict[str, dict[str, set]] = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row.get("wikidata_qid", "").strip()
            if not qid:
                continue

            potential.setdefault(qid, {})

            for col, pid in PAINTING_COLUMN_TO_PID.items():
                raw = row.get(col, "").strip()
                if not raw:
                    continue

                # Split multi-valued cells (semicolon-separated)
                values = [v.strip() for v in raw.split(";") if v.strip()]

                for val in values:
                    potential[qid].setdefault(pid, set()).add(val)

    return potential


def normalize_for_comparison(pid: str, val: str) -> str:
    """Normalize a value for comparison between potential and existing."""
    # Strip quotes
    val = val.strip('"')
    # Normalize dates to just year for comparison
    if pid == "P571":
        if val.startswith("+"):
            val = val[1:]
        val = val.split("-")[0].split("T")[0]
    return val


def compute_missing(
    potential: dict[str, dict[str, set]],
    existing: dict[str, dict[str, set]],
) -> dict[str, dict[str, list]]:
    """
    Compare potential statements against existing ones.
    Returns only the missing statements.
    """
    missing: dict[str, dict[str, list]] = {}

    for qid, props in potential.items():
        for pid, values in props.items():
            existing_values = existing.get(qid, {}).get(pid, set())
            # Normalize existing values for comparison
            existing_normalized = {
                normalize_for_comparison(pid, v) for v in existing_values
            }

            for val in values:
                val_normalized = normalize_for_comparison(pid, val)
                if val_normalized not in existing_normalized:
                    missing.setdefault(qid, {}).setdefault(pid, []).append(val)

    return missing


def write_quickstatements_csv(
    missing: dict[str, dict[str, list]],
    output_path: str,
) -> int:
    """
    Write missing statements as QuickStatements CSV.

    Uses proper QS format: qid as first column, property IDs as column headers.
    One row per statement (only the relevant property column is filled).

    Returns total number of statements written.
    """
    # Collect all property IDs used
    all_pids: set[str] = set()
    for props in missing.values():
        all_pids.update(props.keys())
    sorted_pids = sorted(all_pids)

    total = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["qid"] + sorted_pids)

        for qid in sorted(missing.keys()):
            props = missing[qid]
            for pid in sorted_pids:
                for val in props.get(pid, []):
                    row = [""] * (len(sorted_pids) + 1)
                    row[0] = qid
                    row[sorted_pids.index(pid) + 1] = format_qs_value(pid, val)
                    w.writerow(row)
                    total += 1

    return total


def main() -> None:
    """Run the painting statement check."""
    # Validate required files
    required = [
        "sources/query_painting_statements.json",
        "existing/existing_paintings.csv",
    ]
    for f in required:
        if not Path(f).exists():
            print(f"ERROR: Missing required file: {f}")
            return

    # Step 1: Load and unify Wikidata query results
    print("Step 1: Loading and unifying Wikidata statements...")
    with open("sources/query_painting_statements.json", encoding="utf-8") as f:
        wd_raw = json.load(f)
    print(f"  Raw records from Wikidata: {len(wd_raw)}")

    existing = unify_wikidata_results(wd_raw)
    print(f"  Unique items in Wikidata: {len(existing)}")

    # Count total existing statements
    total_existing = sum(
        len(vals)
        for props in existing.values()
        for pid, vals in props.items()
        if not pid.startswith("item")
    )
    print(f"  Total existing statements: {total_existing}")

    # Step 2: Build potential statements from CSV
    print("\nStep 2: Building potential statements from existing_paintings.csv...")
    potential = build_potential_statements("existing/existing_paintings.csv")
    print(f"  Items with potential statements: {len(potential)}")

    total_potential = sum(
        len(vals) for props in potential.values() for vals in props.values()
    )
    print(f"  Total potential statements: {total_potential}")

    # Step 3 & 4: Compute missing and write output
    print("\nStep 3: Computing missing statements...")
    missing = compute_missing(potential, existing)

    items_with_missing = len(missing)
    total_missing = sum(
        len(vals) for props in missing.values() for vals in props.values()
    )
    print(f"  Items with missing statements: {items_with_missing}")
    print(f"  Total missing statements: {total_missing}")

    # Breakdown by property
    print("\n  Missing statements by property:")
    by_property: dict[str, int] = {}
    for props in missing.values():
        for pid, vals in props.items():
            by_property[pid] = by_property.get(pid, 0) + len(vals)
    for pid in sorted(by_property.keys()):
        print(f"    {pid:8s}: {by_property[pid]}")

    # Write output
    output_path = "missing/missing_painting_statements.csv"
    Path("missing").mkdir(exist_ok=True)
    count = write_quickstatements_csv(missing, output_path)
    print(f"\nStep 4: Wrote {count} missing statements to {output_path}")

    # Summary
    print(f"\n{'='*50}")
    print("Summary:")
    print(f"  Potential statements (from deckenmalerei.eu): {total_potential}")
    print(f"  Existing statements (in Wikidata):           {total_existing}")
    print(f"  Missing statements:                          {total_missing}")
    if total_potential > 0:
        coverage = ((total_potential - total_missing) / total_potential) * 100
        print(f"  Coverage:                                    {coverage:.1f}%")


if __name__ == "__main__":
    main()
