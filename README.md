# CbDD Sync

Set of tools (Python scripts) to syncronize data from deckenmalerei.eu with Wikidata.

## Projects Stats

2026-05-30
Summary of missing entities:

| Category       | Count    |
| -------------- | -------- |
| people         | 1396     |
| buildings      | 373      |
| paintings      | 953      |
| rooms          | 2215     |
| room_sequences | 295      |
| **total**      | **5232** |

Summary of existing entities (in query.csv):
people : 1186
buildings : 830
paintings : 4389
rooms : 1
room_sequences : 1
total : 6407

## Scripts

- **entity_check.py**: Python script that uses the query.csv file to check if an entity exists both in deckenmalerei.eu db and Wikidata. It outputs tables of the entities missing in Wikidata. There should be three tables: people (sType: ACTOR_PERSON), buildings (sType: OBJECT_BUILDING), paintings (sType: OBJECT_PAINTING). The resulting table have the csv format and contain the "appelation" field as well as the ID field.
- **statement_check.py**: Compares potential statements derived from deckenmalerei.eu data against what already exists in Wikidata, and outputs the missing ones in QuickStatements CSV format. It is a generic engine that runs one check per entity type (people, buildings, paintings, rooms, room sequences), driven by the `STATEMENT_CHECKS` config. Each type reads its `existing/existing_<type>.csv` and a cached Wikidata query `sources/query_<type>_statements.json`, and writes `missing/missing_<type>_statements.csv`. Types whose query file is absent are skipped with a note. Statements generated per type: people → sex or gender (P21); buildings → inception (P571), postal code (P281), coordinate location (P625); paintings → creator/inception/materials/dimensions/etc.; rooms & room sequences → inception (P571).

## Helpers

query.csv exists to prevent unnessecary queries to the WD-query service and has the following format:

### Entity Query

Result keys: `item`, `deckenmalerei_eu_ID`. Save as `sources/query.csv` (CSV, not JSON).

```sparql
SELECT ?item ?deckenmalerei_eu_ID WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
}
```

```csv
item,deckenmalerei_eu_ID
http://www.wikidata.org/entity/Q167314,3cd82186-8931-4f8c-84de-f831d3fb579e
http://www.wikidata.org/entity/Q113781459,6b7e31d0-c4c3-11e9-8385-59bf93401dce
```

### Paintings Statement Query

Result keys match `src.config.WD_QUERY_KEY_TO_PID`: `item`, `itemDescription_en`
(**Den**), `itemDescription_de` (**Dde**), `inception` (**P571**), `iconclass`
(**P1257**), `method` (**P2079**), `material` (**P186**), `painter` (**P170**),
`commissioner` (**P88**), `width` (**P2049**), `length` (**P2043**), `height`
(**P2048**), `diameter` (**P2386**), `location` (**P276**), `condition`
(**P5816**), `bildindex` (**P12754**). Save as `sources/query_painting_statements.json`.

```sparql
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
```

### People Statement Query

Result keys: `item`, `gender` (mapped to **P21** sex or gender). Save as `sources/query_people_statements.json`.

```sparql
SELECT DISTINCT ?item ?itemLabel ?gender ?GND_ID WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID;
    wdt:P31 wd:Q5.
  OPTIONAL { ?item wdt:P21 ?gender. }
  OPTIONAL { ?item wdt:P227 ?GND_ID. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],mul,en". }
}
```

### Building Statement Query

Result keys: `item`, `inception` (**P571**), `postalCode` (**P281**), `coordinate` (**P625**, returned as a `Point(lng lat)` WKT literal). Save as `sources/query_building_statements.json`.

```sparql
SELECT DISTINCT ?item ?inception ?postalCode ?coordinate WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  OPTIONAL { ?item wdt:P571 ?inception. }
  OPTIONAL { ?item wdt:P281 ?postalCode. }
  OPTIONAL { ?item wdt:P625 ?coordinate. }
}
```

### Room / Room Sequence Statement Query

Result key: `item`, `inception` (**P571**). Run once per type, filtering on the relevant Wikidata class if desired, and save as `sources/query_room_statements.json` and `sources/query_room_sequence_statements.json`.

```sparql
SELECT DISTINCT ?item ?inception WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  OPTIONAL { ?item wdt:P571 ?inception. }
}
```

### entities.json examples

People:

