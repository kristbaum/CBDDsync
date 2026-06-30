# AGENTS.md — CBDDsync

## Project Purpose

CBDDsync synchronizes data between **deckenmalerei.eu** (a German database of baroque ceiling paintings, the "CbDD") and **Wikidata**. It identifies entities and statements present in deckenmalerei.eu that are missing from Wikidata, and produces output files ready for upload via [QuickStatements](https://quickstatements.toolforge.org/).

The Wikidata property linking entities is **P10626** (`deckenmalerei.eu ID`).

---

## Repository Layout

```text
CBDDsync/
├── sync.py                     # Entry point — runs entity_check then statement_check
├── src/
│   ├── config.py               # All mappings (sType→label, columns, WD property IDs, value maps)
│   ├── entity_check.py         # Compares entities between CbDD and Wikidata; writes missing/existing CSVs
│   ├── statement_check.py      # Generic statement-comparison engine; runs one check per entity type
│   └── utils.py                # Pure helper functions (date parsing, field mapping, bildindex extraction)
├── sources/                    # Input files (not committed — must be supplied before running)
│   ├── query.csv               # Wikidata SPARQL result: item URL + deckenmalerei_eu_ID
│   ├── entities.json           # Full entity export from deckenmalerei.eu
│   ├── relations.json          # Relationship data (PART, PAINTERS, COMMISSIONERS, …)
│   ├── resources.json          # Additional resource metadata
│   ├── query_people_statements.json        # Wikidata SPARQL result: existing people statements
│   ├── query_building_statements.json      # Wikidata SPARQL result: existing building statements
│   ├── query_painting_statements.json      # Wikidata SPARQL result: existing painting statements
│   ├── query_room_statements.json          # Wikidata SPARQL result: existing room statements
│   └── query_room_sequence_statements.json # Wikidata SPARQL result: existing room-sequence statements
├── missing/                    # Generated output: entities/statements absent from Wikidata
│   ├── missing_people.csv
│   ├── missing_buildings.csv
│   ├── missing_paintings.csv
│   ├── missing_rooms.csv
│   ├── missing_room_sequences.csv
│   └── missing_*_statements.csv  # QuickStatements-ready CSV, one per entity type
├── existing/                   # Generated output: entities present in both databases
│   ├── existing_people.csv
│   ├── existing_buildings.csv
│   ├── existing_paintings.csv
│   ├── existing_rooms.csv
│   └── existing_room_sequences.csv
└── errors/
    └── duplicates.md           # Known data quality issues (e.g. duplicate buildings)
```

---

## Data Model

### Entity types (`sType`)

| sType                 | Label          | Description                                                       |
| --------------------- | -------------- | ----------------------------------------------------------------- |
| `ACTOR_PERSON`        | people         | Painters, commissioners, and other persons                        |
| `OBJECT_BUILDING`     | buildings      | Churches, palaces, and other structures                           |
| `OBJECT_ROOM`         | rooms          | Named rooms within a building                                     |
| `OBJECT_ROOM_SEQUENCE`| room_sequences | Groups of related rooms (e.g. a suite of representational rooms)  |
| `OBJECT_PAINTING`     | paintings      | Ceiling or wall paintings                                         |

### Key ID fields

- **deckenmalerei.eu ID**: UUID, stored in `ID` field of each entity JSON object and in `sources/query.csv` as `deckenmalerei_eu_ID`.
- **Wikidata QID**: e.g. `Q12345`. Extracted from the `item` URL column in `query.csv`.

### Relationship graph (`relations.json`)

Relations link entities by `ID` (source) → `relTar` (target) with a `relDir` and `sType`:

- `PART` + `->` : parent–child spatial containment (painting → room → building)
- `PAINTERS` + `->` : painting → painter
- `COMMISSIONERS` + `->` : painting → commissioner

`entity_check.py` traverses `PART` relations upward from a painting to find its host building.

---

## Running the Tool

```bash
python sync.py
```

This runs both analysis steps sequentially and prints a summary to stdout.

### Prerequisites

These input files must exist in `sources/` before running:

```text
sources/query.csv
sources/entities.json
sources/relations.json
sources/resources.json
sources/query_<type>_statements.json   # one per entity type, only needed for statement_check
```

`statement_check` runs one check per entity type and skips (with a note) any
type whose `query_<type>_statements.json` is absent, so missing statement-query
files are not fatal. The SPARQL queries to generate `query.csv` and the
`query_<type>_statements.json` files are documented in [README.md](README.md).

---

## Output Formats

### `missing/missing_*.csv` and `existing/existing_*.csv`

Plain CSV files with entity-type-specific columns defined in `src/config.py` (`COLUMNS_MISSING`, `COLUMNS_EXISTING`). The `existing_*` files add a `wikidata_qid` column.

Notable derived/computed columns:

| Column                  | Source                                                                      |
| ----------------------- | --------------------------------------------------------------------------- |
| `url`                   | `https://www.deckenmalerei.eu/{ID}`                                         |
| `wikishootme`           | `https://wikishootme.toolforge.org/#lat=…&lng=…`                            |
| `processedDating`       | Parsed from `verbaleDating` (e.g. `"ca. 1820"` → `"1820"`)                 |
| `productionMethods_wd`  | CbDD technique codes → Wikidata Q IDs                                       |
| `productionMaterials_wd`| CbDD material codes → Wikidata Q IDs                                        |
| `position`              | `ceiling`/`wall` → Wikidata Q IDs                                           |
| `condition`             | `destroyed`/`restored`/… → Wikidata Q IDs                                  |
| `location`              | Wikidata QID of the host building (resolved via PART relations)             |
| `description_en/de`     | `"painting in {building_name}"` / `"Malerei in {building_name}"`           |
| `painter` / `commissioner` | Semicolon-separated Wikidata QIDs from relations                         |

### `missing/missing_painting_statements.csv`

QuickStatements CSV format. Columns: `qid` + one column per Wikidata property ID (e.g. `P170`, `P571`). Each row encodes one statement. Values are formatted for QS:

- Q-items: `Q12345`
- Dates: `+1820-00-00T00:00:00Z/9` (year precision)
- Dimensions: `42.5U174728` (centimetres)
- Strings: `"value"`
- Descriptions: plain string under `Den` / `Dde` pseudo-columns

---

## Wikidata Property Reference

| Property                             | PID                              | Used for                    |
| ------------------------------------ | -------------------------------- | --------------------------- |
| deckenmalerei.eu ID                  | P10626                           | Primary link between databases |
| creator                              | P170                             | Painter                     |
| commissioned by                      | P88                              | Commissioner                |
| inception                            | P571                             | Dating                      |
| location                             | P276                             | Host building               |
| made from material                   | P186                             | Materials                   |
| fabrication method                   | P2079                            | Techniques                  |
| depicted Iconclass                   | P1257                            | Iconography codes           |
| width / length / height / diameter   | P2049 / P2043 / P2048 / P2386   | Dimensions (cm)             |
| Bildindex ID                         | P12754                           | Marburg art index           |
| state of conservation                | P5816                            | Condition                   |
| applies to part                      | P518                             | Position (ceiling/wall)     |

---

## Config (`src/config.py`)

All lookup tables live here. When adding new entity types, production methods, materials, positions, or conditions, update the relevant `*_MAP` dict and the `COLUMNS_MISSING`/`COLUMNS_EXISTING` lists.

Statement comparison is driven by the `STATEMENT_CHECKS` dict — one entry per entity type. Each entry wires up an `existing_*.csv` (input), a `query_<type>_statements.json` (cached Wikidata statements), an output `missing_*_statements.csv`, the `column_to_pid` / `wd_query_key_to_pid` mappings, and optional `value_maps` (e.g. `GENDER_MAP`) and a `coordinate` helper (combine two lat/lng columns into one P625 value). `src/statement_check.py` is a generic engine over this config; to add statements for a type, edit only `STATEMENT_CHECKS` (and add the matching SPARQL query). `PAINTING_COLUMN_TO_PID` and `WD_QUERY_KEY_TO_PID` are reused by the `paintings` entry.

---

## Known Issues / Errors

- `errors/duplicates.md` lists deckenmalerei.eu entities that map to the same building (data quality issue in the source database, not a code bug).
- `POSITION_MAP` maps `equipment` to the wall-painting QID as a temporary approximation.
- `CONDITION_MAP` has empty strings for `translocated` and `paintedOver` — no Wikidata Q IDs assigned yet.
