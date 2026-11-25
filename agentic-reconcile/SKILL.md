---
name: agentic-reconcile
description: Match deckenmalerei.eu (CbDD) people and buildings that the sync tool lists as missing from Wikidata against existing Wikidata items, and optionally prepare new items for the ones that have none. A dataset skill for the wikibase-ingest skill (required), which runs the generic pipeline - candidate generation, verification, triage, preflight checks, QuickStatements batches, Como games. This skill adds what only CbDD knows - the ingest file built from the CbDD dump with the sync tool's statement mapping, the classes and occupations of new items, lifetime against the CbDD works, lobid GND links, street addresses, monument components, CbDD duplicate checks - and the review rules. Writes a QuickStatements batch adding the deckenmalerei.eu ID (P10626) to matched items, a curator batch with missing GND/Bildindex IDs (and CREATE blocks with --create), and a Markdown evidence report. Use when asked to reconcile, match, link or create items for entries of missing/missing_people.csv or missing/missing_buildings.csv.
---

# Agentic reconciliation of CbDD entities

The sync tool (`uv run sync.py`) lists CbDD entities without a Wikidata item
carrying their deckenmalerei.eu ID (P10626) in `missing/missing_<type>.csv`.
Many of them **do** have an item, just without the ID. Find that item, prove
it is the same entity, and line up the edit that adds the ID. With
`--create`, entities that turn out to have no item get a new one, with
statements from the sync tool's mapping.

Supported: **people** (`missing/missing_people.csv`, sType `ACTOR_PERSON`) and
**buildings** (`missing/missing_buildings.csv`, sType `OBJECT_BUILDING`).

## This skill is a dataset skill

The **wikibase-ingest** skill owns the pipeline and every generic step; read
its README or `SKILL.md` for the stages, `reference/reconciliation.md`,
`evidence.md`, `options.md` and `adapters.md` for the details, and
`glossary.md` for the terms (source entity, attributes, claim, evidence,
triage). This skill adds only what CbDD knows, at the stage where it is
needed, declared in [adapter.toml](adapter.toml):

| Stage | CbDD part | File |
|---|---|---|
| 0 Intake | the answers that don't change: link property, references, auto-match rules | `adapter.toml` `[options]` |
| 1 Extraction | CbDD dump → ingest file: names and spelling variants, attributes (GND, Bildindex, life dates, coordinates), the P10626/GND/Bildindex claims | `scripts/cbdd_ingest.py` |
| 2 Reconciliation, item creation | item structure and Wikidata conventions for new items: class from the CbDD functions, occupation from the CbDD roles, description pattern, the sync tool's statements (`--create`, `src/config.py` `STATEMENT_CHECKS`), the CbDD reference | `scripts/cbdd_ingest.py` |
| 3 Validation | evidence only CbDD gives: lobid GND links, lifetime against the CbDD works, gender, street address, monument components, already linked | `scripts/cbdd_hints.py` (evidence hook) |
| 3 Validation | duplicate records in CbDD | `scripts/cbdd_preflight.py` (preflight hook) |
| 4 Triage, review | when a match is safe; what is never a candidate | `policy/people.json`, `policy/buildings.json` |
| 4 Triage, review | the evidence dossier for the entities left to you; the review rules below | `scripts/cbdd_context.py` |
| 5 Upload, feedback | preflight + batches + CbDD evidence report, removals, CbDD corrections | `scripts/finish.py` |

`agentic-reconcile/scripts/wikibase-ingest` runs the command line from the
wikibase-ingest checkout next to this repository (`../wikibase-ingest`), or
`$WIKIBASE_INGEST`; if it finds neither, ask the user to clone it. Read the
generic docs there (`../wikibase-ingest/README.md`, `skill/`). This skill
is not packaged or copied anywhere: it lives and runs in this repository.
Don't reimplement the generic steps here.

All commands run from the repository root. Below,
`WI=agentic-reconcile/scripts/wikibase-ingest`, `A=agentic-reconcile`,
`S=agentic-reconcile/scripts`, `T` is `people` or `buildings`, and `I` the
run's `ingest.json`.


## Options

