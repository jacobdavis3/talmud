## Talmud Sage Statements (Python)

Small Python app that builds a searchable SQLite database of Talmud statements by sage.

### What this does

- Loads a sage list + aliases from `data/sages.json`.
- Fetches Talmud text from Sefaria (tractate by tractate / daf by daf).
- Detects sage mentions in each segment.
- Stores statements in SQLite so you can search by rabbi name.
- Provides a minimal web UI to search a sage and list all matched statements.

### Project files

- `ingest.py`: build/refresh the SQLite DB from Sefaria text.
- `app.py`: Flask API + web UI.
- `matcher.py`: Hebrew normalization and sage mention matching.
- `talmud_db.py`: DB schema and query helpers.
- `tractates.py`: tractate max-daf map.
- `data/sages.json`: sage metadata and aliases.

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Build database

Default is only `Berakhot`:

```bash
python ingest.py
```

Choose tractates explicitly:

```bash
python ingest.py --tractates Berakhot Shabbat Eruvin
```

Choose identification source:

```bash
# Recommended: Sefaria person-topic identification
python ingest.py --mode sefaria --tractates Berakhot

# Hybrid fallback (Sefaria first, alias heuristic if needed) (Recommended)
python ingest.py --mode hybrid --tractates Berakhot

# Legacy alias-only behavior
python ingest.py --mode heuristic --tractates Berakhot
```

This writes `data/talmud.sqlite3`.

### Run app

```bash
python app.py
```

Open: `http://127.0.0.1:5000`

### API

- `GET /api/sages?q=<name>`
- `GET /api/statements?sage_id=<id>`
- `GET /api/sage/<id>` (full sage info + aliases, used for hover tooltip)

### Notes

- Canonical sages are always loaded from `data/sages.json` (your curated SAGE_INFO list).
- `--mode sefaria` uses Sefaria API v3 named-entity tags (`namedEntityLink`) and maps matches onto the curated sages via Hebrew alias normalization.
- In `--mode sefaria` and `--mode hybrid`, entities are also filtered to the Sefaria **Talmudic Figures** category (`/topics/category/talmudic-figures`).
- Ambiguous entities are excluded by default to reduce confusion; add `--allow-ambiguous` to include only those with exactly one person possibility.
- `--mode heuristic` uses local alias matching from `data/sages.json` and may include ambiguous matches.
