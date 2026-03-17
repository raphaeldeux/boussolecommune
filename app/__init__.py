import logging
import secrets as _secrets
from datetime import timedelta
from flask import Flask, request, session, abort
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

    flask_env = os.environ.get("FLASK_ENV", "development")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(flask_env == "production"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )

    # Helper CSRF accessible dans tous les templates
    def _csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = _secrets.token_hex(32)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = _csrf_token

    # Vérification CSRF sur tous les POST admin (sauf login géré séparément)
    @app.before_request
    def _check_csrf():
        if request.method == "POST" and request.endpoint and request.endpoint.startswith("admin."):
            if request.endpoint == "admin.login":
                return  # le login n'a pas encore de session CSRF
            form_token = request.form.get("_csrf")
            session_token = session.get("_csrf")
            if not form_token or not session_token or form_token != session_token:
                abort(403)

    from app.database import init_db, get_db
    with app.app_context():
        init_db()
        # Seed automatique au premier démarrage si la table est vide
        conn = get_db()
        nb = conn.execute("SELECT COUNT(*) FROM indicateurs").fetchone()[0]
        conn.close()
        if nb == 0:
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
                from seed import seed
                seed()
            except Exception as e:
                print(f"[ERREUR] Auto-seed échoué : {e}", flush=True)

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
        return str(d)[:10]

    return app