`adapter.toml` `[options]` settles the intake questions of the
wikibase-ingest skill (`reference/options.md`). Ask the user only about the
two that change per run, if the request doesn't say:

- **Create items** for entities without a match (`--create`)? Default: no,
  link only. Recommend it only for buildings and for people with works in
  CbDD; the curator batch holds the CREATE blocks for review either way.
- **Unclear cases**: decide them yourself (default) or prepare a Como game
  (step 6)?

## Inputs

- The entities: a `missing_<type>.csv` (column `ID`), a slice of it, or CbDD
  IDs given by the user. Default **50** per run; a whole table is fine (the
  generators query in bulk, everything is cached), but your review is the
  bottleneck, so do it in blocks.
- `sources/entities.json`, `sources/relations.json`, `sources/query.csv`. If
  they are missing, tell the user to run `uv run setup.py` and `uv run sync.py`.
- Wikidata (public API and WDQS; no token needed), lobid.org for GND records.

## A run

One folder per run, `agentic-reconcile/to_match/<type>_<YYYY-MM-DD>[_n]/`:

| File | Written by | Holds |
|---|---|---|
| `ingest.json` | `cbdd_ingest.py`, then `wikibase-ingest run` | source entities `_:cbdd:<UUID>` with candidates and evidence; claims `<UUID>:P10626` (direct), `<UUID>:P227`/`:P2092` (curator), with `--create` `<UUID>:new:*` (curator, only if created) |
| `ingest.state.json` | wikibase-ingest | decisions, batches, uploads, games |
| `notes.json` | you | what would settle uncertain cases, removals, CbDD corrections, notes (format in `finish.py`) |
| `batches/direct_NNN.qs` | `next` | `Q…⇥P10626⇥"<UUID>"`, one line per match |
| `batches/curator_NNN.qs` + `.md` | `next` | GND/Bildindex the matched item lacks; CREATE blocks of new items (label, description, P10626, P31, …); review sheet |
| `removals.qs` | `finish.py` | `-` lines from `notes.json` |
| `report.md` | `finish.py` | every entity and its evidence, new items, repairs, CbDD corrections, notes |

The flat `*.qs`/`*.md` files in `to_match/` are runs from before the pipeline;
`--skip-done` skips their IDs too. Never edit `missing/` or `existing/`
(regenerated by `sync.py`). Never commit, push or upload unless the user asks.

## Workflow

### 1. Build the ingest file (extraction)

```bash
uv run python $S/cbdd_ingest.py --csv missing/missing_$T.csv --limit 50 --skip-done [--create]
# or explicit IDs: uv run python $S/cbdd_ingest.py <UUID> <UUID> … [--create]
```

It prints the ingest file path. Entities already linked in `query.csv` are left
out. People get their CbDD name in natural order as label, the CbDD
alternative names as aliases, and spelling variants (first given name only,
"von" forms, Joseph/Josef …) as `search_names`, which are searched but never
uploaded; life dates written into a name ("Kopp, Gottfried (1652–1723)")
become P569/P570 attributes.

With `--create`, each entity also gets the statements of a new item, marked
`only_if_created` (dropped if it is matched), all with the CbDD reference:
P31 (human; for buildings a class from the CbDD functions, e.g.
`CHURCHES_BUILDINGS` → church building, else building), the sync tool's
statements (`STATEMENT_CHECKS`: gender; inception, postal code, coordinates)
P106 for artists (painter, plasterer, architect, master builder,
sculptor), and P569/P570 when the CbDD name carries life dates. The P10626 link joins the CREATE block.

### 2. Candidates, CbDD evidence, verify, triage (reconciliation, validation, triage)

```bash
$WI run $A $T $I
```

Runs, with the adapter's settings: candidate generation (people: identifier,
label; buildings: identifier, geo within 300 m of the building types,
label with the street address as search name),
`cbdd_hints.py` (below), `verify`, `triage` with `policy/$T.json`, `check`.
`--step <name>` repeats one step, `--dry-run` prints the commands.
For a building whose CbDD point is far off (Duttenstein points 6.5 km away at
Schloss Taxis), add `$WI candidates $I --method label --entity <id> --write`
and repeat `--step evidence --step verify`.

`cbdd_hints.py` adds, as verified evidence:

- **already linked**: a candidate carrying this CbDD ID (query.csv is older)
  → the entity becomes a match at once;
- people: the item the **CbDD GND record links to** (lobid `sameAs`) as a
  candidate, also when it lacks P227 (the curator batch adds it);
  **lifetime vs. works** (`date`, P569: ✓ fits, ✗ contradicts most works with
  their own dating, ~ fits most); **gender** differs (✗);
- buildings: **street address** equals the item's P6375 or label (✓);
  numbered **monument component** ("… (D-1-81-122-26#1)") ✗, and its monument
  (P361) added as a candidate;
- the entity's `hint`: what the CbDD GND record names
  (`GND 4821135-7 (lobid): 'Sankt Jakobus der Ältere (Mammendorf)'`).

The policies:

| | people | buildings |
|---|---|---|
| automatic match | CbDD GND on a human | identifier (GND, Bildindex) + within 300 m + building type |
| candidate hidden | other GND or other CbDD ID, lifetime contradicts, not human, gender differs, name < 60 % similar | other GND/Bildindex or CbDD ID, not a building type (Stolperstein, street, Bodendenkmal, …), monument component |

A matching street address is evidence (✓), never an automatic match: parts of
a complex share their parent's address (a garden pavilion, a chapel inside a
mill or palace, a friary church next to the friary wing), and so do museum
institutions and rooms. In the full 2026-11 test 10 of 12 address-only
matches were wrong in scope. Routes: `match` (done), `game` (shown candidates
left, you decide), `curator` (none left; review the hidden ones), with
`--create` also `create` (nothing found: a new item, still reviewed in the
curator batch).

`$WI status $I` shows the counts. **Never `triage --force`**: it re-routes the
claims too. To undo an automatic match, use `decide` (step 3).

### 3. Review (your part of triage)

**Spot-check automatic matches first**: read 10 random ones (`route_reason`,
the candidate's evidence) against the dossier. A wrong kind of match means a
policy rule is too loose: fix `policy/<type>.json` and the matches with
`decide`, and tell the user. With `--create`, check every `create` entity
too: absence on Wikidata is often a search that missed (another name, an
offset point).

Then decide every entity still `reconcile`. Build dossiers in blocks:

```bash
uv run python $S/cbdd_context.py <UUID> [<UUID> …]
```

and read each entity's candidates in the ingest file: shown ones with their ✓/✗
evidence and score, **hidden ones with the reason** (`hidden`). A candidate
hidden for "other GND" or a lifetime ✗ is often still the right one (see the
rules below), so look at those yourself. Look things up where the evidence
leaves a doubt ("Wikidata lookups"). Then:

| Your verdict | Record it |
|---|---|
| **high** (rules below) | `$WI decide $I _:cbdd:<UUID>=Q… --reason "<the evidence, one line>"` |
| **no match**, link only | `$WI decide $I _:cbdd:<UUID>=drop --reason "searched …; candidates Q… (why not)"` |
| **no match**, `--create` | `$WI decide $I _:cbdd:<UUID>=create --reason "searched …"` |
| **medium** | leave it `reconcile`; put what would settle it into `notes.json` → `uncertain` |
| automatic match or creation is wrong | `$WI decide $I _:cbdd:<UUID>=reconcile` (or `=Q…` for the right item) |

Write the reason as evidence, not opinion: "GND 118… on item; painter; works
1776–1790 fit 1757–1805; text: 'einer Gammertinger Malerfamilie'". It goes
into the report. Collect removals, Wikidata duplicates and CbDD errors in
`notes.json` as you go.

### 4. Finish (preflight, batches)

```bash
uv run python $S/finish.py $I
```

It runs `wikibase-ingest preflight` with the adapter, and refuses (writes
nothing) when a matched item is missing or redirected, already carries
another CbDD ID, or is the match of two entities; when one GND or Bildindex
value would go onto two items (CbDD gives a parish's GND to several
buildings: `decide <UUID>:P227=reject` for the wrong ones); or when CbDD has a
second record with the matched entity's GND (a CbDD duplicate, "Bys" and
"Byss": undo the match or name the other UUID in `cbdd_corrections`). A
malformed P10626 next to the valid one is a warning with the removal line for
`notes.json`. Otherwise statements already on their items become skips, and
it runs `wikibase-ingest next` and writes `removals.qs` and `report.md`.

