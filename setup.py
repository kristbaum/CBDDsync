"""
setup.py

Refreshes every input file in sources/, replacing whatever is already there:

  - entities.json, relations.json, resources.json
      Pulled from the deckenmalerei.eu dump mirrored on GitHub.
  - query.csv and query_<type>_statements.json
      Live SPARQL queries against QLever's Wikidata endpoint (qlever.dev),
      run by src/update_queries.py. To refresh only these, run
      `uv run python -m src.update_queries` instead.

Run this, then `uv run sync.py` to regenerate the analysis.
"""

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
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    download_dump_files()
    if update_queries([]):
        sys.exit("Some queries failed; see above.")
    print("\n✓ All source files replaced.")


if __name__ == "__main__":
    main()
