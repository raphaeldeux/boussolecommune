# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development (local, without Docker)
```bash
pip install -r requirements.txt
cp .env.example .env          # then edit with local DB credentials
python seed.py                # initialize 41 indicators (idempotent)
python seed_communes.py       # populate INSEE commune reference data (~35k rows)
python wsgi.py                # runs Flask dev server on http://localhost:5000
```

### Docker (recommended)
```bash
docker compose up -d
docker compose exec web python seed.py
docker compose exec web python seed_communes.py
# App exposed at http://localhost:5001
```

### Rebuild after code changes
```bash
docker compose up -d --build
```

No test framework or linter is configured in this project.

## Architecture

**Stack:** Flask 3.0 + PostgreSQL 16 + Gunicorn (2 workers, 120s timeout) behind Nginx. Optional Ollama (local LLM) for AI-generated summaries.

### Application structure
- `app/__init__.py` — app factory: registers blueprints, CSRF protection, security headers, runs DB init + auto-seeding on startup
- `app/config.py` — environment variables (DATABASE_URL, ADMIN credentials, SECRET_KEY, OLLAMA settings)
- `app/database.py` — raw psycopg2 connection wrapper; `init_db()` creates schema and uses `pg_advisory_lock` to prevent race conditions across Gunicorn workers
- `app/models/` — thin data-access layer (one file per entity, direct SQL via psycopg2)
- `app/routes/public.py` — public-facing pages (dashboard, thematic, compare, councils)
- `app/routes/admin.py` — 40+ admin endpoints (login, data entry, CSV upload, interpretation, user/city management, reference bank)
- `app/services/` — business logic: scoring, CSV parsers, Ollama integration, external API fetchers

### Multi-tenancy
A single instance serves multiple communes. Every data row carries a `ville_id` FK. The session stores `admin_ville_id` / `public_ville_id` to scope queries. Super-admins see all cities; gestionnaires see only their assigned cities.

### Scoring system (A–E)
- 41 indicators across 6 weighted thematic categories + 4 portrait indicators
- Each indicator has thresholds and a `sens` (haut/bas/neutre); scores adjusted by trajectory and benchmark comparison
- Logic lives in `app/services/scoring.py`

### Data ingestion channels
- OFGL CSV, generic CSV, ma-cantine API, manual entry, Ollama PDF→summary
- See `app/services/` for parsers and fetchers

### Key environment variables (`.env`)
`DATABASE_URL`, `POSTGRES_PASSWORD`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY`, `FLASK_ENV`, `OLLAMA_URL`, `OLLAMA_MODEL`