### 5. Hand over

Summarise for the user: matched (automatic / yours), new items, uncertain,
no match, repairs, and the file paths. Don't upload; the user reviews and
uploads:

1. `batches/direct_NNN.qs` to QuickStatements 3, then
   `$WI resolve $I batch-<id>-report.csv` (records what went through;
   `$WI report $I` shows what is left);
2. `batches/curator_NNN.qs` after reading its review sheet (CREATE blocks
   first; `resolve` its report too, so new QIDs are recorded);
3. `removals.qs` after reading the report's Repairs section.

### 6. Optional: a Como game for the uncertain ones

When many entities stay medium with 2–4 plausible candidates, players can
pick the right one. The match is the edit, so the game writes P10626 itself:

```bash
$WI como $I --link-property P10626            # como/reconcile_person.json or reconcile_building.json
$WI validate-game agentic-reconcile/to_match/<run>/como/reconcile_person.json
```

Review the file's settings first (the wikibase-ingest skill covers game
design). The user creates the game from the file. Later,
`$WI como-sync $I <game URL>` applies the answers. "None of these" rules the
shown candidates out for good; with `--create` it makes the entity a new
item, which the next `finish.py` puts into the curator batch.

## CbDD evidence rules

### People

| Check | Wikidata | CbDD evidence | Rule |
|---|---|---|---|
| Lifetime vs. works | `P569`, `P570`, `P1317`, `P2031`/`P2032` | dating of works in roles where the person must be alive | Born ≥ ~12 years before the first work (≈20 for architects/master builders), died ≤ ~2 years before the last. `cbdd_hints` applies this per role: a work fits if any year of its dating fits, because CbDD datings list a building's whole history ("1385-1835/42, 1944/45"). A ✗ on a GND match is therefore usually a dating artefact (restorers, later residents, paintings bought for a collection), rarely a wrong identity. |
| Exempt roles | | `TEMPLATE_PROVIDERS`, `REFERENCE_PERSONS`, `DONORS` | Templates are often engravings decades older; depicted persons can be long dead. The person only has to have lived *before* the work. |
| Commissioners | | `COMMISSIONERS` | Nobles, abbots, abbesses, prince-bishops; they may have commissioned as minors or died before completion. More slack, but the office must fit the place and time (a prince-abbess of Buchau, an abbot of the monastery the work is in). |
| Occupation | `P106` | the role | painter/fresco painter ↔ `PAINTERS`; stuccoist ↔ `PLASTERERS`; architect, master builder ↔ `ARCHITECTS`/`BUILDERS`; sculptor ↔ `SCULPTORS`. Missing is no contradiction; incompatible is. |
| Place | `P19`, `P20`, `P937`, `P27` | places of work | Same region, or a known itinerant artist. A painter who never left Italy, working only in Bavaria per CbDD, is suspicious. |
| Text facts | descriptions, sitelinks | CbDD text passages in the dossier | Life dates, family, offices must agree ("Joseph Anton Reiser (1757–1805)", "einer Gammertinger Malerfamilie", "Bauinspektor"). |
| Already linked | `P10626` | | A candidate with a **different** P10626 is hidden: report it as a possible CbDD duplicate. |

Searching by hand: CbDD writes "Surname, Given names". Try the full-text
search (`list=search` with `haswbstatement:P31=Q5`, finds aliases and
descriptions such as "10 Mar 1706 - 1750 Erlangen") and the GND via lobid
(`https://lobid.org/gnd/search?q=preferredName:"<Surname, Given>" OR variantName:"<…>"&filter=type:Person&format=json`):
GND variant names bridge spellings (CbDD "Mermos" = Wikidata "Mermoos"), and
the GND biography often states the office ("40. Abt von Kaisheim"). A GND found
this way leads to the item via `P227`. Genealogy items (P1819, P2600) often carry
dates only in the description and full given names in the aliases; family
links (P22/P25/P40) can confirm what the CbDD text says. Co-workers and
buildings with QIDs (in the dossier) are strong hints: a candidate that is
`P170` creator of a painting in the same building.

