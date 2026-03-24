import logging
import secrets as _secrets
from datetime import timedelta
from flask import Flask, request, session, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


def create_app():
    app = Flask(__name__, template_folder="templates")
    flask_env = os.environ.get("FLASK_ENV", "development")
    secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
    if flask_env == "production" and secret_key == "dev-secret-key":
        raise RuntimeError(
            "SECRET_KEY non configurée : définissez la variable d'environnement "
            "SECRET_KEY avec une valeur aléatoire forte avant de lancer en production."
        )
    app.secret_key = secret_key
    # Fait confiance à 1 niveau de proxy (nginx) pour X-Forwarded-For / X-Forwarded-Proto
    # → request.remote_addr retourne l'IP réelle du client (utilisé par le rate limiting)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(flask_env == "production"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 Mo max par upload
    )

    # Helper CSRF accessible dans tous les templates
    def _csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = _secrets.token_hex(32)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = _csrf_token

    @app.template_filter("format_delib_desc")
    def format_delib_desc(text):
        """Transforme une description IA en HTML lisible.
        Si un paragraphe contient plusieurs montants séparés par des virgules,
        le convertit en tableau label/montant avec total."""
        import re
        if not text:
            return ""

        # Extrait les items "MONTANT € [HT/TTC] (libellé)"
        item_re = re.compile(
            r'([\d\s\u202f]+(?:[,\.]\d+)?\s*€\s*(?:HT|TTC)?)\s*\(([^)]+)\)'
        )

        def parse_amount(s):
            """Convertit une chaîne montant en float."""
            clean = re.sub(r'[^\d,\.]', '', s)
            # Gère virgule décimale (651,17) vs séparateur milliers (1.000)
            if ',' in clean and '.' in clean:
                clean = clean.replace('.', '').replace(',', '.')
            elif ',' in clean:
                # Virgule = décimale si < 3 chiffres après, sinon milliers
                parts_c = clean.split(',')
                if len(parts_c[-1]) <= 2:
                    clean = clean.replace(',', '.')
                else:
                    clean = clean.replace(',', '')
            try:
                return float(clean)
            except ValueError:
                return 0.0

        parts = []
        for para in text.split("\n"):
            para = para.strip()
            if not para:
                continue
            matches = item_re.findall(para)
            if len(matches) >= 2:
                rows = ""
                total = 0.0
                for montant_str, label in matches:
                    montant_str = montant_str.strip()
                    label = label.strip().capitalize()
                    total += parse_amount(montant_str)
                    rows += (f"<tr>"
                             f"<td class='py-0.5 pr-3 text-gray-700'>{label}</td>"
                             f"<td class='py-0.5 font-semibold text-emerald-700 text-right whitespace-nowrap'>{montant_str}</td>"
                             f"</tr>")
                if total:
                    total_fmt = f"{total:,.2f}".replace(",", "\u202f").replace(".", ",") + " €"
                    rows += (f"<tr class='border-t border-emerald-200'>"
                             f"<td class='pt-1 pr-3 font-bold text-emerald-800'>Total</td>"
                             f"<td class='pt-1 font-bold text-emerald-800 text-right whitespace-nowrap'>{total_fmt}</td>"
                             f"</tr>")
                parts.append(f"<table class='w-full text-xs mt-1'>{rows}</table>")
            else:
                parts.append(f"<p>{para}</p>")
        return "\n".join(parts)

    @app.template_filter("date_fr")
    def date_fr(value):
        """Formate une date en JJ/MM/AAAA."""
        if not value:
            return ""
        import datetime
        if isinstance(value, str):
            try:
                value = datetime.date.fromisoformat(value)
            except ValueError:
                return value
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.strftime("%d/%m/%Y")
        return str(value)

    # Vérification CSRF sur tous les POST admin (sauf login)
    @app.before_request
    def _check_csrf():
        if request.method == "POST" and request.endpoint and request.endpoint.startswith("admin."):
            if request.endpoint == "admin.login":
                return
            form_token = request.form.get("_csrf")
            session_token = session.get("_csrf")
            if not form_token or not session_token or form_token != session_token:
                abort(403)

    from app.database import init_db, get_db
    with app.app_context():
        init_db()

        # Seed auto des indicateurs si table vide
        conn = get_db()
        nb = conn.execute("SELECT COUNT(*) AS nb FROM indicateurs").fetchone()["nb"]
        conn.close()
        if nb == 0:
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
                from seed import seed
                seed()
            except Exception as e:
                print(f"[ERREUR] Auto-seed échoué : {e}", flush=True)

        # Sync villes.code_insee depuis communes (après seed_communes)
        conn = get_db()
        conn.execute("""
            UPDATE villes SET code_insee = (
                SELECT c.code_insee FROM communes c
                WHERE REPLACE(c.nom_normalise, ' ', '-') = villes.slug
                LIMIT 1
            )
            WHERE code_insee IS NULL
              AND EXISTS (SELECT 1 FROM communes LIMIT 1)
        """)
        conn.commit()
        conn.close()

        # Créer le super-admin par défaut si aucun utilisateur n'existe
        conn = get_db()
        nb_users = conn.execute("SELECT COUNT(*) AS nb FROM users").fetchone()["nb"]
        conn.close()
        if nb_users == 0:
            from app.config import ADMIN_USERNAME, ADMIN_PASSWORD
            if flask_env == "production" and ADMIN_PASSWORD == "admin":
                raise RuntimeError(
                    "ADMIN_PASSWORD='admin' n'est pas acceptable en production. "
                    "Définissez la variable d'environnement ADMIN_PASSWORD."
                )
            from app.models.user import create as create_user
            create_user(ADMIN_USERNAME, ADMIN_PASSWORD, "super_admin")
            print(f"[INFO] Super-admin créé : {ADMIN_USERNAME}", flush=True)

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    logging.basicConfig(level=logging.INFO)

    from app.routes.public import bp as public_bp
    from app.routes.admin import bp as admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    @app.template_filter("format_valeur")
    def format_valeur(v):
        if v is None:
            return "—"
        if isinstance(v, float) and v == int(v):
            return f"{int(v):,}".replace(",", "\u202f")
        if isinstance(v, (int, float)):
            return f"{v:,.2f}".replace(",", "\u202f").replace(".", ",")
        return str(v)

    @app.template_filter("format_date")
    def format_date(d):
        if not d:
            return "—"
        import datetime
        if isinstance(d, str):
            try:
                d = datetime.date.fromisoformat(str(d)[:10])
            except ValueError:
                return str(d)[:10]
        if isinstance(d, (datetime.date, datetime.datetime)):
            return d.strftime("%d/%m/%Y")
        return str(d)[:10]

    @app.template_filter("from_json")
    def from_json_filter(s):
        import json
        if not s:
            return []
        try:
            return json.loads(s)
        except Exception:
            return []

    return app
