# app/api/auth.py
from fastapi import APIRouter, HTTPException, Body
from app.db import get_connection
import bcrypt
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _verify_password(plain: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), stored.encode())
    except Exception as e:
        logger.warning(f"Password verify error: {e}")
        return False


@router.post("/login")
def login(payload: dict = Body(...)):
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, username, role, password AS pw FROM users WHERE username = %s AND active = 1",
        (username,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not _verify_password(password, user["pw"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "id":       user["id"],
        "username": user["username"],
        "role":     user["role"],
    }
