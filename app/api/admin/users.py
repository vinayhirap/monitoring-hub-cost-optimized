# app/api/admin/users.py
from fastapi import APIRouter, HTTPException, Body
from app.db import get_connection
import datetime
import json
import hashlib

router = APIRouter(prefix="/api/users", tags=["Users"])


def _hash_password(password: str) -> str:
    try:
        from passlib.context import CryptContext
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return ctx.hash(password)
    except ImportError:
        return hashlib.sha256(password.encode()).hexdigest()


def _serialize(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj


def _write_audit(actor: str, action: str, detail: str, role: str = "ADMIN"):
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        payload = json.dumps({"detail": detail, "role": role})
        cursor.execute(
            "INSERT INTO audit_logs (actor, action, payload) VALUES (%s, %s, %s)",
            (actor, action, payload)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Audit log write error: {e}")


def _require_admin(user_id: int, conn):
    """Raise 403 if user_id is not an admin."""
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    if not row or row["role"].lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("")
def list_users():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at ASC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [_serialize(r) for r in rows]


@router.post("")
def create_user(payload: dict = Body(...)):
    username   = (payload.get("username") or "").strip()
    password   = (payload.get("password") or "").strip()
    role       = (payload.get("role") or "viewer").strip().lower()
    actor_name = payload.get("actor", "admin")

    if not username:
        raise HTTPException(status_code=400, detail="username required")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="password min 6 characters")
    if role not in ["admin", "editor", "viewer"]:
        raise HTTPException(status_code=400, detail="role must be admin, editor, or viewer")

    pw_hash = _hash_password(password)
    conn    = get_connection()
    cursor  = conn.cursor()

    cursor.execute("SHOW COLUMNS FROM users LIKE 'password%'")
    col    = cursor.fetchone()
    pw_col = col[0] if col else "password_hash"

    try:
        cursor.execute(
            f"INSERT INTO users (username, {pw_col}, role) VALUES (%s, %s, %s)",
            (username, pw_hash, role)
        )
        conn.commit()
        new_id = cursor.lastrowid
    except Exception as e:
        if "Duplicate" in str(e) or "1062" in str(e):
            raise HTTPException(status_code=409, detail=f"User '{username}' already exists")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

    _write_audit(actor=actor_name, action="User created", detail=f"{username} added as {role.upper()}")
    return {"status": "created", "id": new_id, "username": username, "role": role}


@router.patch("/{user_id}/role")
def update_role(user_id: int, payload: dict = Body(...)):
    new_role    = (payload.get("role") or "").strip().lower()
    actor_id    = payload.get("actor_id")   # DB id of the user making the request
    actor_name  = payload.get("actor", "admin")

    if new_role not in ["admin", "editor", "viewer"]:
        raise HTTPException(status_code=400, detail="role must be admin, editor, or viewer")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Guard 1 — actor must be admin
    if actor_id:
        cursor.execute("SELECT role FROM users WHERE id = %s", (actor_id,))
        actor_row = cursor.fetchone()
        if not actor_row or actor_row["role"].lower() != "admin":
            cursor.close()
            conn.close()
            raise HTTPException(status_code=403, detail="Admin access required")

    # Guard 2 — cannot change own role
    if actor_id and int(actor_id) == user_id:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=403, detail="Cannot change your own role")

    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    cursor.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    _write_audit(actor=actor_name, action="Role changed", detail=f"{user['username']} → {new_role.upper()}")
    return {"status": "updated", "id": user_id, "role": new_role}


@router.patch("/{user_id}/accounts")
def update_account_access(user_id: int, payload: dict = Body(...)):
    account_ids = payload.get("account_ids", [])
    actor_id    = payload.get("actor_id")
    actor_name  = payload.get("actor", "admin")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Guard — actor must be admin
    if actor_id:
        cursor.execute("SELECT role FROM users WHERE id = %s", (actor_id,))
        actor_row = cursor.fetchone()
        if not actor_row or actor_row["role"].lower() != "admin":
            cursor.close()
            conn.close()
            raise HTTPException(status_code=403, detail="Admin access required")

    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    try:
        cursor.execute("DELETE FROM user_account_access WHERE user_id = %s", (user_id,))
        for acc_id in account_ids:
            cursor.execute(
                "INSERT IGNORE INTO user_account_access (user_id, aws_account_id) VALUES (%s, %s)",
                (user_id, acc_id)
            )
        conn.commit()
    except Exception:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_account_access (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                aws_account_id BIGINT NOT NULL,
                UNIQUE KEY uniq_user_account (user_id, aws_account_id)
            )
        """)
        conn.commit()
        for acc_id in account_ids:
            cursor.execute(
                "INSERT IGNORE INTO user_account_access (user_id, aws_account_id) VALUES (%s, %s)",
                (user_id, acc_id)
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    _write_audit(actor=actor_name, action="Account access updated", detail=f"{user['username']} access: {account_ids}")
    return {"status": "updated", "user_id": user_id, "account_ids": account_ids}


@router.delete("/{user_id}")
def delete_user(user_id: int, payload: dict = Body(default={})):
    actor_id   = payload.get("actor_id")
    actor_name = payload.get("actor", "admin")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Guard — actor must be admin
    if actor_id:
        cursor.execute("SELECT role FROM users WHERE id = %s", (actor_id,))
        actor_row = cursor.fetchone()
        if not actor_row or actor_row["role"].lower() != "admin":
            cursor.close()
            conn.close()
            raise HTTPException(status_code=403, detail="Admin access required")

    # Guard — cannot delete self
    if actor_id and int(actor_id) == user_id:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=403, detail="Cannot delete your own account")

    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    _write_audit(actor=actor_name, action="User deleted", detail=f"{user['username']} removed")
    return {"status": "deleted", "id": user_id, "username": user["username"]}