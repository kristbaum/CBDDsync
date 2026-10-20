"""
update_queries.py

Re-runs the Wikidata SPARQL queries on QLever (qlever.dev) and replaces the
cached results in sources/:

  - query.csv
      every item carrying a deckenmalerei.eu ID (P10626)
  - query_<type>_statements.json
      statements already present in Wikidata per entity type, used by
      src/statement_check.py

Usage (from the repository root):

    uv run python -m src.update_queries                 # all files
    uv run python -m src.update_queries people paintings  # only these

The queries are written for QLever: every prefix is declared and there is no
label service. To port a query drafted on query.wikidata.org, paste it into
https://to-qlever.toolforge.org/ first.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SOURCES_DIR = Path("sources")

QLEVER_ENDPOINT = "https://qlever.dev/api/wikidata"
USER_AGENT = "CBDDsync/0.1 (https://github.com/kristbaum/CBDDsync)"

# QLever, unlike the official Wikidata Query Service, has no built-in prefix
# registry — every prefix used below must be declared explicitly.
PREFIXES = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX schema: <http://schema.org/>
"""

ENTITY_QUERY = (
    PREFIXES
    + """
SELECT ?item ?deckenmalerei_eu_ID WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
}
"""
)

PEOPLE_STATEMENTS_QUERY = (
    PREFIXES
    + """
SELECT DISTINCT ?item ?gender WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID;
    wdt:P31 wd:Q5.
  OPTIONAL { ?item wdt:P21 ?gender. }
}
"""
)

BUILDING_STATEMENTS_QUERY = (
    PREFIXES
    + """
SELECT DISTINCT ?item ?inception ?postalCode ?coordinate WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  OPTIONAL { ?item wdt:P571 ?inception. }
  OPTIONAL { ?item wdt:P281 ?postalCode. }
  OPTIONAL { ?item wdt:P625 ?coordinate. }
}
"""
)

# Result keys match src.config.WD_QUERY_KEY_TO_PID exactly.
PAINTING_STATEMENTS_QUERY = (
    PREFIXES
    + """
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
  OPTIONAL { ?item wdt:P2092 ?bildindex. }
}
"""
)

ROOM_STATEMENTS_QUERY = (
    PREFIXES
    + """
SELECT DISTINCT ?item ?inception WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  OPTIONAL { ?item wdt:P571 ?inception. }
}
"""
)

# name -> (output file in sources/, query). "entities" is written as CSV, the
# statement queries as flattened JSON. Rooms and room sequences share the same
# query (README.md); they are only distinguished by which entities happen to
# carry P10626 in each Wikidata class.
QUERIES = {
    "entities": ("query.csv", ENTITY_QUERY),
    "people": ("query_people_statements.json", PEOPLE_STATEMENTS_QUERY),
    "buildings": ("query_building_statements.json", BUILDING_STATEMENTS_QUERY),
    "paintings": ("query_painting_statements.json", PAINTING_STATEMENTS_QUERY),
    "rooms": ("query_room_statements.json", ROOM_STATEMENTS_QUERY),
    "room_sequences": ("query_room_sequence_statements.json", ROOM_STATEMENTS_QUERY),
}


def fetch(url: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(request) as response:
        return response.read()


def run_sparql_query(query: str, accept: str) -> bytes:
    # Content negotiation via the Accept header is what the SPARQL protocol
    # actually honors; a "format" query param is unreliable.
    url = f"{QLEVER_ENDPOINT}?{urllib.parse.urlencode({'query': query})}"
    return fetch(url, accept=accept)


def simplify_bindings(raw_json: bytes) -> list[dict]:
    """Flatten SPARQL JSON results into a list of {var: value} dicts."""
    data = json.loads(raw_json)
    return [
        {var: binding["value"] for var, binding in row.items()}
        for row in data["results"]["bindings"]
    ]


def select_queries(names: list[str]) -> list[str]:
    """Validate the requested query names; no names means all of them."""
    unknown = [n for n in names if n not in QUERIES]
    if unknown:
        raise ValueError(
            f"unknown query name(s): {', '.join(unknown)} "
            f"(choose from: {', '.join(QUERIES)})"
        )
    return names or list(QUERIES)


def update_query(name: str) -> str:
    """Run one query and replace its file in sources/. Returns a summary."""
    filename, query = QUERIES[name]
    path = SOURCES_DIR / filename
    if filename.endswith(".csv"):
        data = run_sparql_query(query, accept="text/csv")
        rows = max(data.count(b"\n") - 1, 0)
        path.write_bytes(data)
    else:
        bindings = simplify_bindings(
            run_sparql_query(query, accept="application/sparql-results+json")
        )
        rows = len(bindings)
        path.write_text(
            json.dumps(bindings, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return f"sources/{filename} ({rows} rows)"


def update_queries(names: list[str]) -> int:
    """Run the given queries; returns the number that failed."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name in select_queries(names):
        print(f"Querying QLever for {name}...")
        try:
            print(f"  -> {update_query(name)}")
        except (urllib.error.URLError, ValueError, KeyError) as e:
            # The old file is left untouched: it is only written after success.
            print(f"  !! {name} failed: {e}", file=sys.stderr)
            failed += 1
    return failed


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Re-run the Wikidata queries on qlever.dev and update sources/."
    )
    ap.add_argument(
        "names",
        nargs="*",
        metavar="name",
        help=f"queries to run (default: all): {', '.join(QUERIES)}",
    )
    args = ap.parse_args()
    try:
        failed = update_queries(args.names)
    except ValueError as e:
        ap.error(str(e))
    if failed:
        sys.exit(f"{failed} quer{'y' if failed == 1 else 'ies'} failed")
    print("✓ Query results updated.")


if __name__ == "__main__":
    main()
