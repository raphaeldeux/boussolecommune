from functools import wraps
from flask import session, redirect, url_for, flash
from app.config import ADMIN_PASSWORD


def check_password(password):
    return password == ADMIN_PASSWORD


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated
