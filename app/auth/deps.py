from fastapi import Depends, HTTPException, Header
from app.auth.security import decode_token

def get_current_user(authorization: str = Header(...)):
    try:
        token = authorization.replace("Bearer ", "")
        return decode_token(token)
    except Exception:
        raise HTTPException(401, "Invalid token")

def require_role(*roles):
    def wrapper(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Forbidden")
        return user
    return wrapper

def require_account_access(account_id: int, user):
    if user["role"] == "admin":
        return
    if user["accounts"] != "ALL" and account_id not in user["accounts"]:
        raise HTTPException(403, "No access to this account")