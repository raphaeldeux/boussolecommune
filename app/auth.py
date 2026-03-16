import time
from functools import wraps
from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from app.config import ADMIN_PASSWORD

# Hash calculé une seule fois au démarrage (sel aléatoire intégré)
_HASHED_PASSWORD = generate_password_hash(ADMIN_PASSWORD)

# Rate limiting en mémoire : { ip: [timestamp, ...] }
_LOGIN_ATTEMPTS: dict = {}
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 900  # 15 min


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _LOGIN_ATTEMPTS.get(ip, []) if now - t < _WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= _MAX_ATTEMPTS


def record_attempt(ip: str) -> None:
    _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())


def check_password(password: str) -> bool:
    return check_password_hash(_HASHED_PASSWORD, password)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated
