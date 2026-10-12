"""Authentication utilities"""

from datetime import datetime, timedelta

from fastapi import Cookie, Depends, Header, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.utils.db import get_db

settings = get_settings()

try:
    import zxcvbn
except ImportError:
    zxcvbn = None  # Password complexity validation will be skipped if library is missing

# Password hashing
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using Argon2 (default)."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_complexity(password: str) -> bool:
    """
    Validate password complexity using zxcvbn.
    Enforces a minimum score of 3 (Strong) and minimum 8 characters.
    """
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )

    if zxcvbn is None:
        # Skip complexity check if library not installed
        return True

    result = zxcvbn.zxcvbn(password)
    if result.get("score", 0) < 3:
        feedback = result.get("feedback", {})
        warning = feedback.get("warning", "Password is too weak.")
        suggestions = feedback.get("suggestions", [])
        detail = warning
        if suggestions:
            detail += " Suggestions: " + " ".join(suggestions)

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return True


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a long-lived refresh token"""
    to_encode = data.copy()
    # 7 days expiration for refresh tokens
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict | None:
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def token_version_matches_user(payload: dict, user) -> bool:
    """Check whether token's session version still matches user's active session version."""
    try:
        token_version = int(payload.get("tv", 0))
    except (TypeError, ValueError):
        token_version = 0
    user_token_version = int(getattr(user, "token_version", 0) or 0)
    return token_version == user_token_version


async def get_current_user(
    authorization: str = Header(None),
    access_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """Get current user from JWT token"""
    token = None

    if authorization:
        # Extract token from "Bearer <token>" format
        try:
            scheme, parsed_token = authorization.split()
            if scheme.lower() != "bearer":
                raise ValueError("Invalid auth scheme")
            token = parsed_token
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.models.db import User

    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not token_version_matches_user(payload, user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is pending approval",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
