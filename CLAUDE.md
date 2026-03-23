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
- **41 indicators** across 6 weighted thematic categories (Finances 25%, Cadre Vie 20%, Personnes 20%, Lien Social 15%, Démocratie 12%, Vivant 8%) plus 4 portrait indicators
- Each indicator has `seuil_vert`/`seuil_orange`/`seuil_rouge` thresholds and a `sens` (haut/bas/neutre)
- Raw score 1–5 is adjusted by trajectory (YoY change ±0.5–1.5) and benchmark comparison vs. similar communes (±0.5–1.5), clamped to [1, 5]
- Scores can be overridden manually via the interpretation table
- Logic lives in `app/services/scoring.py`

### Data ingestion channels
1. **OFGL CSV** (`app/services/parser_ofgl.py`) — municipal finance data
2. **Generic CSV** (`app/services/parser_csv.py`) — flexible format: `année, indicateur_id, valeur, source`
3. **ma-cantine API** (`app/services/fetchers/macantine.py`) — EGAlim indicators (bio, sustainable, fish)
4. **Manual entry** — admin saisie page
5. **Ollama PDF→Summary** (`app/services/ollama_service.py`) — council meeting PDFs → citizen-friendly text via local LLM

### Authentication & security
- Session-based auth with CSRF tokens validated on all admin POSTs
- Rate limiting: 5 failed login attempts per IP per 15 minutes
- 8-hour session TTL; HTTPONLY + SAMESITE=Lax cookies
- Production mode enforces non-default SECRET_KEY and ADMIN_PASSWORD at startup
- Security headers set in app factory (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)

### Key environment variables (`.env`)
```
DATABASE_URL        postgresql://boussole:password@db:5432/boussolecommune
POSTGRES_PASSWORD   password for the db container
ADMIN_USERNAME      initial super-admin login
ADMIN_PASSWORD      initial super-admin password (must differ from 'admin' in production)
SECRET_KEY          Flask session secret (required in production)
FLASK_ENV           development | production
OLLAMA_URL          http://ollama:11434 (default)
OLLAMA_MODEL        llama3.2:3b (default)
```
