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
        CREATE TABLE IF NOT EXISTS villes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            population INTEGER,
            actif INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('super_admin','gestionnaire')),
            actif INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS user_villes (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ville_id INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, ville_id)
        );

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
            annee_reference INTEGER,
            description TEXT,
            source_type TEXT CHECK(source_type IN ('csv_ofgl','csv_generique','saisie_manuelle')),
            actif INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS banque_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS indicateur_ville_ref (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
            ville_id INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
            banque_reference_id INTEGER REFERENCES banque_references(id) ON DELETE SET NULL,
            valeur REAL,
            UNIQUE(indicateur_id, ville_id)
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

    # Seed ville Sautron par défaut
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO villes (id, nom, slug, population) VALUES (1, 'Sautron', 'sautron', 8600)"
    )
    conn.commit()
    conn.close()

    # Migration: ajouter colonne format_csv à imports si absente (US10)
    conn = get_db()
    import_cols = [r[1] for r in conn.execute("PRAGMA table_info(imports)").fetchall()]
    if 'format_csv' not in import_cols:
        try:
            conn.execute("ALTER TABLE imports ADD COLUMN format_csv TEXT")
            conn.commit()
        except Exception:
            pass
    conn.close()

    # Migration: recréer donnees avec ville_id si nécessaire
    conn = get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(donnees)").fetchall()]
    if 'ville_id' not in cols:
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS donnees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
                    ville_id INTEGER NOT NULL DEFAULT 1,
                    annee INTEGER NOT NULL,
                    valeur REAL,
                    source TEXT,
                    commentaire TEXT,
                    date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    mode_saisie TEXT CHECK(mode_saisie IN ('csv', 'manuel')),
                    UNIQUE(indicateur_id, annee, ville_id)
                );
            """)
            conn.commit()
        except Exception:
            pass
    conn.close()

    # Migration: recréer donnees_old → donnees si l'ancienne table existait sans ville_id
    conn = get_db()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if 'donnees' not in tables:
        # Devrait pas arriver, mais sécurité
        conn.executescript("""
            CREATE TABLE donnees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                valeur REAL,
                source TEXT,
                commentaire TEXT,
                date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mode_saisie TEXT CHECK(mode_saisie IN ('csv', 'manuel')),
                UNIQUE(indicateur_id, annee, ville_id)
            );
        """)
        conn.commit()
    conn.close()

    # Vérifier si donnees a ville_id, sinon migrer depuis l'ancienne structure
    conn = get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(donnees)").fetchall()]
    if 'ville_id' not in cols:
        conn.executescript("""
            ALTER TABLE donnees RENAME TO donnees_backup;
            CREATE TABLE donnees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                valeur REAL,
                source TEXT,
                commentaire TEXT,
                date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mode_saisie TEXT CHECK(mode_saisie IN ('csv', 'manuel')),
                UNIQUE(indicateur_id, annee, ville_id)
            );
            INSERT INTO donnees (id, indicateur_id, ville_id, annee, valeur, source, commentaire, date_saisie, mode_saisie)
            SELECT id, indicateur_id, 1, annee, valeur, source, commentaire, date_saisie, mode_saisie FROM donnees_backup;
            DROP TABLE donnees_backup;
        """)
        conn.commit()
    conn.close()

    # Migration: interpretations avec ville_id
    conn = get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(interpretations)").fetchall()]
    if 'interpretations' not in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
        conn.executescript("""
            CREATE TABLE interpretations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                score TEXT CHECK(score IN ('A','B','C','D','E')),
                phrase_courte TEXT,
                phrase_longue TEXT,
                date_generation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(indicateur_id, annee, ville_id)
            );
        """)
        conn.commit()
    elif 'ville_id' not in cols:
        conn.executescript("""
            ALTER TABLE interpretations RENAME TO interpretations_backup;
            CREATE TABLE interpretations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                score TEXT CHECK(score IN ('A','B','C','D','E')),
                phrase_courte TEXT,
                phrase_longue TEXT,
                date_generation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(indicateur_id, annee, ville_id)
            );
            INSERT INTO interpretations (id, indicateur_id, ville_id, annee, score, phrase_courte, phrase_longue, date_generation)
            SELECT id, indicateur_id, 1, annee, score, phrase_courte, phrase_longue, date_generation FROM interpretations_backup;
            DROP TABLE interpretations_backup;
        """)
        conn.commit()
    conn.close()

    # Migration: pyramide_ages avec ville_id
    conn = get_db()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pyramide_ages)").fetchall()] if 'pyramide_ages' in tables else []
    if 'pyramide_ages' not in tables:
        conn.executescript("""
            CREATE TABLE pyramide_ages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                tranche TEXT NOT NULL,
                ordre INTEGER NOT NULL,
                hommes INTEGER NOT NULL DEFAULT 0,
                femmes INTEGER NOT NULL DEFAULT 0,
                UNIQUE(ville_id, annee, tranche)
            );
        """)
        conn.commit()
    elif 'ville_id' not in cols:
        conn.executescript("""
            ALTER TABLE pyramide_ages RENAME TO pyramide_ages_backup;
            CREATE TABLE pyramide_ages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                tranche TEXT NOT NULL,
                ordre INTEGER NOT NULL,
                hommes INTEGER NOT NULL DEFAULT 0,
                femmes INTEGER NOT NULL DEFAULT 0,
                UNIQUE(ville_id, annee, tranche)
            );
            INSERT INTO pyramide_ages (id, ville_id, annee, tranche, ordre, hommes, femmes)
            SELECT id, 1, annee, tranche, ordre, hommes, femmes FROM pyramide_ages_backup;
            DROP TABLE pyramide_ages_backup;
        """)
        conn.commit()
    conn.close()

    # Migration: subventions avec ville_id
    conn = get_db()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    cols = [r[1] for r in conn.execute("PRAGMA table_info(subventions)").fetchall()] if 'subventions' in tables else []
    if 'subventions' not in tables:
        conn.executescript("""
            CREATE TABLE subventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                nom_beneficiaire TEXT NOT NULL,
                domaine TEXT NOT NULL DEFAULT 'autre',
                montant REAL NOT NULL,
                commentaire TEXT,
                date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    elif 'ville_id' not in cols:
        conn.executescript("""
            ALTER TABLE subventions RENAME TO subventions_backup;
            CREATE TABLE subventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ville_id INTEGER NOT NULL DEFAULT 1,
                annee INTEGER NOT NULL,
                nom_beneficiaire TEXT NOT NULL,
                domaine TEXT NOT NULL DEFAULT 'autre',
                montant REAL NOT NULL,
                commentaire TEXT,
                date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO subventions (id, ville_id, annee, nom_beneficiaire, domaine, montant, commentaire, date_saisie)
            SELECT id, 1, annee, nom_beneficiaire, domaine, montant, commentaire, date_saisie FROM subventions_backup;
            DROP TABLE subventions_backup;
        """)
        conn.commit()
    conn.close()

    # Seed indicateurs de base
    conn = get_db()
    conn.executescript("""
        INSERT OR IGNORE INTO indicateurs
            (id, thematique, libelle_citoyen, libelle_technique, unite, sens_positif, source_type, actif)
        VALUES
            ('portrait_population',    'portrait', 'Population',                  'Population municipale INSEE',         'hab.',  'neutre', 'saisie_manuelle', 1),
            ('portrait_age_median',    'portrait', 'Âge médian',                  'Âge médian de la population INSEE',   'ans',   'neutre', 'saisie_manuelle', 1),
            ('portrait_revenu_median', 'portrait', 'Revenu médian des ménages',   'Niveau de vie médian INSEE',          '€/an',  'neutre', 'saisie_manuelle', 1),
            ('portrait_chomage',       'portrait', 'Taux de chômage',             'Taux de chômage localisé INSEE',      '%',     'bas',    'saisie_manuelle', 1);
    """)
    conn.commit()
    conn.close()
