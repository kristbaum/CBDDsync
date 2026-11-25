"""
setup.py

Refreshes every input file in sources/, replacing whatever is already there:

  - entities.json, relations.json, resources.json
      Pulled from the deckenmalerei.eu dump mirrored on GitHub.
  - query.csv and query_<type>_statements.json
      Live SPARQL queries against QLever's Wikidata endpoint (qlever.dev),
      run by src/update_queries.py. To refresh only these, run
      `uv run setup.py --wikidata-only` (or `uv run python -m src.update_queries`,
      which also accepts individual query names).

Run this, then `uv run sync.py` to regenerate the analysis.
"""

import argparse
import sys

from src.update_queries import SOURCES_DIR, fetch, update_queries

DUMP_BASE_URL = (
    "https://raw.githubusercontent.com/arthist-lmu/plafond3d/main/dumps/"
    "deckenmalerei.eu/2026_04"
)
DUMP_FILES = ["entities.json", "relations.json", "resources.json"]


def download_dump_files() -> None:
    print("Downloading source data files...")
    for filename in DUMP_FILES:
        data = fetch(f"{DUMP_BASE_URL}/{filename}", accept="application/json")
        (SOURCES_DIR / filename).write_bytes(data)
        print(f"  -> sources/{filename}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Refresh the input files in sources/.")
    ap.add_argument(
        "--wikidata-only",
        action="store_true",
        help="only re-run the Wikidata queries; keep the existing CbDD dump files",
    )
    args = ap.parse_args()

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    if not args.wikidata_only:
        download_dump_files()
    if update_queries([]):
        sys.exit("Some queries failed; see above.")
    if args.wikidata_only:
        print("\n✓ Wikidata query results replaced.")
    else:
        print("\n✓ All source files replaced.")


if __name__ == "__main__":
    main()
