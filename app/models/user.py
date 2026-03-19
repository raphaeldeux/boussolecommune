from app.database import get_db
from werkzeug.security import generate_password_hash, check_password_hash


def get_all():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, role, actif FROM users ORDER BY role, username"
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(user_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, role, actif FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def get_by_username(username):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND actif = 1", (username,)
        ).fetchone()
    return dict(row) if row else None


def verify_password(username, password):
    user = get_by_username(username)
    if not user:
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def create(username, password, role):
    password_hash = generate_password_hash(password)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role)
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return user_id


def update(user_id, username, role, actif=1, password=None):
    with get_db() as conn:
        if password:
            conn.execute(
                "UPDATE users SET username=?, role=?, actif=?, password_hash=? WHERE id=?",
                (username, role, actif, generate_password_hash(password), user_id)
            )
        else:
            conn.execute(
                "UPDATE users SET username=?, role=?, actif=? WHERE id=?",
                (username, role, actif, user_id)
            )
        conn.commit()


def delete(user_id):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()


def get_villes(user_id):
    """Retourne les villes assignées à un utilisateur."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT v.* FROM villes v
            JOIN user_villes uv ON v.id = uv.ville_id
            WHERE uv.user_id = ? AND v.actif = 1
        """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def set_villes(user_id, ville_ids):
    """Remplace les villes assignées à un utilisateur."""
    with get_db() as conn:
        conn.execute("DELETE FROM user_villes WHERE user_id = ?", (user_id,))
        for vid in ville_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_villes (user_id, ville_id) VALUES (?, ?)",
                (user_id, vid)
            )
        conn.commit()


def count_super_admins():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as nb FROM users WHERE role='super_admin' AND actif=1"
        ).fetchone()
    return row["nb"]
