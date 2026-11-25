"""
statement_check.py

Compares statements derived from deckenmalerei.eu data (the existing_*.csv files,
i.e. entities already linked to Wikidata) against the statements already present
in Wikidata (cached SPARQL results in sources/), and writes the missing ones both
as QuickStatements CSV and as a QuickStatements 3.0 V1 batch (.qs). The .qs
batch carries a reference (stated in CbDD + deckenmalerei.eu ID) on every
statement.

The comparison logic in this module is generic. Everything specific to an entity
type — which columns map to which properties, which SPARQL result file to read,
where to write output — lives in src.config.STATEMENT_CHECKS. The main() function
runs one check per configured entity type (people, buildings, paintings, rooms,
room sequences).
"""

import csv
import json
import math
from pathlib import Path

from src.config import (
    CBDD_ID_PID,
    CBDD_SOURCE_QID,
    COORDINATE_TOLERANCE_M,
    STATEMENT_CHECKS,
)
from src.quickstatements import qs_line, qs_string, write_qs_file

# Property groupings that drive value formatting / comparison. These are keyed by
# Wikidata property ID so they apply uniformly across all entity types.
DESCRIPTION_PIDS = {"Den", "Dde"}
DATE_PIDS = {"P571"}
DIMENSION_PIDS = {"P2049", "P2043", "P2048", "P2386"}  # width/length/height/diameter
# CbDD dimensions are in metres (Q11573), as are the existing Wikidata values.
DIMENSION_UNIT = "U11573"
COORDINATE_PIDS = {"P625"}
EARTH_RADIUS_M = 6_371_000
# Quoted plain strings: Bildindex, Iconclass, postal code
STRING_PIDS = {"P2092", "P1256", "P1257", "P281"}
# Monolingual text properties and the language their CbDD values are in
MONOLINGUAL_PIDS = {"P6375": "de"}  # street address

# {qid: {pid: {value: [(qualifier pid, raw qualifier value), ...]}}}
Qualifiers = dict[str, dict[str, dict[str, list[tuple[str, str]]]]]


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
    - Quantities get formatted with the metre unit
    - Coordinates get the @LAT/LNG form
    - Configured string properties get quoted
    - Monolingual text properties get the lang:"text" form
    """
    if pid in DESCRIPTION_PIDS:
        # Descriptions are plain strings
        return val
    if pid in MONOLINGUAL_PIDS:
        return f"{MONOLINGUAL_PIDS[pid]}:{qs_string(val)}"
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
            return f"{val}{DIMENSION_UNIT}"
        except ValueError:
            return val
    # Plain string (normdata/bildindex, iconclass, postal code)
    if pid in STRING_PIDS:
        return qs_string(val)
    return val


def parse_coordinate(val: str) -> tuple[float, float] | None:
    """
    Parse a coordinate into (lat, lng), or None if it cannot be parsed.

    Accepts the WKT form Wikidata query services return ("Point(lng lat)" from
    WDQS, "POINT(lng lat)" from QLever) and the internal "lat/lng" form built
    from the CSV.
    """
    val = val.strip()
    try:
        if val[:6].upper() == "POINT(" and val.endswith(")"):
            lng, lat = val[6:-1].split()
        elif "/" in val:
            lat, lng = val.split("/", 1)
        else:
            return None
        return float(lat), float(lng)
    except ValueError:
        return None


def normalize_coordinate(val: str) -> str:
    """
    Normalize a coordinate to a comparable "lat,lng" string rounded to 4 decimals.

    Accepts the same forms as parse_coordinate. Returns the input unchanged if it
    cannot be parsed.
    """
    parsed = parse_coordinate(val)
    if parsed is None:
        return val.strip()
    lat, lng = parsed
    return f"{round(lat, 4)},{round(lng, 4)}"


def coordinate_distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle (haversine) distance in metres between two (lat, lng) pairs."""
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def coordinate_is_close(val: str, existing_values: set[str]) -> bool:
    """True if ``val`` lies within COORDINATE_TOLERANCE_M of any existing value."""
    point = parse_coordinate(val)
    if point is None:
        return False
    for other in existing_values:
        other_point = parse_coordinate(other)
        if (
            other_point is not None
            and coordinate_distance_m(point, other_point) <= COORDINATE_TOLERANCE_M
        ):
            return True
    return False


