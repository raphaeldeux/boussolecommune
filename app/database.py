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

        -- Référentiel COG INSEE (~35 000 communes)
        CREATE TABLE IF NOT EXISTS communes (
            code_insee      TEXT PRIMARY KEY,
            nom             TEXT NOT NULL,
            nom_normalise   TEXT NOT NULL,
            departement_code TEXT,
            departement_nom  TEXT,
            population      INTEGER,
            slug            TEXT UNIQUE
        );

        -- Score global dénormalisé pour l'autocomplétion
        CREATE TABLE IF NOT EXISTS scores_globaux (
            code_insee  TEXT PRIMARY KEY REFERENCES communes(code_insee) ON DELETE CASCADE,
            score       TEXT CHECK(score IN ('A','B','C','D','E')),
            date_calcul TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Communes mises en avant sur la page d'accueil
        CREATE TABLE IF NOT EXISTS communes_vedette (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code_insee  TEXT REFERENCES communes(code_insee) ON DELETE CASCADE,
            ordre       INTEGER DEFAULT 0,
            actif       INTEGER DEFAULT 1
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

    # Migration: ajouter code_insee à villes (US-001)
    conn = get_db()
    villes_cols = [r[1] for r in conn.execute("PRAGMA table_info(villes)").fetchall()]
    if 'code_insee' not in villes_cols:
        try:
            conn.execute("ALTER TABLE villes ADD COLUMN code_insee TEXT")
            conn.commit()
        except Exception:
            pass
    conn.close()

    # Index perf pour l'autocomplétion (US-001)
    conn = get_db()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_communes_nom ON communes(nom_normalise)")
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

    # Migration banque de références : nouvelle table refs_banque + colonnes indicateur_ville_ref
    conn = get_db()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if 'refs_banque' not in tables:
        conn.executescript("""
            CREATE TABLE refs_banque (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                indicateur_id    TEXT    NOT NULL REFERENCES indicateurs(id),
                strate_id        INTEGER NOT NULL REFERENCES banque_references(id) ON DELETE CASCADE,
                valeur           REAL    NOT NULL,
                source           TEXT    NOT NULL,
                annee            INTEGER,
                statut           TEXT    NOT NULL DEFAULT 'en_attente'
                                 CHECK(statut IN ('en_attente','valide','rejete')),
                propose_par      INTEGER REFERENCES users(id) ON DELETE SET NULL,
                valide_par       INTEGER REFERENCES users(id) ON DELETE SET NULL,
                date_proposition TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_validation  TIMESTAMP,
                commentaire_rejet TEXT,
                UNIQUE(indicateur_id, strate_id)
            );
        """)
        conn.commit()
    ivr_cols = [r[1] for r in conn.execute("PRAGMA table_info(indicateur_ville_ref)").fetchall()]
    for col, defn in [
        ('ref_banque_id',       'INTEGER REFERENCES refs_banque(id) ON DELETE SET NULL'),
        ('valeur_locale',       'REAL'),
        ('justification_locale','TEXT'),
    ]:
        if col not in ivr_cols:
            try:
                conn.execute(f"ALTER TABLE indicateur_ville_ref ADD COLUMN {col} {defn}")
                conn.commit()
            except Exception:
                pass
    # Migrate old valeur → valeur_locale when not yet migrated
    conn.execute("""
        UPDATE indicateur_ville_ref
        SET valeur_locale = valeur
        WHERE valeur IS NOT NULL
          AND valeur_locale IS NULL
          AND ref_banque_id IS NULL
    """)
    conn.commit()
    conn.close()

    # Migration: élargir le CHECK mode_saisie pour inclure 'api'
    conn = get_db()
    try:
        # SQLite ne supporte pas ALTER TABLE pour modifier une contrainte CHECK.
        # On recrée la table donnees avec le nouveau CHECK.
        check_val = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='donnees'"
        ).fetchone()
        if check_val and "'api'" not in check_val[0]:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS donnees_migration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
                    ville_id INTEGER NOT NULL DEFAULT 1,
                    annee INTEGER NOT NULL,
                    valeur REAL,
                    source TEXT,
                    commentaire TEXT,
                    date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    mode_saisie TEXT CHECK(mode_saisie IN ('csv', 'manuel', 'api')),
                    UNIQUE(indicateur_id, annee, ville_id)
                );
                INSERT OR IGNORE INTO donnees_migration
                    SELECT id, indicateur_id, ville_id, annee, valeur, source, commentaire, date_saisie, mode_saisie
                    FROM donnees;
                DROP TABLE donnees;
                ALTER TABLE donnees_migration RENAME TO donnees;
            """)
            conn.commit()
    except Exception:
        pass
    conn.close()

    # Migration: élargir le CHECK source_type pour inclure 'api_macantine'
    conn = get_db()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    # Cas de reprise : migration interrompue laissant indicateurs_migration sans indicateurs
    if "indicateurs_migration" in tables and "indicateurs" not in tables:
        conn.execute("ALTER TABLE indicateurs_migration RENAME TO indicateurs")
        conn.commit()
        tables.add("indicateurs")
        tables.discard("indicateurs_migration")

    if "indicateurs" in tables:
        check_val = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='indicateurs'"
        ).fetchone()
        if check_val and "'api_macantine'" not in check_val[0]:
            # SQLite ne permet pas ALTER TABLE pour modifier un CHECK.
            # On désactive les FK le temps de la migration pour pouvoir
            # dropper la table référencée par d'autres tables.
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE IF EXISTS indicateurs_migration")
            conn.execute("""
                CREATE TABLE indicateurs_migration (
                    id TEXT PRIMARY KEY,
                    thematique TEXT NOT NULL,
                    libelle_citoyen TEXT,
                    libelle_technique TEXT,
                    unite TEXT,
                    sens_positif TEXT CHECK(sens_positif IN ('haut','bas','neutre')) DEFAULT 'neutre',
                    seuil_vert REAL,
                    seuil_orange REAL,
                    seuil_rouge REAL,
                    valeur_reference REAL,
                    libelle_reference TEXT,
                    annee_reference INTEGER,
                    description TEXT,
                    source_type TEXT,
                    actif INTEGER DEFAULT 1
                )
            """)
            conn.execute("INSERT INTO indicateurs_migration SELECT * FROM indicateurs")
            # Normalise les valeurs inconnues vers NULL
            conn.execute("""
                UPDATE indicateurs_migration
                SET source_type = NULL
                WHERE source_type NOT IN ('csv_ofgl','csv_generique','saisie_manuelle','api_macantine')
            """)
            conn.execute("DROP TABLE indicateurs")
            conn.execute("ALTER TABLE indicateurs_migration RENAME TO indicateurs")
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON")
    conn.close()

    # Migration: ajouter colonne thematique à subventions
    conn = get_db()
    sub_cols = [r[1] for r in conn.execute("PRAGMA table_info(subventions)").fetchall()]
    if "thematique" not in sub_cols:
        try:
            conn.execute("ALTER TABLE subventions ADD COLUMN thematique TEXT NOT NULL DEFAULT 'lien_social'")
            conn.commit()
        except Exception:
            pass
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