```json
{
  "modificationDate": 1671024043543,
  "creationDate": 1671024043543,
  "mType": "ENT",
  "appellation": "Miltenberger, Hans",
  "ID": "fb3ee0f6-a6dd-43d8-89b2-de4722f6f6a9",
  "sType": "ACTOR_PERSON",
  "gender": "MALE"
}
```

Painting:

```json
{
  "verbaleDating": "1543",
  "modificationDate": 1658160540972,
  "creationDate": 1619528350118,
  "mType": "ENT",
  "orientation": {
    "north": true
  },
  "appellation": "Zodiakus Krebs",
  "ID": "57d41439-24fc-4006-a823-7f9280a21e37",
  "sType": "OBJECT_PAINTING",
  "position": {
    "ceiling": true
  },
  "iconography": ["23O31"]
}
```

Building:

```json
{
  "addressState": "Bayern",
  "addressLocality": "München",
  "alternativeNames": ["München, Paulanerkloster am Neudeck"],
  "buildingInventoryNumber": "cbdd00080",
  "condition": {
    "destroyed": true
  },
  "addressStreet": "Am Neudeck",
  "creationDate": 1649761730167,
  "modificationDate": 1649761730167,
  "appellation": "München, Kirche und Kloster der ehem. Paulaner",
  "moduleNumber": 0,
  "functions": ["MONASTIC_CHURCHES_BUILDINGS"],
  "locationLng": 11.5838047,
  "locationLat": 48.1240115,
  "mType": "ENT",
  "ID": "6c96a3b4-eb3f-47f7-af30-dae59672d1ab",
  "addressCountry": "Deutschland",
  "addressZip": "81541",
  "sType": "OBJECT_BUILDING"
}
```

For formatting links: <https://wikishootme.toolforge.org/#lat=48.1591296&lng=11.5634272&zoom=18>

## Installation

The project is managed with [uv](https://docs.astral.sh/uv/) and needs no runtime
dependencies beyond the standard library. From the project root directory:

```bash
uv sync            # create .venv and install the dev tools
uv run setup.py    # download the dumps and run the SPARQL queries into sources/
uv run sync.py      # run the analysis
```

`setup.py` replaces every file in `sources/`: it downloads `entities.json`,
`relations.json`, and `resources.json` from the deckenmalerei.eu dump on
GitHub, and runs the SPARQL queries documented below against the Wikidata
Query Service to (re-)generate `query.csv` and each
`query_<type>_statements.json`.

## Development

```bash
uv run pytest        # tests
uv run ruff check .  # lint
uv run ruff format . # format
uv run ty check      # type check
```

### Missing required input files error

Ensure all required files exist in the `sources/` directory:

- `query.csv`
- `entities.json`
- `relations.json`

The script will provide a clear error message if any files are missing.

## Required Input Files

Before running the tools, ensure the following files are present in the `sources/` directory:

- `query.csv` - List of entities already in Wikidata
- `entities.json` - Complete entity data from deckenmalerei.eu
- `relations.json` - Relationship data between entities
- `resources.json` - Additional resource metadata
- `query_<type>_statements.json` - Wikidata statements already present for each entity type, used by the statement check. One file per type: `query_people_statements.json`, `query_building_statements.json`, `query_painting_statements.json`, `query_room_statements.json`, `query_room_sequence_statements.json`. Any type whose file is absent is skipped.

## Output Files

The tool generates CSV files in two directories:

### missing/ directory

Contains entities from deckenmalerei.eu that are NOT yet in Wikidata:

- `missing_people.csv` - Missing person entities
- `missing_buildings.csv` - Missing building entities
- `missing_paintings.csv` - Missing painting entities
- `missing_rooms.csv` - Missing room entities
- `missing_room_sequences.csv` - Missing room sequence entities
- `missing_<type>_statements.csv` - Missing statements in QuickStatements CSV format, one per entity type (`missing_people_statements.csv`, `missing_building_statements.csv`, `missing_painting_statements.csv`, `missing_room_statements.csv`, `missing_room_sequence_statements.csv`)

### existing/ directory

Contains entities that exist in both databases:

- `existing_people.csv` - People already in Wikidata
- `existing_buildings.csv` - Buildings already in Wikidata
- `existing_paintings.csv` - Paintings already in Wikidata
- `existing_rooms.csv` - Rooms already in Wikidata
- `existing_room_sequences.csv` - Room sequences already in Wikidata
