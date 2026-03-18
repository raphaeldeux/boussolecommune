#!/usr/bin/env python3
"""
Seed du référentiel COG INSEE (~35 000 communes françaises).

Usage :
    python seed_communes.py

Télécharge les communes depuis l'API geo.api.gouv.fr et les insère en base.
Idempotent : peut être relancé sans effets indésirables.
"""
import sys
import unicodedata
import re
import sqlite3

try:
    import requests
except ImportError:
    print("[ERREUR] Le module 'requests' est requis. Installez-le avec : pip install requests")
    sys.exit(1)

# Charger la config Flask pour obtenir DATABASE_PATH
import os
sys.path.insert(0, os.path.dirname(__file__))
from app.config import DATABASE_PATH

GEO_API_URL = "https://geo.api.gouv.fr/communes"
GEO_API_PARAMS = {
    "fields": "nom,code,codeDepartement,nomDepartement,population",
    "format": "json",
    "geometry": "none",
}
BATCH_SIZE = 500


def normaliser(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s-]", "", s.lower())
    return s.strip()


def slugify(nom: str, dep_code: str) -> str:
    return normaliser(nom).replace(" ", "-") + "-" + dep_code.lower()


def fetch_communes():
    print("[INFO] Téléchargement des communes depuis geo.api.gouv.fr…")
    r = requests.get(GEO_API_URL, params=GEO_API_PARAMS, timeout=60)
    r.raise_for_status()
    data = r.json()
    print(f"[INFO] {len(data)} communes reçues.")
    return data


def seed():
    communes = fetch_communes()

    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    # Vider et réinsérer
    print("[INFO] Insertion en base…")
    conn.execute("DELETE FROM communes")
    conn.commit()

    batch = []
    skipped = 0
    for c in communes:
        code = c.get("code", "")
        nom = c.get("nom", "")
        dep_code = c.get("codeDepartement", "")
        dep_nom = c.get("nomDepartement", "")
        population = c.get("population")

        if not code or not nom or not dep_code:
            skipped += 1
            continue

        nom_normalise = normaliser(nom)
        slug = slugify(nom, dep_code)

        batch.append((code, nom, nom_normalise, dep_code, dep_nom, population, slug))

        if len(batch) >= BATCH_SIZE:
            conn.executemany(
                """INSERT OR REPLACE INTO communes
                   (code_insee, nom, nom_normalise, departement_code, departement_nom, population, slug)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                batch,
            )
            conn.commit()
            batch = []

    if batch:
        conn.executemany(
            """INSERT OR REPLACE INTO communes
               (code_insee, nom, nom_normalise, departement_code, departement_nom, population, slug)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            batch,
        )
        conn.commit()

    nb = conn.execute("SELECT COUNT(*) FROM communes").fetchone()[0]
    print(f"[OK] {nb} communes insérées ({skipped} ignorées).")

    # Index de performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_communes_nom ON communes(nom_normalise)")
    conn.commit()
    print("[OK] Index créé.")
    conn.close()


if __name__ == "__main__":
    seed()
