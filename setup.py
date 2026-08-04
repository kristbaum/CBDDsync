"""
setup.py

Refreshes every input file in sources/, replacing whatever is already there:

  - entities.json, relations.json, resources.json
      Pulled from the deckenmalerei.eu dump mirrored on GitHub.
  - query.csv
      Live SPARQL query against the Wikidata Query Service: every item
      carrying a deckenmalerei.eu ID (P10626).
  - query_people_statements.json, query_building_statements.json,
    query_painting_statements.json, query_room_statements.json,
    query_room_sequence_statements.json
      Live SPARQL queries for the statements already present in Wikidata for
      each entity type, used by src/statement_check.py.

The SPARQL queries mirror the ones documented in README.md. Run this instead
of the old setup.sh, then `uv run sync.py` to regenerate the analysis.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

SOURCES_DIR = Path("sources")

DUMP_BASE_URL = (
    "https://raw.githubusercontent.com/arthist-lmu/plafond3d/main/dumps/"
    "deckenmalerei.eu/2026_04"
)
DUMP_FILES = ["entities.json", "relations.json", "resources.json"]

WDQS_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "CBDDsync/0.1 (https://github.com/kristbaum/CBDDsync)"

ENTITY_QUERY = """
SELECT ?item ?deckenmalerei_eu_ID WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
}
"""

PEOPLE_STATEMENTS_QUERY = """
SELECT DISTINCT ?item ?gender WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID;
    wdt:P31 wd:Q5.
  OPTIONAL { ?item wdt:P21 ?gender. }
}
"""

BUILDING_STATEMENTS_QUERY = """
SELECT DISTINCT ?item ?inception ?postalCode ?coordinate WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  OPTIONAL { ?item wdt:P571 ?inception. }
  OPTIONAL { ?item wdt:P281 ?postalCode. }
  OPTIONAL { ?item wdt:P625 ?coordinate. }
}
"""

# Result keys match src.config.WD_QUERY_KEY_TO_PID exactly.
PAINTING_STATEMENTS_QUERY = """
SELECT DISTINCT ?item ?itemDescription_en ?itemDescription_de ?inception
                ?iconclass ?method ?material ?painter ?commissioner
                ?width ?length ?height ?diameter ?location ?condition ?bildindex WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  OPTIONAL { ?item schema:description ?itemDescription_en. FILTER(LANG(?itemDescription_en) = "en") }
  OPTIONAL { ?item schema:description ?itemDescription_de. FILTER(LANG(?itemDescription_de) = "de") }
  OPTIONAL { ?item wdt:P571 ?inception. }
  OPTIONAL { ?item wdt:P1257 ?iconclass. }
  OPTIONAL { ?item wdt:P2079 ?method. }
  OPTIONAL { ?item wdt:P186 ?material. }
  OPTIONAL { ?item wdt:P170 ?painter. }
  OPTIONAL { ?item wdt:P88 ?commissioner. }
  OPTIONAL { ?item wdt:P2049 ?width. }
  OPTIONAL { ?item wdt:P2043 ?length. }
  OPTIONAL { ?item wdt:P2048 ?height. }
  OPTIONAL { ?item wdt:P2386 ?diameter. }
  OPTIONAL { ?item wdt:P276 ?location. }
  OPTIONAL { ?item wdt:P5816 ?condition. }
  OPTIONAL { ?item wdt:P12754 ?bildindex. }
}
"""

ROOM_STATEMENTS_QUERY = """
SELECT DISTINCT ?item ?inception WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  OPTIONAL { ?item wdt:P571 ?inception. }
}
"""

# Rooms and room sequences share the same shape of query (README.md); they
# are only distinguished by which entities happen to carry P10626 in each
# Wikidata class, so the same query is reused for both output files.
STATEMENT_QUERIES = {
    "query_people_statements.json": PEOPLE_STATEMENTS_QUERY,
    "query_building_statements.json": BUILDING_STATEMENTS_QUERY,
    "query_painting_statements.json": PAINTING_STATEMENTS_QUERY,
    "query_room_statements.json": ROOM_STATEMENTS_QUERY,
    "query_room_sequence_statements.json": ROOM_STATEMENTS_QUERY,
}


def fetch(url: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(request) as response:
        return response.read()


def download_dump_files() -> None:
    print("Downloading source data files...")
    for filename in DUMP_FILES:
        data = fetch(f"{DUMP_BASE_URL}/{filename}", accept="application/json")
        (SOURCES_DIR / filename).write_bytes(data)
        print(f"  -> sources/{filename}")


def run_sparql_query(query: str, accept: str) -> bytes:
    # Content negotiation via the Accept header is what the SPARQL protocol
    # (and WDQS) actually honors; a "format" query param is unreliable.
    url = f"{WDQS_ENDPOINT}?{urllib.parse.urlencode({'query': query})}"
    return fetch(url, accept=accept)


def simplify_bindings(raw_json: bytes) -> list[dict]:
    """Flatten SPARQL JSON results into a list of {var: value} dicts."""
    data = json.loads(raw_json)
    return [
        {var: binding["value"] for var, binding in row.items()}
        for row in data["results"]["bindings"]
    ]


def download_entity_query() -> None:
    print("Querying Wikidata for entities already linked (query.csv)...")
    csv_bytes = run_sparql_query(ENTITY_QUERY, accept="text/csv")
    (SOURCES_DIR / "query.csv").write_bytes(csv_bytes)
    print("  -> sources/query.csv")


def download_statement_queries() -> None:
    for filename, query in STATEMENT_QUERIES.items():
        print(f"Querying Wikidata for {filename}...")
        raw = run_sparql_query(query, accept="application/sparql-results+json")
        rows = simplify_bindings(raw)
        (SOURCES_DIR / filename).write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  -> sources/{filename} ({len(rows)} rows)")


def main() -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    download_dump_files()
    download_entity_query()
    download_statement_queries()
    print("\n✓ All source files replaced.")


if __name__ == "__main__":
    main()
