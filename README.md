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
- **statement_check.py**: Compares potential statements derived from deckenmalerei.eu data against what already exists in Wikidata. Outputs missing statements in QuickStatements CSV format (`missing/missing_painting_statements.csv`). Requires `sources/query_painting_statements.json` from a Wikidata query.

## Helpers

query.csv exists to prevent unnessecary queries to the WD-query service and has the following format:

### Entity Query

```sparql
SELECT * WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
}
```

### Paintings Statement Query

This query retrieves all painting data with their associated properties:

```sparql
SELECT DISTINCT
  ?item
  ?itemLabel_en
  ?itemLabel_de
  ?deckenmalerei_eu_ID
  ?inception
  ?location
  ?locationLabel_en
  ?locationLabel_de
  (GROUP_CONCAT(DISTINCT ?painterQID; separator=";") AS ?painters)
  (GROUP_CONCAT(DISTINCT ?commissionerQID; separator=";") AS ?commissioners)
  (GROUP_CONCAT(DISTINCT ?materialQID; separator=";") AS ?materials)
  (GROUP_CONCAT(DISTINCT ?methodQID; separator=";") AS ?methods)
  (GROUP_CONCAT(DISTINCT ?depictsQID; separator=";") AS ?iconography)
  ?height
  ?width
  ?length
  ?diameter
  ?bildindex
  ?conditionQID
  ?positionQID
WHERE {
  # Main item with deckenmalerei.eu ID
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
  
  # Get English label directly
  OPTIONAL { ?item rdfs:label ?itemLabel_en. FILTER(LANG(?itemLabel_en) = "en") }
  
  # Get German label directly
  OPTIONAL { ?item rdfs:label ?itemLabel_de. FILTER(LANG(?itemLabel_de) = "de") }
  
  # Inception/dating
  OPTIONAL { ?item wdt:P571 ?inception. }
  
  # Location (typically a building)
  OPTIONAL { 
    ?item wdt:P276 ?location.
    OPTIONAL { ?location rdfs:label ?locationLabel_en. FILTER(LANG(?locationLabel_en) = "en") }
    OPTIONAL { ?location rdfs:label ?locationLabel_de. FILTER(LANG(?locationLabel_de) = "de") }
  }
  
  # Painters/creators
  OPTIONAL { 
    ?item wdt:P170 ?painter.
  }
  
  # Commissioners
  OPTIONAL { 
    ?item wdt:P825 ?commissioner.
  }
  
  # Materials
  OPTIONAL { 
    ?item wdt:P186 ?material.
  }
  
  # Production methods
  OPTIONAL { 
    ?item wdt:P2079 ?method.
  }
  
  # Iconography (depicts)
  OPTIONAL { 
    ?item wdt:P180 ?depicts.
    BIND(STRAFTER(STR(?depicts), "http://www.wikidata.org/entity/") AS ?depictsQID)
  }
  
  # Dimensions
  OPTIONAL { ?item wdt:P2048 ?height. }
  OPTIONAL { ?item wdt:P2049 ?width. }
  OPTIONAL { ?item wdt:P2043 ?length. }
  OPTIONAL { ?item wdt:P2386 ?diameter. }
  
  # Bildindex (Marburg Index)
  OPTIONAL { ?item wdt:P2092 ?bildindex. }
  
  # Condition
  OPTIONAL { 
    ?item wdt:P5816 ?condition.
    BIND(STRAFTER(STR(?condition), "http://www.wikidata.org/entity/") AS ?conditionQID)
  }
  
  # Position (e.g., ceiling painting, wall painting)
  OPTIONAL { 
    ?item wdt:P518 ?position.
    BIND(STRAFTER(STR(?position), "http://www.wikidata.org/entity/") AS ?positionQID)
  }
}
GROUP BY ?item ?itemLabel_en ?itemLabel_de ?deckenmalerei_eu_ID ?inception 
         ?location ?locationLabel_en ?locationLabel_de
         ?height ?width ?length ?diameter ?bildindex ?conditionQID ?positionQID
ORDER BY ?item
```

**Column mapping:**

- url: Constructed from `?item`
- appellation: `?itemLabel_de` or `?itemLabel_en`
- verbaleDating/processedDating: `?inception`
- iconography: `?iconography` (grouped depicts QIDs)
- productionMethods_wd: `?methods`
- productionMaterials_wd: `?materials`
- position: `?positionQID`
- normdata: `?bildindex`
- commissioner: `?commissioners`
- painter: `?painters`
- width/length/height/diameter: respective dimension fields
- description_en/description_de: Constructed from location labels
- location: `?location` QID
- condition: `?conditionQID`
- wikidata_qid: Extracted from `?item`
- ID: `?deckenmalerei_eu_ID`

item,deckenmalerei_eu_ID
<http://www.wikidata.org/entity/Q167314,3cd82186-8931-4f8c-84de-f831d3fb579e>
<http://www.wikidata.org/entity/Q113781459,6b7e31d0-c4c3-11e9-8385-59bf93401dce>

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

From the project root directory:

```bash
python sync.py
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
- `query_painting_statements.json` - Wikidata statements for existing paintings (for statement check)

## Output Files

The tool generates CSV files in two directories:

### missing/ directory

Contains entities from deckenmalerei.eu that are NOT yet in Wikidata:

- `missing_people.csv` - Missing person entities
- `missing_buildings.csv` - Missing building entities
- `missing_paintings.csv` - Missing painting entities
- `missing_rooms.csv` - Missing room entities
- `missing_room_sequences.csv` - Missing room sequence entities
- `missing_painting_statements.csv` - Missing painting statements in QuickStatements CSV format

### existing/ directory

Contains entities that exist in both databases:

- `existing_people.csv` - People already in Wikidata
- `existing_buildings.csv` - Buildings already in Wikidata
- `existing_paintings.csv` - Paintings already in Wikidata
- `existing_rooms.csv` - Rooms already in Wikidata
- `existing_room_sequences.csv` - Room sequences already in Wikidata