### Buildings

| Check | Wikidata | CbDD evidence | Rule |
|---|---|---|---|
| Location | `P625` | coordinates | Within ~300 m (large complexes more). |
| Locality | `P131`, `P281`, `P6375` | `addressLocality`, `addressZip`, `addressStreet` | Must agree. |
| Scope | `P31`, `P361`/`P527` | name, functions, "Part of", parts | Same *scope*: "Kloster X, Bibliothek" is not the item for the whole monastery, and a church is not its monastery. CbDD part + Wikidata whole only = **no match**. |
| Identity over time | `P571`, `P576`, `P5816` | dating, condition | A destroyed and rebuilt building may have separate items; match the one CbDD describes (the baroque interiors). |
| Identifiers | `P227`, `P2092`, `P4244` | normdata | Any matching identifier is strong evidence, but check the GND's lobid name in the hint first. |

Patterns seen in practice (565-building run, 2026-10):

- **Churches** are the easy majority: a church item within ~10 m whose patron
  matches is high. Patron variants are the same patron: Laurentius = Lorenz,
  Johannes Baptist = Johannes der Täufer = Johann, Nikolai = Nikolaus,
  Inventio Crucis / Kreuzauffindung = Heilig Kreuz, Margareta = Margaretha =
  Margareth, Kastulus = Castulus, St. Pölten = St. Hippolyt. CbDD alternative
  names often carry the Wikidata label ("Ramsachkircherl", "Maria im Tal"). A
  different patron at the same spot is a contradiction.
- **Town houses** match by address (✓ address from `cbdd_hints`); compare
  street *and* number exactly, and check the item is the house, not its
  complex or a museum in it. The neighbours of a house usually have
  items, the house itself often not (Lübeck, Lüneburg: many CbDD houses have no
  item yet → no match). Monument items labelled with the bare address
  ("Mengstraße 19", P131 Lübecker Altstadt, P1435) often have **no P625**:
  only the label generator finds them. Label = CbDD street and number + same
  town (P131) + P31 building + no other P10626 is high (2026-11: 8 of 50
  October leftovers were such items). Check `P131`: "Markt 9" exists in
  dozens of towns.
