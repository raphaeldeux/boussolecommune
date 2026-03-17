import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "data", "communesante.db"))
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
