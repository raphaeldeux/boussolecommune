import time
from functools import wraps
from flask import session, redirect, url_for, flash

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


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("admin.login"))
        if session.get("user_role") != "super_admin":
            flash("Accès réservé aux super-administrateurs.", "danger")
            return redirect(url_for("admin.dashboard"))
        return f(*args, **kwargs)
    return decorated


def can_modify_ville(ville_id):
    """Retourne True si l'utilisateur connecté peut modifier la ville donnée."""
    if session.get('user_role') == 'super_admin':
        return True
    return session.get('admin_ville_id') == ville_id