- **Bavarian monument items come in layers**: the monument item (name or
  "Baudenkmal D-…", address in `P6375`) and numbered components ("Pfarrhof
  Kirchplatz 8 … (D-1-81-122-26#1)") with `P361` → the monument. Match the
  monument (`cbdd_hints` hides components and adds the monument). Bodendenkmal
  items are never the building but sit on the same spot: a church 85 m from the
  CbDD point whose Bodendenkmal is also 85 m away means the point is offset.
- **Monasteries**: for the whole complex ("ehem. Augustiner-Chorherrenstift",
  alt. name "Kloster X") the monastery item with the dewiki article is the
  match, not the Germania Sacra item next to it ("Kloster in Deutschland", P31
  Kloster + religiöse Gemeinschaft, QIDs around Q2897…–Q2898…, the
  institution). A single wing, library, church or chapel needs its own item.
- **Institution vs. building**: museums, courts, libraries, schools often
  have only an institution item. High only if it is also typed as the building
  (Fachwerkhaus, Bauwerk, Gebäude) or names it ("Schwedenspeicher-Museum");
  otherwise medium.
- **CbDD rooms disguised as buildings** ("Fembohaus, Tanzsaal", "Pellerhaus,
  Schönes Zimmer, heute im Stadtmuseum"): the house item is a scope mismatch →
  medium.
- **One Wikidata item, two CbDD entries** (double church upper/lower church;
  provostry palace + church in one item): neither is matched; both medium
  (`finish.py` refuses one QID for two entities).
- **CbDD normdata is not always the building's**: the GND can be the parish
  ("Pfarrei St. Georg"), the collection (Gemäldegalerie Düsseldorf), the town
  (Schorndorf), a namesake church elsewhere, or another building of the
  complex (Sanssouci for the Lordmarschallhaus). Compare the lobid name in the
  hint before trusting an identifier match, or a hidden "other GND".
- **CbDD coordinates are sometimes far off** (Weilheim St. Pölten points at
  the parish office). If no candidate fits, search by name before "no match".

### Decide

- **high**: a matching GND (or Bildindex) with no contradiction, **or** at
  least two independent agreeing hints (name + lifetime fits the works +
  occupation; coordinates + name + locality) with no contradiction and no
  second candidate that fits as well.
- **medium**: plausible but thin (name and period fit, nothing else
  confirms), or two candidates not separable.
- **no match**: no candidate, or all contradicted.

One real contradiction (wrong lifetime, wrong gender, different P10626, wrong
scope) rules a candidate out, however good the name. Never put two CbDD IDs on
one QID or one CbDD ID on two QIDs; downgrade both to medium. Don't guess:
every reason must come from the dossier, the source JSON or a statement you
looked up.

## Repairs and corrections

| Found | Where it goes |
|---|---|
| Matched item lacks the CbDD GND / Bildindex | nothing to do: the ingest file's `<UUID>:P227`/`:P2092` claims go into the curator batch with the CbDD reference (`S248 Q107174967 S10626 "<UUID>"`); values already present are skipped by preflight. If the GND names something else (lobid hint), `$WI decide $I <UUID>:P227=reject --reason …` and add a CbDD correction |
| Malformed value on Wikidata (a P10626 that is no UUID, `"cbdd10059"`, next to the valid one) | `notes.json` → `removals`: `{"line": "-Q…\tP10626\t\"cbdd10059\"", "why": "…"}` |
| A demonstrably wrong statement (identifier of another building, wrong P131) | `removals` (plus the correct value in `notes` if known) |
| Two Wikidata items for the same building/person | `notes`: merging is not reversible by batch; the user merges via Special:MergeItems |
| Item already carries another CbDD ID (CbDD duplicate) | `cbdd_corrections` |
| Wrong or malformed GND/Bildindex in CbDD, offset coordinates, wrong address, two CbDD records for one entity | `cbdd_corrections` |

Repairs touch only statements you verified; when in doubt, put the case in
`notes`. Removals carry no reference.

## Wikidata lookups

With the Wikidata MCP server: `search_items`, `get_statements`,
`execute_sparql`. Its instructions warn that its IDs may differ from the live
ones, so take QIDs for decisions from the public API. Without it (send a
descriptive `User-Agent`):

- Name search: `https://www.wikidata.org/w/api.php?action=wbsearchentities&search=<name>&language=de&uselang=de&type=item&limit=20&format=json`
- Full text: `…/w/api.php?action=query&list=search&srsearch=<text> haswbstatement:P31=Q5&format=json`
- Exact identifier: `…/w/api.php?action=query&list=search&srsearch=haswbstatement:P227=<GND>&format=json`
- Items: `wbgetentities` with up to 50 `ids=Q1|Q2|…`, much faster than one query per item.
- SPARQL: `https://query.wikidata.org/sparql` (WDQS, has `wikibase:around`;
  answers 502/429 now and then, retry with a pause). QLever
  (`https://qlever.dev/api/wikidata`) is faster for plain lookups but has no
  label or geo service.

Works of a candidate person (to compare with the CbDD works):

```sparql
SELECT ?work ?workLabel ?inception ?locationLabel WHERE {
  VALUES ?p { wdt:P170 wdt:P88 wdt:P84 } ?work ?p wd:<QID>.
  OPTIONAL { ?work wdt:P571 ?inception. }
  OPTIONAL { ?work wdt:P276 ?location. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de,en,mul". }
}
```

## Fixed IDs

| What | ID |
|---|---|
| deckenmalerei.eu ID | `P10626` |
| GND ID | `P227` |
| Bildindex object number (CbDD `normdata.bildindex`, digits only) | `P2092` |
| Bavarian monument authority ID | `P4244` |
| stated in: CbDD (reference) | `Q107174967` |
| human | `Q5` |
| male / female | `Q6581097` / `Q6581072` |
| building types (geo filter, class check): built structure / cultural heritage ensemble / museum | `Q811979` / `Q1516079` / `Q33506` |
