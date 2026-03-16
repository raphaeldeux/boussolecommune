from flask import Flask
from dotenv import load_dotenv
import os

load_dotenv()


def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

    from app.database import init_db, get_db
    with app.app_context():
        init_db()
        # Seed automatique au premier démarrage si la table est vide
        conn = get_db()
        nb = conn.execute("SELECT COUNT(*) FROM indicateurs").fetchone()[0]
        conn.close()
        if nb == 0:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from seed import seed
            seed()

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
