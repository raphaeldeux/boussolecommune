import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "data", "boussolecommune.db"))
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
