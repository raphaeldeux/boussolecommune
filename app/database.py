import sqlite3
import os
from app.config import DATABASE_PATH


def get_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS indicateurs (
            id TEXT PRIMARY KEY,
            thematique TEXT NOT NULL,
            libelle_citoyen TEXT NOT NULL,
            libelle_technique TEXT,
            unite TEXT,
            sens_positif TEXT CHECK(sens_positif IN ('haut','bas','neutre')),
            seuil_vert REAL,
            seuil_orange REAL,
            seuil_rouge REAL,
            valeur_reference REAL,
            libelle_reference TEXT,
            description TEXT,
            source_type TEXT CHECK(source_type IN ('csv_ofgl','csv_generique','saisie_manuelle')),
            actif INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS donnees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
            annee INTEGER NOT NULL,
            valeur REAL,
            source TEXT,
            commentaire TEXT,
            date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            mode_saisie TEXT CHECK(mode_saisie IN ('csv', 'manuel')),
            UNIQUE(indicateur_id, annee)
        );

        CREATE TABLE IF NOT EXISTS interpretations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
            annee INTEGER NOT NULL,
            score TEXT CHECK(score IN ('A','B','C','D','E')),
            phrase_courte TEXT,
            phrase_longue TEXT,
            date_generation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(indicateur_id, annee)
        );

        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fichier TEXT,
            thematique TEXT,
            nb_lignes_traitees INTEGER,
            nb_lignes_importees INTEGER,
            nb_erreurs INTEGER,
            rapport TEXT,
            date_import TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            statut TEXT CHECK(statut IN ('succes','partiel','echec'))
        );
    """)
    conn.commit()
    conn.close()