def normalize_for_comparison(pid: str, val: str) -> str:
    """Normalize a value for comparison between potential and existing."""
    # Strip quotes
    val = val.strip('"')
    if pid in COORDINATE_PIDS:
        return normalize_coordinate(val)
    # Compare dimensions numerically ("3" from CbDD equals "3.0" from Wikidata)
    if pid in DIMENSION_PIDS:
        try:
            return repr(float(val))
        except ValueError:
            return val
    # Normalize dates to just year for comparison
    if pid in DATE_PIDS:
        val = val.removeprefix("+")
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


def build_potential_statements(csv_path: str, check: dict) -> dict[str, dict[str, set]]:
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


def load_qualifiers(csv_path: str, check: dict) -> Qualifiers:
    """
    Read the qualifiers configured in the check's ``qualifiers`` from an
    existing_*.csv.

    For every statement value a row yields for a qualified pid, the row's
    qualifier columns (when non-empty) are attached to that value.
    """
    config: dict[str, dict[str, str]] = check.get("qualifiers", {})
    if not config:
        return {}
    column_to_pid: dict[str, str] = check["column_to_pid"]
    pid_to_column = {pid: col for col, pid in column_to_pid.items()}

    qualifiers: Qualifiers = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            qid = row.get("wikidata_qid", "").strip()
            if not qid:
                continue
            for pid, qualifier_columns in config.items():
                raw = row.get(pid_to_column.get(pid, ""), "") or ""
                values = [v.strip() for v in raw.split(";") if v.strip()]
                pairs = [
                    (q_pid, q_val)
                    for q_pid, q_col in qualifier_columns.items()
                    if (q_val := (row.get(q_col, "") or "").strip())
                ]
                if not pairs:
                    continue
                for val in values:
                    qualifiers.setdefault(qid, {}).setdefault(pid, {}).setdefault(
                        val, pairs
                    )
    return qualifiers


def load_cbdd_ids(csv_path: str) -> dict[str, str]:
    """
    Map each QID in an existing_*.csv to its deckenmalerei.eu ID.

    Used as the reference for generated statements. If several CbDD entities map
    to the same QID (see errors/duplicates.md), the first one in the file wins.
    """
    ids: dict[str, str] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            qid = row.get("wikidata_qid", "").strip()
            cbdd_id = row.get("ID", "").strip()
            if qid and cbdd_id:
                ids.setdefault(qid, cbdd_id)
    return ids


def compute_missing(
    potential: dict[str, dict[str, set]],
    existing: dict[str, dict[str, set]],
    overwrite_descriptions: bool = False,
) -> dict[str, dict[str, list]]:
    """
    Compare potential statements against existing ones.
    Returns only the missing statements.

    An item holds one description per language, so a differing CbDD
    description would replace the existing one. Unless
    ``overwrite_descriptions`` is set, descriptions are only proposed for
    items that have none in that language.
    """
    missing: dict[str, dict[str, list]] = {}

    for qid, props in potential.items():
        for pid, values in props.items():
            existing_values = existing.get(qid, {}).get(pid, set())
            if (
                pid in DESCRIPTION_PIDS
                and existing_values
                and not overwrite_descriptions
            ):
                continue
            # Normalize existing values for comparison
            existing_normalized = {
                normalize_for_comparison(pid, v) for v in existing_values
            }

            for val in values:
                val_normalized = normalize_for_comparison(pid, val)
                if val_normalized in existing_normalized:
                    continue
                if pid in COORDINATE_PIDS and coordinate_is_close(val, existing_values):
                    continue
                missing.setdefault(qid, {}).setdefault(pid, []).append(val)

    return missing


def statement_qualifiers(
    qualifiers: Qualifiers, qid: str, pid: str, val: str
) -> list[tuple[str, str]]:
    """Formatted (qualifier pid, value) pairs for one statement."""
    return [
        (q_pid, format_qs_value(q_pid, q_val))
        for q_pid, q_val in qualifiers.get(qid, {}).get(pid, {}).get(val, [])
    ]


