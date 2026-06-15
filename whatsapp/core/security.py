# core/security.py
# ══════════════════════════════════════════════════════
# CORE — JWT Auth + Password Hashing
#
# NEW vs URL Shortener: full auth system
#
# Architecture concept:
#   JWT (JSON Web Token) = stateless auth
#   - No session DB needed
#   - Token is self-contained: { user_id, exp }
#   - Server only needs the secret to verify
#   - Scales to millions with zero shared state
# ══════════════════════════════════════════════════════

import jwt
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from config.settings import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINS


# ── PASSWORD HASHING ──────────────────────────────────
# We use SHA-256 + salt for simplicity (use bcrypt in production)
def hash_password(password: str) -> str:
    """Hash a password with a random salt. Never store plain text."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"

def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against its hash."""
    try:
        salt, h = hashed.split(":")
        expected = hashlib.sha256(f"{salt}{plain}".encode()).hexdigest()
        return hmac.compare_digest(h, expected)
    except Exception:
        return False


# ── JWT TOKEN ─────────────────────────────────────────
def create_token(user_id: int) -> str:
    """
    Create a signed JWT token for a user.
    Payload: { user_id, exp (expiry timestamp) }
    Signed with JWT_SECRET — cannot be forged without the secret.
    """
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Optional[int]:
    """
    Decode and verify a JWT. Returns user_id or None if invalid/expired.
    Architecture: this runs on EVERY request — must be fast (it is, O(1)).
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("user_id")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── FASTAPI DEPENDENCY ────────────────────────────────
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from db.database import get_db

bearer_scheme = HTTPBearer()

def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> int:
    """
    FastAPI dependency: extract and verify JWT from Authorization header.
    Usage in routes: user_id: int = Depends(get_current_user_id)
    """
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
