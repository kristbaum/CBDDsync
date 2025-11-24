# CbDD Sync

Set of tools (Python scripts) to syncronize data from deckenmalerei.eu with Wikidata.

## Projects Stats

2025-11-24
Summary of missing entities:

| Category  | Count |
|-----------|-------|
| people    | 1396  |
| buildings | 386   |
| paintings | 5341  |
| **total** | **7123** |

## Scripts

* exists_in_both.py: Python scripts that uses the query.csv file to check if an entity exists both in deckenmalerei.eu db and Wikidata. It outputs tables of the entities missing in Wikidata. There should be three tables: people (sType: ACTOR_PERSON), buildings (sType: OBJECT_BUILDING), paintings (sType: OBJECT_PAINTING). The resulting table have the csv format and contain the "appelation" field as well as the ID field.
* missings statements.py: Calculate possible statements from the deckenmalerei.eu db and checks their existance in Wikidata

## Helpers

query.csv exists to prevent unnessecary queries to the WD-query service and has the following format:

Update Query:

```sparql
SELECT * WHERE {
  ?item wdt:P10626 ?deckenmalerei_eu_ID.
}
```

item,deckenmalerei_eu_ID
http://www.wikidata.org/entity/Q167314,3cd82186-8931-4f8c-84de-f831d3fb579e
http://www.wikidata.org/entity/Q113781459,6b7e31d0-c4c3-11e9-8385-59bf93401dce

entities.json examples:

People:
{
  "modificationDate": 1671024043543,
  "creationDate": 1671024043543,
  "mType": "ENT",
  "appellation": "Miltenberger, Hans",
  "ID": "fb3ee0f6-a6dd-43d8-89b2-de4722f6f6a9",
  "sType": "ACTOR_PERSON",
  "gender": "MALE"
}

Painting:

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
  "iconography": [
    "23O31"
  ]
}

Building:

{
  "addressState": "Bayern",
  "addressLocality": "München",
  "alternativeNames": [
    "München, Paulanerkloster am Neudeck"
  ],
  "buildingInventoryNumber": "cbdd00080",
  "condition": {
    "destroyed": true
  },
  "addressStreet": "Am Neudeck",
  "creationDate": 1649761730167,
  "modificationDate": 1649761730167,
  "appellation": "München, Kirche und Kloster der ehem. Paulaner",
  "moduleNumber": 0,
  "functions": [
    "MONASTIC_CHURCHES_BUILDINGS"
  ],
  "locationLng": 11.5838047,
  "locationLat": 48.1240115,
  "mType": "ENT",
  "ID": "6c96a3b4-eb3f-47f7-af30-dae59672d1ab",
  "addressCountry": "Deutschland",
  "addressZip": "81541",
  "sType": "OBJECT_BUILDING"
}

For formatting Links: https://wikishootme.toolforge.org/#lat=48.1591296&lng=11.5634272&zoom=18