"""
statement_check.py

Compares statements derived from deckenmalerei.eu data (the existing_*.csv files,
i.e. entities already linked to Wikidata) against the statements already present
in Wikidata (cached SPARQL results in sources/), and writes the missing ones in
QuickStatements CSV format.

The comparison logic in this module is generic. Everything specific to an entity
type — which columns map to which properties, which SPARQL result file to read,
where to write output — lives in src.config.STATEMENT_CHECKS. The main() function
runs one check per configured entity type (people, buildings, paintings, rooms,
room sequences).
"""

import csv
import json
from pathlib import Path

from src.config import STATEMENT_CHECKS

# Property groupings that drive value formatting / comparison. These are keyed by
# Wikidata property ID so they apply uniformly across all entity types.
DESCRIPTION_PIDS = {"Den", "Dde"}
DATE_PIDS = {"P571"}
DIMENSION_PIDS = {"P2049", "P2043", "P2048", "P2386"}  # width/length/height/diameter
COORDINATE_PIDS = {"P625"}
STRING_PIDS = {"P2092", "P1256", "P281"}  # quoted plain strings (e.g. postal code)


def extract_qid(url: str) -> str:
    """Extract QID from a Wikidata entity URL."""
    return url.rsplit("/", 1)[-1] if url else ""


# --------------------------------------------------------------------------- #
# Generic value formatting / comparison
# --------------------------------------------------------------------------- #


def format_qs_value(pid: str, val: str) -> str:
    """
    Format a value for QuickStatements CSV.

    - Q-items stay as-is
    - Dates get formatted with precision
    - Quantities get formatted with the centimetre unit
    - Coordinates get the @LAT/LNG form
    - Configured string properties get quoted
    """
    if pid in DESCRIPTION_PIDS:
        # Descriptions are plain strings
        return val
    if val.startswith("Q"):
        return val
    if pid in COORDINATE_PIDS:
        # Stored internally as "lat/lng"; QuickStatements wants @lat/lng
        return f"@{val}"
    # Dates: 4-digit year
    if pid in DATE_PIDS and len(val) == 4 and val.isdigit():
        return f"+{val}-00-00T00:00:00Z/9"
    if pid in DATE_PIDS and len(val) == 10:
        # Full date like 2024-01-15
        return f"+{val}T00:00:00Z/11"
    # Numeric values (dimensions)
    if pid in DIMENSION_PIDS:
        try:
            float(val)
            return f"{val}U174728"  # U174728 = centimetre
        except ValueError:
            return val
    # Plain string (normdata/bildindex, iconclass, postal code)
    if pid in STRING_PIDS:
        return f'"{val}"'
    return val


def normalize_coordinate(val: str) -> str:
    """
    Normalize a coordinate to a comparable "lat,lng" string rounded to 4 decimals.

    Accepts the WKT form Wikidata returns ("Point(lng lat)") and the internal
    "lat/lng" form built from the CSV. Returns the input unchanged if it cannot
    be parsed.
    """
    val = val.strip()
    try:
        if val.startswith("Point(") and val.endswith(")"):
            lng, lat = val[len("Point(") : -1].split()
        elif "/" in val:
            lat, lng = val.split("/", 1)
        else:
            return val
        return f"{round(float(lat), 4)},{round(float(lng), 4)}"
    except ValueError:
        return val


def normalize_for_comparison(pid: str, val: str) -> str:
    """Normalize a value for comparison between potential and existing."""
    # Strip quotes
    val = val.strip('"')
    if pid in COORDINATE_PIDS:
        return normalize_coordinate(val)
    # Normalize dates to just year for comparison
    if pid in DATE_PIDS:
        if val.startswith("+"):
            val = val[1:]
        val = val.split("-")[0].split("T")[0]
    return val


# --------------------------------------------------------------------------- #
# Generic comparison engine
# --------------------------------------------------------------------------- #


def unify_wikidata_results(
    data: list[dict], key_to_pid: dict[str, str]
) -> dict[str, dict]:
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

        unified.setdefault(item, {})

        for key, pid in key_to_pid.items():
            val = row.get(key, "")
            if not val:
                continue
            # Normalize entity URLs to QIDs (coordinates keep their Point(...) form)
            if val.startswith("http"):
                val = extract_qid(val)
            # Strip datetime suffixes for inception dates
            if pid in DATE_PIDS and "T" in val:
                val = val.split("T")[0]
            unified[item].setdefault(pid, set()).add(val)

        # Also store labels (not statements, but useful context)
        for label_key in ("itemLabel_de", "itemLabel_en"):
            val = row.get(label_key, "")
            if val:
                unified[item].setdefault(label_key, set()).add(val)

    return unified


