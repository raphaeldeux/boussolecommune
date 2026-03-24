from app.database import get_db
from werkzeug.security import generate_password_hash, check_password_hash

# Dummy hash used to equalize response time for unknown usernames (prevent enumeration)
_DUMMY_HASH = generate_password_hash("timing-safety-placeholder-boussolecommune")


def get_all():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, role, actif FROM users ORDER BY role, username"
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(user_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, role, actif FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def get_by_username(username):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = %s AND actif = 1", (username,)
        ).fetchone()
    return dict(row) if row else None


def verify_password(username, password):
    user = get_by_username(username)
    if not user:
        # Always run bcrypt to prevent username enumeration via timing
        check_password_hash(_DUMMY_HASH, password)
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def create(username, password, role):
    password_hash = generate_password_hash(password)
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
            (username, password_hash, role)
        )
        user_id = cur.fetchone()["id"]
        conn.commit()
    return user_id


def update(user_id, username, role, actif=1, password=None):
    with get_db() as conn:
        if password:
            conn.execute(
                "UPDATE users SET username=%s, role=%s, actif=%s, password_hash=%s WHERE id=%s",
                (username, role, actif, generate_password_hash(password), user_id)
            )
        else:
            conn.execute(
                "UPDATE users SET username=%s, role=%s, actif=%s WHERE id=%s",
                (username, role, actif, user_id)
            )
        conn.commit()


def delete(user_id):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def get_villes(user_id):
    """Retourne les villes assignées à un utilisateur."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT v.* FROM villes v
            JOIN user_villes uv ON v.id = uv.ville_id
            WHERE uv.user_id = %s AND v.actif = 1
        """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def set_villes(user_id, ville_ids):
    """Remplace les villes assignées à un utilisateur."""
    with get_db() as conn:
        conn.execute("DELETE FROM user_villes WHERE user_id = %s", (user_id,))
        for vid in ville_ids:
            conn.execute(
                "INSERT INTO user_villes (user_id, ville_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, vid)
            )
        conn.commit()


def count_super_admins():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as nb FROM users WHERE role='super_admin' AND actif=1"
        ).fetchone()
    return row["nb"]
