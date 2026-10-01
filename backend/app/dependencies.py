import sqlite3

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import db
from .security import decode_token, verify_secret

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> sqlite3.Row:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user_id = decode_token(credentials.credentials)
    with db.connect() as connection:
        user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return user


def get_strategy_user(x_strategy_key: str = Header(...)) -> sqlite3.Row:
    with db.connect() as connection:
        users = connection.execute("SELECT * FROM users").fetchall()
    user = next((candidate for candidate in users if verify_secret(x_strategy_key, candidate["strategy_api_key_hash"])), None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid strategy API key")
    return user

