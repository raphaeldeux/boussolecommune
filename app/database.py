import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://boussole:boussole@localhost:5432/boussolecommune"
)


class PgConnection:
    """Thin wrapper around a psycopg2 connection.

    Provides conn.execute() that returns a psycopg2 cursor using
    RealDictCursor so rows behave like dicts.  Supports the context-manager
    protocol: commits on clean exit, rolls back on exception, always closes.
    """

    def __init__(self, connection):
        self._conn = connection

    # ── Context-manager ──────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            try:
                self._conn.rollback()
            except Exception:
                pass
        self._conn.close()
        return False  # do not suppress exceptions

    # ── Delegation ───────────────────────────────────────────────────────

    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, params_list):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.executemany(sql, params_list)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db() -> PgConnection:
    """Return a new PgConnection wrapping a fresh psycopg2 connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return PgConnection(conn)


# ── Helper: check whether a column exists ────────────────────────────────

def _column_exists(conn: PgConnection, table: str, column: str) -> bool:
    row = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    return row is not None


def _table_exists(conn: PgConnection, table: str) -> bool:
    row = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    ).fetchone()
    return row is not None


# ── Schema creation ───────────────────────────────────────────────────────

def init_db():  # noqa: C901
    conn = get_db()

    # Advisory lock — held for the entire init to prevent race conditions
    # between Gunicorn workers starting simultaneously.
    conn.execute("SELECT pg_advisory_lock(42)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS villes (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            population INTEGER,
            actif INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('super_admin','gestionnaire')),
            actif INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_villes (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ville_id INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, ville_id)
        )
    """)

    conn.execute("""
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
            source_type TEXT CHECK(source_type IN ('csv_ofgl','csv_generique','saisie_manuelle','api_macantine','api_rpls','api_cerema')),
            actif INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS banque_references (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            description TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicateur_ville_ref (
            id SERIAL PRIMARY KEY,
            indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
            ville_id INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
            banque_reference_id INTEGER REFERENCES banque_references(id) ON DELETE SET NULL,
            valeur REAL,
            UNIQUE(indicateur_id, ville_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            id SERIAL PRIMARY KEY,
            fichier TEXT,
            thematique TEXT,
            nb_lignes_traitees INTEGER,
            nb_lignes_importees INTEGER,
            nb_erreurs INTEGER,
            rapport TEXT,
            date_import TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            statut TEXT CHECK(statut IN ('succes','partiel','echec'))
        )
    """)

    # Référentiel COG INSEE (~35 000 communes)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS communes (
            code_insee      TEXT PRIMARY KEY,
            nom             TEXT NOT NULL,
            nom_normalise   TEXT NOT NULL,
            departement_code TEXT,
            departement_nom  TEXT,
            population      INTEGER,
            slug            TEXT UNIQUE
        )
    """)

    # Score global dénormalisé pour l'autocomplétion
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores_globaux (
            code_insee  TEXT PRIMARY KEY REFERENCES communes(code_insee) ON DELETE CASCADE,
            score       TEXT CHECK(score IN ('A','B','C','D','E')),
            date_calcul TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Communes mises en avant sur la page d'accueil
    conn.execute("""
        CREATE TABLE IF NOT EXISTS communes_vedette (
            id          SERIAL PRIMARY KEY,
            code_insee  TEXT REFERENCES communes(code_insee) ON DELETE CASCADE,
            ordre       INTEGER DEFAULT 0,
            actif       INTEGER DEFAULT 1
        )
    """)

    conn.commit()

    # Migration : ajouter api_cerema au CHECK source_type si absent
    row = conn.execute(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_name = 'indicateurs' AND constraint_type = 'CHECK' "
        "AND constraint_name = 'indicateurs_source_type_check'"
    ).fetchone()
    if row:
        defn = conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'indicateurs_source_type_check'"
        ).fetchone()
        if defn and "api_cerema" not in defn["pg_get_constraintdef"]:
            conn.execute("ALTER TABLE indicateurs DROP CONSTRAINT indicateurs_source_type_check")
            conn.execute(
                "ALTER TABLE indicateurs ADD CONSTRAINT indicateurs_source_type_check "
                "CHECK(source_type IN ('csv_ofgl','csv_generique','saisie_manuelle',"
                "'api_macantine','api_rpls','api_cerema'))"
            )
            conn.commit()

    # Seed ville Sautron par défaut
    conn.execute(
        "INSERT INTO villes (id, nom, slug, population) VALUES (1, 'Sautron', 'sautron', 8600) "
        "ON CONFLICT DO NOTHING"
    )
    conn.commit()

    # Migration: ajouter nb_conseillers à villes
    if not _column_exists(conn, 'villes', 'nb_conseillers'):
        conn.execute("ALTER TABLE villes ADD COLUMN nb_conseillers INTEGER DEFAULT NULL")
        conn.commit()

    # Migration: ajouter code_insee à villes (US-001)
    if not _column_exists(conn, 'villes', 'code_insee'):
        try:
            conn.execute("ALTER TABLE villes ADD COLUMN code_insee TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # Index perf pour l'autocomplétion (US-001)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_communes_nom ON communes(nom_normalise)")
    conn.commit()

    # Migration: ajouter colonne format_csv à imports si absente (US10)
    if not _column_exists(conn, 'imports', 'format_csv'):
        try:
            conn.execute("ALTER TABLE imports ADD COLUMN format_csv TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # Créer la table donnees si elle n'existe pas (avec ville_id inclus dès le départ)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS donnees (
            id SERIAL PRIMARY KEY,
            indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
            ville_id INTEGER NOT NULL DEFAULT 1,
            annee INTEGER NOT NULL,
            valeur REAL,
            source TEXT,
            commentaire TEXT,
            date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            mode_saisie TEXT CHECK(mode_saisie IN ('csv', 'manuel', 'api')),
            UNIQUE(indicateur_id, annee, ville_id)
        )
    """)
    conn.commit()

    # Créer la table interpretations si elle n'existe pas (avec ville_id)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interpretations (
            id SERIAL PRIMARY KEY,
            indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
            ville_id INTEGER NOT NULL DEFAULT 1,
            annee INTEGER NOT NULL,
            score TEXT CHECK(score IN ('A','B','C','D','E')),
            phrase_courte TEXT,
            phrase_longue TEXT,
            date_generation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(indicateur_id, annee, ville_id)
        )
    """)
    conn.commit()

    # Créer la table pyramide_ages si elle n'existe pas
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pyramide_ages (
            id SERIAL PRIMARY KEY,
            ville_id INTEGER NOT NULL DEFAULT 1,
            annee INTEGER NOT NULL,
            tranche TEXT NOT NULL,
            ordre INTEGER NOT NULL,
            hommes INTEGER NOT NULL DEFAULT 0,
            femmes INTEGER NOT NULL DEFAULT 0,
            UNIQUE(ville_id, annee, tranche)
        )
    """)
    conn.commit()

    # Créer la table subventions si elle n'existe pas
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subventions (
            id SERIAL PRIMARY KEY,
            ville_id INTEGER NOT NULL DEFAULT 1,
            annee INTEGER NOT NULL,
            nom_beneficiaire TEXT NOT NULL,
            domaine TEXT NOT NULL DEFAULT 'autre',
            montant REAL NOT NULL,
            commentaire TEXT,
            date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Migration: ajouter colonne thematique à subventions
    if not _column_exists(conn, 'subventions', 'thematique'):
        try:
            conn.execute(
                "ALTER TABLE subventions ADD COLUMN thematique TEXT NOT NULL DEFAULT 'lien_social'"
            )
            conn.commit()
        except Exception:
            conn.rollback()

    # Migration banque de références : nouvelle table refs_banque + colonnes indicateur_ville_ref
    if not _table_exists(conn, 'refs_banque'):
        conn.execute("""
            CREATE TABLE refs_banque (
                id               SERIAL PRIMARY KEY,
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
            )
        """)
        conn.commit()

    for col, defn in [
        ('ref_banque_id',       'INTEGER REFERENCES refs_banque(id) ON DELETE SET NULL'),
        ('valeur_locale',       'REAL'),
        ('justification_locale', 'TEXT'),
    ]:
        if not _column_exists(conn, 'indicateur_ville_ref', col):
            try:
                conn.execute(f"ALTER TABLE indicateur_ville_ref ADD COLUMN {col} {defn}")
                conn.commit()
            except Exception:
                conn.rollback()

    # Migrate old valeur → valeur_locale when not yet migrated
    conn.execute("""
        UPDATE indicateur_ville_ref
        SET valeur_locale = valeur
        WHERE valeur IS NOT NULL
          AND valeur_locale IS NULL
          AND ref_banque_id IS NULL
    """)
    conn.commit()

    # Seed indicateurs de base
    for row in [
        ('portrait_population',    'portrait', 'Population',                'Population municipale INSEE',       'hab.',  'neutre', 'saisie_manuelle', 1),
        ('portrait_age_median',    'portrait', 'Âge médian',                'Âge médian de la population INSEE', 'ans',   'neutre', 'saisie_manuelle', 1),
        ('portrait_revenu_median', 'portrait', 'Revenu médian des ménages', 'Niveau de vie médian INSEE',        '€/an',  'neutre', 'saisie_manuelle', 1),
        ('portrait_chomage',       'portrait', 'Taux de chômage',           'Taux de chômage localisé INSEE',    '%',     'bas',    'saisie_manuelle', 1),
    ]:
        conn.execute("""
            INSERT INTO indicateurs
                (id, thematique, libelle_citoyen, libelle_technique, unite, sens_positif, source_type, actif)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, row)
    conn.commit()

    # Table conseils municipaux (US-T1)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conseils (
            id           SERIAL PRIMARY KEY,
            ville_id     INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
            titre        TEXT NOT NULL,
            date_conseil DATE NOT NULL,
            fichier_pdf  TEXT,
            resume_citoyen TEXT,
            publie       BOOLEAN NOT NULL DEFAULT FALSE,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    if not _column_exists(conn, "conseils", "statut_resume"):
        conn.execute(
            "ALTER TABLE conseils ADD COLUMN statut_resume TEXT NOT NULL DEFAULT 'idle'"
        )
        conn.commit()

    # Reset any rows stuck in 'en_cours' from a previous interrupted generation
    conn.execute(
        "UPDATE conseils SET statut_resume = 'idle' WHERE statut_resume = 'en_cours'"
    )
    conn.commit()

    if not _column_exists(conn, "conseils", "resume_structure"):
        conn.execute(
            "ALTER TABLE conseils ADD COLUMN resume_structure TEXT DEFAULT NULL"
        )
        conn.commit()

    if not _column_exists(conn, "conseils", "progres_resume"):
        conn.execute(
            "ALTER TABLE conseils ADD COLUMN progres_resume INTEGER DEFAULT NULL"
        )
        conn.commit()

    if not _column_exists(conn, "conseils", "message_resume"):
        conn.execute(
            "ALTER TABLE conseils ADD COLUMN message_resume TEXT DEFAULT NULL"
        )
        conn.commit()

    if not _column_exists(conn, "conseils", "type_conseil"):
        conn.execute(
            "ALTER TABLE conseils ADD COLUMN type_conseil TEXT NOT NULL DEFAULT 'municipal'"
        )
        conn.commit()

    # Table documents publics (US-T7)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id           SERIAL PRIMARY KEY,
            ville_id     INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
            titre        TEXT NOT NULL,
            categorie    TEXT NOT NULL DEFAULT 'autre',
            fichier      TEXT,
            publie       BOOLEAN NOT NULL DEFAULT FALSE,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    conn.close()