def write_quickstatements_csv(
    missing: dict[str, dict[str, list]],
    output_path: str,
    qualifiers: Qualifiers | None = None,
) -> int:
    """
    Write missing statements as QuickStatements CSV.

    Uses proper QS format: qid as first column, property IDs as column headers,
    each followed by its qualifier columns (``qal<number>``). One row per
    statement (only the relevant property and qualifier columns are filled).

    Returns total number of statements written.
    """
    qualifiers = qualifiers or {}
    # Collect all property IDs used, and the qualifier pids used per property
    all_pids: set[str] = set()
    qualifier_pids: dict[str, set[str]] = {}
    for qid, props in missing.items():
        all_pids.update(props.keys())
        for pid, vals in props.items():
            for val in vals:
                for q_pid, _ in statement_qualifiers(qualifiers, qid, pid, val):
                    qualifier_pids.setdefault(pid, set()).add(q_pid)

    header = ["qid"]
    column_index: dict[tuple[str, str], int] = {}
    for pid in sorted(all_pids):
        column_index[(pid, "")] = len(header)
        header.append(pid)
        for q_pid in sorted(qualifier_pids.get(pid, ())):
            column_index[(pid, q_pid)] = len(header)
            header.append("qal" + q_pid.removeprefix("P"))

    total = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)

        for qid in sorted(missing.keys()):
            props = missing[qid]
            for pid in sorted(all_pids):
                for val in props.get(pid, []):
                    row = [""] * len(header)
                    row[0] = qid
                    row[column_index[(pid, "")]] = format_qs_value(pid, val)
                    for q_pid, q_val in statement_qualifiers(qualifiers, qid, pid, val):
                        row[column_index[(pid, q_pid)]] = q_val
                    w.writerow(row)
                    total += 1

    return total


def write_quickstatements_v1(
    missing: dict[str, dict[str, list]],
    output_path: str,
    cbdd_ids: dict[str, str],
    qualifiers: Qualifiers | None = None,
) -> int:
    """
    Write missing statements as a QuickStatements 3.0 batch (V1 commands).

    One command per statement, items and properties in sorted order, with the
    statement's configured qualifiers (see ``load_qualifiers``). Statements
    get the reference ``S248 <CbDD>  S10626 "<deckenmalerei.eu ID>"`` when the
    item's CbDD ID is known; descriptions take no reference. Lines carry no
    "+" prefix, so values already present are merged rather than duplicated.

    Returns total number of commands written.
    """

    qualifiers = qualifiers or {}

    def lines():
        for qid in sorted(missing):
            cbdd_id = cbdd_ids.get(qid)
            refs = (
                [("P248", CBDD_SOURCE_QID), (CBDD_ID_PID, qs_string(cbdd_id))]
                if cbdd_id
                else []
            )
            for pid in sorted(missing[qid]):
                for val in missing[qid][pid]:
                    if pid in DESCRIPTION_PIDS:
                        yield qs_line(qid, pid, qs_string(val))
                    else:
                        yield qs_line(
                            qid,
                            pid,
                            format_qs_value(pid, val),
                            qualifiers=statement_qualifiers(qualifiers, qid, pid, val),
                            references=refs,
                        )

    return write_qs_file(lines(), output_path)


# --------------------------------------------------------------------------- #
# Per-entity-type runner
# --------------------------------------------------------------------------- #


def run_statement_check(
    label: str, check: dict, overwrite_descriptions: bool = False
) -> dict | None:
    """
    Run the statement check for one entity type.

    Returns a stats dict, or None if required input files are missing (in which
    case a note is printed and the check is skipped). See ``compute_missing``
    for ``overwrite_descriptions``.
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
    missing = compute_missing(potential, existing, overwrite_descriptions)

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    qualifiers = load_qualifiers(existing_csv, check)
    count = write_quickstatements_csv(missing, output_csv, qualifiers)
    output_qs = str(Path(output_csv).with_suffix(".qs"))
    write_quickstatements_v1(
        missing, output_qs, load_cbdd_ids(existing_csv), qualifiers
    )

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
    print(f"    -> {output_qs}")

    return {
        "label": label,
        "potential": total_potential,
        "existing": total_existing,
        "missing": count,
    }


def main(overwrite_descriptions: bool = False) -> None:
    """Run the statement check for every configured entity type."""
    results: list[dict] = []
    for label, check in STATEMENT_CHECKS.items():
        print(f"\nChecking statements for {label}...")
        stats = run_statement_check(label, check, overwrite_descriptions)
        if stats:
            results.append(stats)

    if not results:
        print("\nNo statement checks ran (no Wikidata query files found).")
        return

    total_potential = sum(r["potential"] for r in results)
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
    import sys

    main(overwrite_descriptions="--overwrite-descriptions" in sys.argv[1:])