def build_potential_statements(
    csv_path: str, check: dict
) -> dict[str, dict[str, set]]:
    """
    Read an existing_*.csv and build the statements it implies, per QID.

    Driven by the check's ``column_to_pid`` (single-column statements, with
    optional ``value_maps``) and ``coordinate`` (two columns combined into one
    P625 value). Returns {qid: {pid: {value, ...}}}.
    """
    column_to_pid: dict[str, str] = check["column_to_pid"]
    value_maps: dict[str, dict[str, str]] = check.get("value_maps", {})
    coordinate: dict[str, str] | None = check.get("coordinate")

    potential: dict[str, dict[str, set]] = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row.get("wikidata_qid", "").strip()
            if not qid:
                continue

            potential.setdefault(qid, {})

            for col, pid in column_to_pid.items():
                raw = row.get(col, "").strip()
                if not raw:
                    continue

                # Split multi-valued cells (semicolon-separated)
                values = [v.strip() for v in raw.split(";") if v.strip()]
                value_map = value_maps.get(pid)

                for val in values:
                    if value_map is not None:
                        val = value_map.get(val, "")
                        if not val:
                            continue  # skip values we cannot map to Wikidata
                    potential[qid].setdefault(pid, set()).add(val)

            if coordinate:
                lat = row.get(coordinate["lat"], "").strip()
                lng = row.get(coordinate["lng"], "").strip()
                if lat and lng:
                    potential[qid].setdefault(coordinate["pid"], set()).add(
                        f"{lat}/{lng}"
                    )

    return potential


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


# --------------------------------------------------------------------------- #
# Per-entity-type runner
# --------------------------------------------------------------------------- #


def run_statement_check(label: str, check: dict) -> dict | None:
    """
    Run the statement check for one entity type.

    Returns a stats dict, or None if required input files are missing (in which
    case a note is printed and the check is skipped).
    """
    existing_csv = check["existing_csv"]
    wd_query_json = check["wd_query_json"]
    output_csv = check["output_csv"]

    for f in (existing_csv, wd_query_json):
        if not Path(f).exists():
            print(f"  [{label}] skipped — missing input file: {f}")
            return None

    with open(wd_query_json, encoding="utf-8") as f:
        wd_raw = json.load(f)
    existing = unify_wikidata_results(wd_raw, check["wd_query_key_to_pid"])

    potential = build_potential_statements(existing_csv, check)
    missing = compute_missing(potential, existing)

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    count = write_quickstatements_csv(missing, output_csv)

    total_existing = sum(
        len(vals)
        for props in existing.values()
        for pid, vals in props.items()
        if not pid.startswith("itemLabel")
    )
    total_potential = sum(
        len(vals) for props in potential.values() for vals in props.values()
    )

    # Breakdown by property
    by_property_missing: dict[str, int] = {}
    for props in missing.values():
        for pid, vals in props.items():
            by_property_missing[pid] = by_property_missing.get(pid, 0) + len(vals)
    by_property_potential: dict[str, int] = {}
    for props in potential.values():
        for pid, vals in props.items():
            by_property_potential[pid] = by_property_potential.get(pid, 0) + len(vals)

    print(f"  [{label}] items in Wikidata: {len(existing)}")
    print(f"    existing statements:  {total_existing}")
    print(f"    potential statements: {total_potential}")
    print(f"    missing statements:   {count}")
    all_pids = sorted(set(by_property_missing) | set(by_property_potential))
    if all_pids:
        print(f"    {'property':8s}  {'missing':>8s} / {'potential':>9s}  {'%':>6s}")
        for pid in all_pids:
            m = by_property_missing.get(pid, 0)
            p = by_property_potential.get(pid, 0)
            pct = f"{(m / p * 100):.1f}%" if p > 0 else "-"
            print(f"    {pid:8s}  {m:>8d} / {p:>9d}  {pct:>6s}")
    print(f"    -> {output_csv}")

    return {
        "label": label,
        "potential": total_potential,
        "existing": total_existing,
        "missing": count,
    }


def main() -> None:
    """Run the statement check for every configured entity type."""
    results: list[dict] = []
    for label, check in STATEMENT_CHECKS.items():
        print(f"\nChecking statements for {label}...")
        stats = run_statement_check(label, check)
        if stats:
            results.append(stats)

    if not results:
        print("\nNo statement checks ran (no Wikidata query files found).")
        return

    total_potential = sum(r["potential"] for r in results)
    total_existing = sum(r["existing"] for r in results)
    total_missing = sum(r["missing"] for r in results)

    print(f"\n{'=' * 50}")
    print("Statement check summary:")
    print(f"  {'type':16s}  {'missing':>8s} / {'potential':>9s}")
    for r in results:
        print(f"  {r['label']:16s}  {r['missing']:>8d} / {r['potential']:>9d}")
    print(f"  {'total':16s}  {total_missing:>8d} / {total_potential:>9d}")
    if total_potential > 0:
        coverage = ((total_potential - total_missing) / total_potential) * 100
        print(f"  Coverage (already in Wikidata): {coverage:.1f}%")


if __name__ == "__main__":
    main()
