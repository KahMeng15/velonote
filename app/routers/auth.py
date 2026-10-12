"""Authentication router"""

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db import (
    ChatMessage,
    EmailVerificationToken,
    IPBlock,
    PasswordChangeConfirmation,
    PasswordResetToken,
    Resource,
    StudySession,
    Subject,
    SubjectGroup,
    SystemSettings,
    User,
    UserInvitation,
    UserLog,
)
from app.schemas.schemas import FullNameStr, NicknameStr, UserCreate, UserUpdate
from app.schemas.schemas import User as UserSchema
from app.utils.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    pwd_context,
    validate_password_complexity,
    verify_password,
)
from app.utils.auth import get_current_user as get_current_user_from_token
from app.utils.db import get_db
from app.utils.email import send_password_reset_email, send_verification_email
from app.utils.invitation_utils import is_link_only_email
from app.utils.quotas import get_user_quota_status, get_user_tier_config

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/config")
async def get_auth_config():
    """Return public auth configuration for the frontend (no authentication required)."""
    return {
        "turnstile_site_key": settings.TURNSTILE_SITE_KEY,
        "turnstile_enabled": bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY),
    }

# Firebase project config

FIREBASE_VERIFY_URL = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyCustomToken"


def _set_auth_cookie(response: Response, access_token: str, expire_minutes: int) -> None:
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=expire_minutes * 60,
        path="/",
    )
    response.headers[settings.CSRF_HEADER_NAME] = csrf_token


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    # 7 days expiration for refresh tokens
    max_age = 7 * 24 * 60 * 60
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="Lax",  # Lax is generally safer for refresh tokens
        max_age=max_age,
        path="/auth/refresh",  # Only send this cookie to the refresh endpoint
    )


def _prepare_user_for_response(user: User) -> dict:
    """Ensure sensitive encrypted fields are safely presented in API responses."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "nickname": user.nickname,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "is_approved": user.is_approved,
        "is_verified": user.is_verified,
        "tier": user.tier,
        "ai_provider": user.ai_provider,
        "ai_model": user.ai_model,
        "ai_base_url": user.ai_base_url,
        "ai_api_key": None,
        "ai_api_key_configured": False,
        "use_global_ai_config": user.use_global_ai_config,
        "nav_sidebar_open": getattr(user, "nav_sidebar_open", True),
        "action_sidebar_open": getattr(user, "action_sidebar_open", True),
        "sort_preference": getattr(user, "sort_preference", "name_asc"),
        "last_chat_context": getattr(user, "last_chat_context", "global"),
        "last_chat_ai_mode": getattr(user, "last_chat_ai_mode", "elaborate"),
        "last_chat_output_format": getattr(user, "last_chat_output_format", "sentence"),
        "conv_response_mode": getattr(user, "conv_response_mode", "voice"),
        "conv_input_mode": getattr(user, "conv_input_mode", "push"),
        "conv_transcription_enabled": getattr(user, "conv_transcription_enabled", True),
        "conv_grading_mode": getattr(user, "conv_grading_mode", "lenient"),
        "has_password": bool(user.hashed_password),
        "created_at": user.created_at,
    }


class GoogleLoginRequest(BaseModel):
    """Google Sign-In request model"""

    idToken: str
    invitation_token: str | None = None


class GoogleCompleteRequest(BaseModel):
    """Complete Google registration with additional info"""

    idToken: str
    nickname: NicknameStr
    full_name: FullNameStr | None = None
    invitation_token: str | None = None
    agree_tos: bool = False
    agree_privacy: bool = False
    agree_fair_use: bool = False


class LinkGoogleAccountRequest(BaseModel):
    """Link Google account to existing user account"""

    idToken: str
    password: str


class UnlinkGoogleAccountRequest(BaseModel):
    """Unlink Google account from user account"""

    password: str


def verify_firebase_token(id_token_str: str):
    """Verify Firebase ID token signature and claims with Google certs."""
    try:
        logger.debug(f"Token verification starting, len={len(id_token_str) if id_token_str else 0}")

        if not id_token_str:
            raise ValueError("No token provided")

        request_adapter = google_requests.Request()
        verified_claims = id_token.verify_firebase_token(
            id_token_str,
            request_adapter,
            audience=settings.FIREBASE_PROJECT_ID,
        )

        if not verified_claims:
            raise ValueError("Token verification returned empty claims")

        # Validate essential claims
        email = verified_claims.get("email")
        if not email:
            raise ValueError("Token missing email claim")

        # Verify exact issuer for the configured Firebase project
        expected_issuer = f"https://securetoken.google.com/{settings.FIREBASE_PROJECT_ID}"
        issuer = verified_claims.get("iss", "")
        if issuer != expected_issuer:
            raise ValueError(f"Invalid token issuer. Expected: {expected_issuer}, Got: {issuer}")

        logger.debug("firebase.token_verified", extra={"email": email})
        return verified_claims

    except ValueError as e:
        logger.error(f"Token verification ValueError: {e!s}")
        raise e
    except Exception as e:
        logger.error(f"Token verification error: {type(e).__name__}: {e!s}", exc_info=True)
        raise ValueError(f"Token verification failed: {type(e).__name__}")


def record_auth_attempt(
    db: Session,
    action: str,
    email: str | None,
    ip_address: str | None,
    device_info: str,
    status: str,
    reason: str | None = None,
    user: User | None = None,
):
    detail_parts = []
    if email:
        detail_parts.append(f"email={email}")
    else:
        detail_parts.append("email=unknown")
    detail_parts.append(f"status={status}")
    if reason:
        detail_parts.append(reason)
    db.add(
        UserLog(
            user_id=user.id if user else None,
            action=action,
            ip_address=ip_address,
            device_info=device_info,
            details="; ".join(detail_parts),
        )
    )
    db.commit()


def validate_invitation_token(db: Session, token: str | None, email: str) -> UserInvitation:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is restricted to invited users only. Token required.",
        )

    invitation = (
        db.query(UserInvitation)
        .filter(UserInvitation.token == token, ~UserInvitation.is_used)
        .first()
    )
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired invitation token."
        )

    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invitation token has expired."
        )

    if not is_link_only_email(invitation.email) and invitation.email.lower() != email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitation token was issued for a different email address.",
        )

    return invitation


@router.get("/firebase-config")
def get_firebase_config():
    """Return the public Firebase configuration"""
    return {
        "apiKey": settings.FIREBASE_API_KEY,
        "authDomain": settings.FIREBASE_AUTH_DOMAIN,
        "projectId": settings.FIREBASE_PROJECT_ID,
        "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
        "messagingSenderId": settings.FIREBASE_MESSAGING_SENDER_ID,
        "appId": settings.FIREBASE_APP_ID,
        "measurementId": settings.FIREBASE_MEASUREMENT_ID,
    }


@router.get("/public-settings")
def get_public_settings(db: Session = Depends(get_db)):
    """Return public-safe system settings"""
    settings = db.query(SystemSettings).first()
    if not settings:
        return {
            "signup_config": "open",
            "maintenance_mode": False,
            "footer_text": "",
            "unnecessary_logins_enabled": False,
        }
    return {
        "signup_config": settings.signup_config,
        "maintenance_mode": settings.maintenance_mode,
        "footer_text": settings.footer_text,
        "unnecessary_logins_enabled": settings.unnecessary_logins_enabled,
    }


@router.get("/invitation/{token}")
def get_invitation(token: str, db: Session = Depends(get_db)):
    """Return invitation details for a valid token (public, no auth required)"""
    invite = (
        db.query(UserInvitation)
        .filter(UserInvitation.token == token, ~UserInvitation.is_used)
        .first()
    )
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation token.")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=404, detail="Invitation token has expired.")
    return {
        "email": None if is_link_only_email(invite.email) else invite.email,
        "tier": invite.tier,
    }


@router.post("/register", response_model=UserSchema)
def register(
    user_data: UserCreate, request: Request, token: str | None = None, db: Session = Depends(get_db)
):
    """Register a new user"""
    # Check maintenance mode
    sys_settings = db.query(SystemSettings).first()
    if sys_settings and sys_settings.maintenance_mode:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is disabled during maintenance.",
        )

    # Check system signup config
    signup_config = sys_settings.signup_config if sys_settings else "open"

    # Check required agreement fields
    if not user_data.agree_tos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must agree to the Terms of Service to register.",
        )
    if not user_data.agree_privacy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must agree to the Privacy Policy to register.",
        )
    if not user_data.agree_fair_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must agree to the Fair Use Policy to register.",
        )

    invitation = None
    if signup_config == "invite":
        if not token:
            raise HTTPException(
                status_code=403,
                detail="Registration is restricted to invited users only. Token required.",
            )

        invitation = (
            db.query(UserInvitation)
            .filter(UserInvitation.token == token, ~UserInvitation.is_used)
            .first()
        )
        if not invitation:
            raise HTTPException(status_code=403, detail="Invalid or expired invitation token.")

        if invitation.expires_at < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Invitation token has expired.")

        if (
            not is_link_only_email(invitation.email)
            and invitation.email.lower() != user_data.email.lower()
        ):
            raise HTTPException(
                status_code=403, detail="Invitation token was issued for a different email address."
            )

    # Validate password complexity
    validate_password_complexity(user_data.password)

    # Check if user exists
    existing_user = (
        db.query(User).filter(func.lower(User.email) == func.lower(user_data.email)).first()
    )

    # Special handling for Admin Email: allow "re-claiming" via signup if password is lost
    is_admin_signup = (
        settings.ADMIN_EMAIL and user_data.email.lower() == settings.ADMIN_EMAIL.lower()
    )

    if existing_user and not is_admin_signup:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    if is_admin_signup and existing_user:
        # Update existing admin user
        existing_user.nickname = user_data.nickname
        existing_user.full_name = user_data.full_name
        existing_user.hashed_password = hash_password(user_data.password)
        existing_user.is_admin = True
        existing_user.is_active = True
        existing_user.is_approved = True
        user = existing_user
    else:
        # Create new user
        is_admin = is_admin_signup
        is_approved = True if signup_config != "approval" or is_admin else False

        user = User(
            username=user_data.email,  # Use email as username
            email=user_data.email,
            full_name=user_data.full_name,
            nickname=user_data.nickname,
            hashed_password=hash_password(user_data.password),
            is_admin=is_admin,
            is_approved=is_approved,
            is_verified=True if is_admin else False,  # Admins auto-verified
            tier=invitation.tier if invitation else "free",
        )
        db.add(user)

    # Ensure new users have an ID before we set invitation.used_by
    db.flush()

    # Create verification token for new non-admin users
    if not user.is_verified:
        verification_token = EmailVerificationToken(
            user_id=user.id,
            email=user.email,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.add(verification_token)
        db.commit()
        db.refresh(verification_token)

        # Build verification link
        sys_settings = db.query(SystemSettings).first()
        domain = (
            sys_settings.domain_url
            if sys_settings and sys_settings.domain_url
            else "http://localhost:8000"
        )
        if not domain.startswith("http"):
            domain = f"http://{domain}"

        verify_link = f"{domain.rstrip('/')}/login?verify_token={verification_token.token}"

        # Send verification email
        email_sent = send_verification_email(db, user.email, verify_link)
        if not email_sent:
            logger.warning(f"Failed to send verification email to {user.email}")

    if invitation:
        invitation.is_used = True
        invitation.used_by = user.id

    db.commit()
    db.refresh(user)

    # Log signup
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(UserLog(user_id=user.id, action="signup", ip_address=ip_address, device_info=user_agent))
    db.commit()

    return user


@router.post("/login")
async def login(request: Request, response: Response, db: Session = Depends(get_db)):
    """Login user and return access token"""
    try:
        credentials = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    email = credentials.get("email")
    password = credentials.get("password")
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "Unknown Device")

    if not email or not password:
        record_auth_attempt(
            db,
            action="login_attempt",
            email=email,
            ip_address=ip_address,
            device_info=user_agent,
            status="missing_credentials",
            reason="Email or password missing",
        )
        raise HTTPException(status_code=400, detail="Missing email or password")

    # IP Lockout Check
    ip_block = db.query(IPBlock).filter(IPBlock.ip_address == ip_address).first()
    if ip_block and ip_block.locked_until and ip_block.locked_until > datetime.utcnow():
        wait_mins = int((ip_block.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Too many failed attempts from this IP. Please try again in {wait_mins} minutes.",
        )

    # Check maintenance mode
    sys_settings = db.query(SystemSettings).first()
    if sys_settings and sys_settings.maintenance_mode:
        if not settings.ADMIN_EMAIL or email.lower() != settings.ADMIN_EMAIL.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="System is undergoing maintenance. Only administrators can log in at this time.",
            )

    user = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()

    # User Lockout Check
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        wait_mins = int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account temporarily locked due to too many failed attempts. Please try again in {wait_mins} minutes.",
        )

    try:
        if not user or not verify_password(password, user.hashed_password):
            # Record failure and handle lockouts
            if not ip_block:
                ip_block = IPBlock(ip_address=ip_address, failed_attempts=1)
                db.add(ip_block)
            else:
                ip_block.failed_attempts += 1
                if ip_block.failed_attempts >= 10:  # IP limit is higher than user limit
                    ip_block.locked_until = datetime.utcnow() + timedelta(minutes=30)

            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=30)

            db.commit()

            record_auth_attempt(
                db,
                action="login_attempt",
                email=email,
                ip_address=ip_address,
                device_info=user_agent,
                status="invalid_credentials",
                reason="Invalid email or password",
                user=user,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
            )

        # Success: Reset attempts
        if ip_block:
            ip_block.failed_attempts = 0
            ip_block.locked_until = None

        user.failed_login_attempts = 0
        user.locked_until = None

        # Phase 1: Argon2 Upgrade Path
        if pwd_context.needs_update(user.hashed_password):
            user.hashed_password = hash_password(password)
            logger.info(f"Upgraded password hash to Argon2 for user: {user.email}")

        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        record_auth_attempt(
            db,
            action="login_attempt",
            email=email,
            ip_address=ip_address,
            device_info=user_agent,
            status="verification_error",
            reason=str(e),
            user=user,
        )
        logger.error(f"auth.login_error: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during login.",
        )

    if not user.is_active:
        record_auth_attempt(
            db,
            action="login_attempt",
            email=email,
            ip_address=ip_address,
            device_info=user_agent,
            status="disabled",
            reason="Account disabled",
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is disabled"
        )

    if not user.is_approved:
        record_auth_attempt(
            db,
            action="login_attempt",
            email=email,
            ip_address=ip_address,
            device_info=user_agent,
            status="unapproved",
            reason="Account pending approval",
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is pending approval by administrator",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified. Please check your inbox for the verification link.",
        )

    # Auto-elevate admin matching settings
    if (
        settings.ADMIN_EMAIL
        and user.email.lower() == settings.ADMIN_EMAIL.lower()
        and not user.is_admin
    ):
        user.is_admin = True
        db.commit()

    # Create token
    expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    if sys_settings and sys_settings.session_length:
        length = sys_settings.session_length
        unit = sys_settings.session_unit or "hours"
        if unit == "hours":
            expire_minutes = length * 60
        elif unit == "days":
            expire_minutes = length * 1440

    access_token = create_access_token(
        data={"sub": str(user.id), "tv": int(user.token_version or 0)},
        expires_delta=timedelta(minutes=expire_minutes),
    )

    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "tv": int(user.token_version or 0)}
    )

    _set_auth_cookie(response, access_token, expire_minutes)
    _set_refresh_cookie(response, refresh_token)

    # Log login
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(
        UserLog(
            user_id=user.id,
            action="login",
            ip_address=ip_address,
            device_info=user_agent,
            details=f"email={email}; status=success",
        )
    )
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": _prepare_user_for_response(user),
    }


@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    """Refresh access token using refresh token cookie"""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    from jose import JWTError, jwt

    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        from app.utils.auth import token_version_matches_user

        if not token_version_matches_user(payload, user):
            raise HTTPException(status_code=401, detail="Session expired")

        # Create new tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "tv": int(user.token_version or 0)}
        )
        # Also rotate refresh token
        new_refresh_token = create_refresh_token(
            data={"sub": str(user.id), "tv": int(user.token_version or 0)}
        )

        _set_auth_cookie(response, access_token, settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        _set_refresh_cookie(response, new_refresh_token)

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/google-login")
def google_login(
    google_request: GoogleLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Verify Google token and check if user exists"""
    # Check maintenance mode
    sys_settings = db.query(SystemSettings).first()
    if sys_settings and sys_settings.maintenance_mode:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is disabled during maintenance. Please use administrative email login.",
        )
    signup_config = sys_settings.signup_config if sys_settings else "open"
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    email: str | None = None

    try:
        logger.debug("auth.google_login.request_received")

        # Verify the Firebase ID token
        claims = verify_firebase_token(google_request.idToken)

        # Extract user information from token
        email = claims.get("email")
        full_name = claims.get("name", "")
        picture = claims.get("picture", "")

        logger.debug("auth.google_login.token_verified", extra={"email": email})

        if not email:
            record_auth_attempt(
                db,
                action="google_login_attempt",
                email=email,
                ip_address=ip_address,
                device_info=user_agent,
                status="missing_email",
                reason="Email missing from Google token",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email not found in Google account"
            )

        # Check if user exists
        user = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()
        firebase_user_id = claims.get("user_id") or claims.get("sub")

        if user:
            # Existing user - auto-link Google account if not yet linked
            if not user.google_oauth_id:
                # Auto-link the Google account
                logger.info(f"Auto-linking Google account to existing user: {email}")
                user.google_oauth_id = firebase_user_id
                db.commit()
            elif user.google_oauth_id != firebase_user_id:
                # Different Google account is already linked
                record_auth_attempt(
                    db,
                    action="google_login_attempt",
                    email=email,
                    ip_address=ip_address,
                    device_info=user_agent,
                    status="mismatch",
                    reason="Google OAuth ID mismatch",
                    user=user,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="A different Google account is linked to this account. Please use that Google account.",
                )

            if not user.is_active:
                record_auth_attempt(
                    db,
                    action="google_login_attempt",
                    email=email,
                    ip_address=ip_address,
                    device_info=user_agent,
                    status="disabled",
                    reason="Account disabled",
                    user=user,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is disabled"
                )
            if not user.is_approved:
                record_auth_attempt(
                    db,
                    action="google_login_attempt",
                    email=email,
                    ip_address=ip_address,
                    device_info=user_agent,
                    status="unapproved",
                    reason="Account pending approval",
                    user=user,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is pending approval by administrator",
                )

            if (
                settings.ADMIN_EMAIL
                and user.email.lower() == settings.ADMIN_EMAIL.lower()
                and not user.is_admin
            ):
                user.is_admin = True
                db.commit()

            sys_settings = db.query(SystemSettings).first()
            expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
            if sys_settings and sys_settings.session_length:
                length = sys_settings.session_length
                unit = sys_settings.session_unit or "hours"
                if unit == "hours":
                    expire_minutes = length * 60
                elif unit == "days":
                    expire_minutes = length * 1440

            access_token = create_access_token(
                data={"sub": str(user.id), "tv": int(user.token_version or 0)},
                expires_delta=timedelta(minutes=expire_minutes),
            )
            refresh_token = create_refresh_token(
                data={"sub": str(user.id), "tv": int(user.token_version or 0)}
            )
            _set_auth_cookie(response, access_token, expire_minutes)
            _set_refresh_cookie(response, refresh_token)

            # Log login
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent", "Unknown Device")
            db.add(
                UserLog(
                    user_id=user.id,
                    action="login",
                    ip_address=ip_address,
                    device_info=user_agent,
                    details=f"Google Auth; email={email}; status=success",
                )
            )
            db.commit()

            logger.info("auth.google_login.success", extra={"email": email, "is_new_user": False})
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": _prepare_user_for_response(user),
                "is_new_user": False,
            }
        else:
            # New user - enforce invite-only config before prompting for profile completion
            try:
                if signup_config == "invite":
                    validate_invitation_token(db, google_request.invitation_token, email)
            except HTTPException as invite_exc:
                record_auth_attempt(
                    db,
                    action="google_login_attempt",
                    email=email,
                    ip_address=ip_address,
                    device_info=user_agent,
                    status="invite_invalid",
                    reason=str(invite_exc.detail),
                )
                raise

            record_auth_attempt(
                db,
                action="google_login_attempt",
                email=email,
                ip_address=ip_address,
                device_info=user_agent,
                status="new_user",
                reason="Needs profile completion",
            )
            logger.info("auth.google_login.new_user_detected", extra={"email": email})
            return {
                "is_new_user": True,
                "email": email,
                "full_name": full_name,
                "picture": picture,
                "suggested_nickname": full_name.split()[0] if full_name else email.split("@")[0],
            }

    except HTTPException:
        raise
    except ValueError as e:
        record_auth_attempt(
            db,
            action="google_login_attempt",
            email=email,
            ip_address=ip_address,
            device_info=user_agent,
            status="token_error",
            reason=str(e),
        )
        logger.warning("auth.google_login.token_error", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        record_auth_attempt(
            db,
            action="google_login_attempt",
            email=email,
            ip_address=ip_address,
            device_info=user_agent,
            status="auth_error",
            reason=str(e),
        )
        logger.error("auth.google_login.unexpected_error", extra={"email": email, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {e!s}"
        )


@router.post("/google-complete")
def google_complete(
    google_request: GoogleCompleteRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Complete Google registration for new user with additional info"""
    # Check maintenance mode
    sys_settings = db.query(SystemSettings).first()
    if sys_settings and sys_settings.maintenance_mode:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is disabled during maintenance.",
        )
    signup_config = sys_settings.signup_config if sys_settings else "open"

    try:
        # Check required agreement fields
        if not google_request.agree_tos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must agree to the Terms of Service to register.",
            )
        if not google_request.agree_privacy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must agree to the Privacy Policy to register.",
            )
        if not google_request.agree_fair_use:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must agree to the Fair Use Policy to register.",
            )

        # Verify the Firebase ID token
        claims = verify_firebase_token(google_request.idToken)

        # Extract user information from token
        email = claims.get("email")
        token_full_name = claims.get("name", "")
        requested_full_name = (google_request.full_name or "").strip()
        full_name = requested_full_name or token_full_name
        google_user_id = claims.get("user_id") or claims.get("sub")  # Firebase user ID

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email not found in Google account"
            )

        # Check if user already exists
        existing_user = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()

        if existing_user:
            # User already exists, just log them in
            # Update google_oauth_id if not already set
            if not existing_user.google_oauth_id:
                existing_user.google_oauth_id = claims.get("user_id") or claims.get("sub")
                db.commit()
                db.refresh(existing_user)  # Refresh to get latest data

            if not existing_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is disabled"
                )

            if (
                settings.ADMIN_EMAIL
                and existing_user.email.lower() == settings.ADMIN_EMAIL.lower()
                and not existing_user.is_admin
            ):
                existing_user.is_admin = True
                db.commit()

            sys_settings = db.query(SystemSettings).first()
            expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
            if sys_settings and sys_settings.session_length:
                length = sys_settings.session_length
                unit = sys_settings.session_unit or "hours"
                if unit == "hours":
                    expire_minutes = length * 60
                elif unit == "days":
                    expire_minutes = length * 1440

            access_token = create_access_token(
                data={"sub": str(existing_user.id), "tv": int(existing_user.token_version or 0)},
                expires_delta=timedelta(minutes=expire_minutes),
            )
            refresh_token = create_refresh_token(
                data={"sub": str(existing_user.id), "tv": int(existing_user.token_version or 0)}
            )
            _set_auth_cookie(response, access_token, expire_minutes)
            _set_refresh_cookie(response, refresh_token)
            # Ensure user object is fresh with latest google_oauth_id
            db.refresh(existing_user)
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": _prepare_user_for_response(existing_user),
            }

        # Create new user with the provided nickname
        invitation = None
        if signup_config == "invite":
            invitation = validate_invitation_token(db, google_request.invitation_token, email)

        is_admin = (
            True
            if settings.ADMIN_EMAIL and email.lower() == settings.ADMIN_EMAIL.lower()
            else False
        )
        is_approved = True if signup_config != "approval" or is_admin else False
        tier = invitation.tier if invitation else "free"

        user = User(
            username=email,
            email=email,
            full_name=full_name,
            nickname=google_request.nickname,
            hashed_password="",  # No local password for Google auth users
            is_active=True,
            is_admin=is_admin,
            is_approved=is_approved,
            is_verified=True,  # Google users are pre-verified
            tier=tier,
            google_oauth_id=google_user_id,  # Store Firebase user ID
        )
        db.add(user)
        db.flush()
        if invitation:
            invitation.is_used = True
            invitation.used_by = user.id
        db.commit()
        db.refresh(user)

        # Log signup
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "Unknown Device")
        log_details = "Google Auth"
        if not is_approved:
            log_details = "Google Auth (pending approval)"
        db.add(
            UserLog(
                user_id=user.id,
                action="signup",
                ip_address=ip_address,
                device_info=user_agent,
                details=log_details,
            )
        )

        # Send welcome email
        from app.utils.email import send_welcome_email

        send_welcome_email(db, user.email, user.full_name or user.nickname)

        db.commit()

        if not is_approved:
            return {
                "pending_approval": True,
                "message": "Your account is pending administrator approval. We'll notify you once it is ready.",
            }

        # Create JWT token
        sys_settings = db.query(SystemSettings).first()
        expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        if sys_settings and sys_settings.session_length:
            length = sys_settings.session_length
            unit = sys_settings.session_unit or "hours"
            if unit == "hours":
                expire_minutes = length * 60
            elif unit == "days":
                expire_minutes = length * 1440

        access_token = create_access_token(
            data={"sub": str(user.id), "tv": int(user.token_version or 0)},
            expires_delta=timedelta(minutes=expire_minutes),
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "tv": int(user.token_version or 0)}
        )
        _set_auth_cookie(response, access_token, expire_minutes)
        _set_refresh_cookie(response, refresh_token)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": _prepare_user_for_response(user),
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Google registration failed: {e!s}"
        )


def get_current_user(current_user: User = Depends(get_current_user_from_token)):
    """Get current user info"""
    return current_user


@router.get("/me", response_model=UserSchema)
async def get_current_user_info(
    current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db)
):
    """Get current user information - used for session validation and data refresh"""
    # Refresh user data from DB to ensure we have latest info
    db.refresh(current_user)
    return _prepare_user_for_response(current_user)


@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Clear auth/session cookies and revoke active tokens for secure logout."""
    current_user.token_version = int(current_user.token_version or 0) + 1
    db.commit()

    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")
    response.delete_cookie(key="refresh_token", path="/auth/refresh")
    return {"message": "Logged out successfully"}


@router.put("/profile", response_model=UserSchema)
async def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Update user profile"""
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    if user_update.nickname is not None:
        current_user.nickname = user_update.nickname
    if user_update.ai_provider is not None:
        current_user.ai_provider = user_update.ai_provider
    if user_update.ai_model is not None:
        current_user.ai_model = user_update.ai_model
    if user_update.ai_base_url is not None:
        current_user.ai_base_url = user_update.ai_base_url
    if user_update.ai_api_key is not None:
        pass  # Keys are no longer stored in DB (managed via global fallback or user secrets if implemented later)
    if user_update.use_global_ai_config is not None:
        current_user.use_global_ai_config = user_update.use_global_ai_config
    if getattr(user_update, "nav_sidebar_open", None) is not None:
        current_user.nav_sidebar_open = user_update.nav_sidebar_open
    if getattr(user_update, "action_sidebar_open", None) is not None:
        current_user.action_sidebar_open = user_update.action_sidebar_open
    if getattr(user_update, "sort_preference", None) is not None:
        current_user.sort_preference = user_update.sort_preference
    if getattr(user_update, "last_chat_context", None) is not None:
        current_user.last_chat_context = user_update.last_chat_context
    if getattr(user_update, "last_chat_ai_mode", None) is not None:
        current_user.last_chat_ai_mode = user_update.last_chat_ai_mode
    if getattr(user_update, "last_chat_output_format", None) is not None:
        current_user.last_chat_output_format = user_update.last_chat_output_format
    if getattr(user_update, "conv_response_mode", None) is not None:
        current_user.conv_response_mode = user_update.conv_response_mode
    if getattr(user_update, "conv_input_mode", None) is not None:
        current_user.conv_input_mode = user_update.conv_input_mode
    if getattr(user_update, "conv_transcription_enabled", None) is not None:
        current_user.conv_transcription_enabled = user_update.conv_transcription_enabled
    if getattr(user_update, "conv_grading_mode", None) is not None:
        current_user.conv_grading_mode = user_update.conv_grading_mode

    db.commit()
    db.refresh(current_user)
    return _prepare_user_for_response(current_user)


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    password: str


@router.post("/change-email", response_model=UserSchema)
async def change_email(
    request_data: ChangeEmailRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Change user email with password verification"""
    if current_user.hashed_password:
        if not verify_password(request_data.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
            )

    new_email = request_data.new_email.lower().strip()

    if new_email == current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New email is the same as current email",
        )

    existing = db.query(User).filter(func.lower(User.email) == new_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered to another account. Please log into that account and delete it first, then try again.",
        )

    current_user.email = new_email
    current_user.is_verified = False

    # Generate verification token
    token_str = secrets.token_urlsafe(48)
    verify_token = EmailVerificationToken(
        user_id=current_user.id,
        email=new_email,
        token=token_str,
        expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    db.add(verify_token)
    db.commit()

    # Send verification email
    sys_settings = db.query(SystemSettings).first()
    domain = (
        sys_settings.domain_url
        if sys_settings and sys_settings.domain_url
        else "http://localhost:8000"
    )
    if not domain.startswith("http"):
        domain = f"http://{domain}"
    verify_link = f"{domain.rstrip('/')}/login?verify_token={token_str}"
    send_verification_email(db, new_email, verify_link)

    db.refresh(current_user)
    return _prepare_user_for_response(current_user)


@router.get("/stats")
async def get_user_stats(
    current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db)
):
    """Get personalized statistics and recent logins for the current user"""
    u_id = current_user.id
    notes_count = db.query(func.count(Resource.id)).filter(Resource.user_id == u_id).scalar() or 0
    subjects_count = db.query(func.count(Subject.id)).filter(Subject.user_id == u_id).scalar() or 0
    groups_count = (
        db.query(func.count(SubjectGroup.id)).filter(SubjectGroup.user_id == u_id).scalar() or 0
    )
    questions_count = (
        db.query(func.count(ChatMessage.id)).filter(ChatMessage.user_id == u_id).scalar() or 0
    )

    time_spent_mins = (
        db.query(func.sum(StudySession.duration_minutes))
        .filter(StudySession.user_id == u_id)
        .scalar()
        or 0
    )

    storage_bytes = (
        db.query(func.sum(Resource.file_size)).filter(Resource.user_id == u_id).scalar() or 0
    )
    storage_mb = round(storage_bytes / (1024 * 1024), 2)

    tier_config = get_user_tier_config(current_user, db)
    storage_limit_label = (
        "Unlimited" if tier_config.max_storage_gb == -1 else f"{tier_config.max_storage_gb} GB"
    )

    recent_logins_query = (
        db.query(UserLog)
        .filter(UserLog.user_id == u_id, UserLog.action == "login")
        .order_by(UserLog.timestamp.desc())
        .limit(5)
        .all()
    )

    recent_logins = [
        {
            "ip_address": log.ip_address,
            "device_info": log.device_info,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in recent_logins_query
    ]

    return {
        "notes_uploaded": notes_count,
        "subjects_created": subjects_count,
        "groups_created": groups_count,
        "questions_asked": questions_count,
        "time_spent_mins": time_spent_mins,
        "space_used_mb": storage_mb,
        "storage_limit": storage_limit_label,
        "recent_logins": recent_logins,
    }


@router.get("/quotas")
async def get_user_quotas(
    current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db)
):
    """Get current user's tier, quotas, and usage statistics"""
    return get_user_quota_status(current_user, db)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class RequestPasswordChangeConfirmation(BaseModel):
    current_password: str
    new_password: str


class ConfirmPasswordChange(BaseModel):
    confirmation_code: str


@router.put("/change-password")
async def change_password(
    passwords: PasswordChange,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Change the user's password"""
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Cannot change password for OAuth accounts. Please login via Google.",
        )

    # Validate new password complexity
    validate_password_complexity(passwords.new_password)

    try:
        if not verify_password(passwords.current_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect current password")
    except ValueError:
        raise HTTPException(status_code=400, detail="Error verifying current password")

    current_user.hashed_password = hash_password(passwords.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


@router.post("/request-password-change")
async def request_password_change(
    request_data: RequestPasswordChangeConfirmation,
    request: Request,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Request a password change with email confirmation"""
    # If user has no password, they're setting one for the first time
    if current_user.hashed_password:
        # Verify current password for existing password users
        try:
            if not verify_password(request_data.current_password, current_user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect current password"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Error verifying current password"
            )
    # If user has no password, current_password check is skipped (first-time setup)

    # Validate new password complexity
    validate_password_complexity(request_data.new_password)

    # Check for too many recent requests (rate limiting)
    recent_confirmations = (
        db.query(PasswordChangeConfirmation)
        .filter(
            PasswordChangeConfirmation.user_id == current_user.id,
            ~PasswordChangeConfirmation.is_used,
            PasswordChangeConfirmation.expires_at > datetime.utcnow(),
        )
        .all()
    )

    if len(recent_confirmations) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many password change requests. Please wait before trying again.",
        )

    # Generate confirmation code (6 digits)
    confirmation_code = "".join(secrets.choice("0123456789") for _ in range(6))

    # Hash the new password for later verification
    new_password_hash = hash_password(request_data.new_password)

    # Create confirmation record (15 minute expiry)
    password_confirmation = PasswordChangeConfirmation(
        user_id=current_user.id,
        email=current_user.email,
        confirmation_code=confirmation_code,
        new_password_hash=new_password_hash,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db.add(password_confirmation)
    db.commit()

    # Send confirmation email
    from app.utils.email import send_password_change_confirmation_email

    send_password_change_confirmation_email(db, current_user.email, confirmation_code)

    # Log action
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    action_type = (
        "password_set_requested"
        if not current_user.hashed_password
        else "password_change_requested"
    )
    db.add(
        UserLog(
            user_id=current_user.id,
            action=action_type,
            ip_address=ip_address,
            device_info=user_agent,
        )
    )
    db.commit()

    return {
        "message": "Confirmation code sent to your email. Please check your email (and spam folder) and enter the code in the next 1 hour.",
        "email_masked": f"{current_user.email[:2]}***@{current_user.email.split('@')[1]}",
    }


@router.post("/confirm-password-change")
async def confirm_password_change(
    request_data: ConfirmPasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Confirm password change with confirmation code"""
    # Find the confirmation record
    confirmation = (
        db.query(PasswordChangeConfirmation)
        .filter(
            PasswordChangeConfirmation.user_id == current_user.id,
            PasswordChangeConfirmation.confirmation_code == request_data.confirmation_code,
            ~PasswordChangeConfirmation.is_used,
        )
        .first()
    )

    if not confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid confirmation code."
        )

    # Check if token has expired
    if confirmation.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation code has expired. Please request a new one.",
        )

    # Update password
    current_user.hashed_password = confirmation.new_password_hash
    current_user.token_version = int(current_user.token_version or 0) + 1
    confirmation.is_used = True

    # Log action
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(
        UserLog(
            user_id=current_user.id,
            action="password_changed",
            ip_address=ip_address,
            device_info=user_agent,
        )
    )

    # Send notification email
    from app.utils.email import send_password_changed_notification_email

    send_password_changed_notification_email(db, current_user.email)

    db.commit()

    return {"message": "Password has been changed successfully!"}


@router.delete("/profile")
async def delete_account(
    current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db)
):
    """Permanently delete user account and data"""
    db.delete(current_user)
    db.commit()
    return {"message": "Account deleted successfully"}


@router.get("/download-data")
async def download_data(
    current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db)
):
    """Export all user data as JSON"""
    uid = current_user.id

    # This is a simple aggregated export
    notes = db.query(Resource).filter(Resource.user_id == uid).all()
    subjects = db.query(Subject).filter(Subject.user_id == uid).all()
    db.query(SubjectGroup).filter(SubjectGroup.user_id == uid).all()
    chats = db.query(ChatMessage).filter(ChatMessage.user_id == uid).all()

    # We serialize the most important details for them
    data = {
        "profile": {
            "email": current_user.email,
            "full_name": current_user.full_name,
            "nickname": current_user.nickname,
            "joined_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "subjects": [{"id": s.id, "name": s.name} for s in subjects],
        "notes_uploaded": [
            {"id": l.id, "title": l.title, "subject_id": l.subject_id} for l in notes
        ],
        "chat_history": [
            {"role": c.role, "content": c.content, "timestamp": c.timestamp.isoformat()}
            for c in chats
        ],
    }

    from fastapi.responses import JSONResponse

    # Use headers to force file download in browser
    headers = {
        "Content-Disposition": f"attachment; filename=velonote_export_{current_user.username}.json"
    }
    return JSONResponse(content=data, headers=headers)


# --- Password Reset ---
class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetSubmit(BaseModel):
    token: str
    new_password: str


@router.post("/password-reset-request")
def request_password_reset(
    reset_request: PasswordResetRequest, request: Request, db: Session = Depends(get_db)
):
    """Request a password reset email. Rate limited to prevent abuse."""
    email = reset_request.email.lower().strip()

    # Check if user exists
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user:
        # For security, don't reveal whether email exists
        return {
            "message": "If an account exists with this email, a password reset link has been sent."
        }

    # Check for too many recent requests from same email (rate limiting)
    recent_resets = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.email == email,
            ~PasswordResetToken.is_used,
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        .all()
    )

    if len(recent_resets) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many password reset requests. Please wait a few hours before trying again.",
        )

    # Create password reset token (24 hour expiry)
    reset_token = PasswordResetToken(
        user_id=user.id,
        email=email,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(reset_token)
    db.commit()
    db.refresh(reset_token)

    # Build reset link
    sys_settings = db.query(SystemSettings).first()
    domain = (
        sys_settings.domain_url
        if sys_settings and sys_settings.domain_url
        else "http://localhost:8000"
    )
    if not domain.startswith("http"):
        domain = f"http://{domain}"

    reset_link = f"{domain.rstrip('/')}/login?reset_token={reset_token.token}"

    # Send email
    send_password_reset_email(db, email, reset_link)

    # Log action
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(
        UserLog(
            user_id=user.id,
            action="password_reset_request",
            ip_address=ip_address,
            device_info=user_agent,
        )
    )
    db.commit()

    return {"message": "If an account exists with this email, a password reset link has been sent."}


@router.post("/password-reset")
def reset_password(
    reset_data: PasswordResetSubmit, request: Request, db: Session = Depends(get_db)
):
    """Reset password with valid token"""

    # Find the reset token
    reset_token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token == reset_data.token, ~PasswordResetToken.is_used)
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used password reset token.",
        )

    # Check if token has expired
    if reset_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset link has expired. Please request a new one.",
        )

    # Get user
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found.")

    # Validate new password complexity
    validate_password_complexity(reset_data.new_password)

    # Update password
    user.hashed_password = hash_password(reset_data.new_password)
    user.token_version = int(user.token_version or 0) + 1
    reset_token.is_used = True

    # Log action
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(
        UserLog(
            user_id=user.id,
            action="password_reset_complete",
            ip_address=ip_address,
            device_info=user_agent,
        )
    )

    # Send notification email
    from app.utils.email import send_password_changed_notification_email

    send_password_changed_notification_email(db, user.email)

    db.commit()

    return {
        "message": "Password has been reset successfully. You can now log in with your new password."
    }


@router.get("/password-reset-token-valid")
def check_reset_token_validity(token: str, db: Session = Depends(get_db)):
    """Check if a password reset token is still valid"""
    reset_token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token == token, ~PasswordResetToken.is_used)
        .first()
    )

    if not reset_token:
        return {"valid": False, "message": "Invalid or already-used token"}

    if reset_token.expires_at < datetime.utcnow():
        return {"valid": False, "message": "Token has expired"}

    return {"valid": True, "message": "Token is valid"}


# --- Email Verification ---


class EmailVerifySubmit(BaseModel):
    token: str


@router.post("/verify-email")
def verify_email(verify_data: EmailVerifySubmit, request: Request, db: Session = Depends(get_db)):
    """Verify email with valid token"""

    sys_settings = db.query(SystemSettings).first()
    approval_mode = sys_settings.signup_config == "approval" if sys_settings else False
    success_msg = (
        "Email verified! Please wait for the admin to approve your access. You will receive an email."
        if approval_mode
        else "Email verified successfully! You can now log in."
    )

    # Atomically claim the token — only succeeds if not yet used and not expired
    from sqlalchemy import update

    result = db.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.token == verify_data.token,
            ~EmailVerificationToken.is_used,
        )
        .values(is_used=True)
    )
    db.commit()

    if result.rowcount == 0:
        # Token not found or already used
        token = (
            db.query(EmailVerificationToken)
            .filter(EmailVerificationToken.token == verify_data.token)
            .first()
        )
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification link.",
            )
        if token.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification link has expired. Please request a new one by trying to log in.",
            )
        # Token was claimed by a concurrent request — if user is already verified, treat as success
        user = db.query(User).filter(User.id == token.user_id).first()
        if user and user.is_verified:
            return {"message": success_msg}
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link has already been used.",
        )

    # Fetch the now-used token and its user
    verify_token = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token == verify_data.token)
        .first()
    )
    user = db.query(User).filter(User.id == verify_token.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found.")

    # Update user verification status
    user.is_verified = True

    # Log action
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(
        UserLog(
            user_id=user.id, action="email_verified", ip_address=ip_address, device_info=user_agent
        )
    )

    db.commit()

    # Send welcome email (after commit, so concurrent duplicates are blocked)
    from app.utils.email import send_welcome_email

    send_welcome_email(db, user.email, user.full_name or user.nickname)

    return {"message": success_msg}


@router.get("/email-verification-token-valid")
def check_verification_token_validity(token: str, db: Session = Depends(get_db)):
    """Check if an email verification token is still valid"""
    verify_token = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token == token, ~EmailVerificationToken.is_used)
        .first()
    )

    if not verify_token:
        return {"valid": False, "message": "Invalid or already-used link"}

    if verify_token.expires_at < datetime.utcnow():
        return {"valid": False, "message": "Link has expired"}

    return {"valid": True, "message": "Link is valid"}


class ResendVerificationRequest(BaseModel):
    email: EmailStr


@router.post("/resend-verification")
def resend_verification(
    resend_request: ResendVerificationRequest, request: Request, db: Session = Depends(get_db)
):
    """Resend email verification link. Rate limited."""
    email = resend_request.email.lower().strip()

    # Find user
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user:
        # Security: Don't reveal email existence
        return {
            "message": "If your account is not verified, a new verification link has been sent."
        }

    if user.is_verified:
        return {"message": "Your account is already verified. You can sign in."}

    # Rate limiting: Check for too many recent resends
    recent_tokens = (
        db.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.email == email,
            ~EmailVerificationToken.is_used,
            EmailVerificationToken.expires_at > datetime.utcnow(),
        )
        .all()
    )

    if len(recent_tokens) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait before requesting another link.",
        )

    # Create new token
    verification_token = EmailVerificationToken(
        user_id=user.id,
        email=user.email,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(verification_token)
    db.commit()
    db.refresh(verification_token)

    # Build verification link
    sys_settings = db.query(SystemSettings).first()
    domain = (
        sys_settings.domain_url
        if sys_settings and sys_settings.domain_url
        else "http://localhost:8000"
    )
    if not domain.startswith("http"):
        domain = f"http://{domain}"

    verify_link = f"{domain.rstrip('/')}/login?verify_token={verification_token.token}"

    # Send email
    email_sent = send_verification_email(db, user.email, verify_link)
    if not email_sent:
        logger.warning(f"Failed to resend verification email to {user.email}")
        return {
            "message": "Warning: Unable to send verification email. Please check server email configuration and try again later."
        }

    # Log action
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(
        UserLog(
            user_id=user.id,
            action="verification_resend",
            ip_address=ip_address,
            device_info=user_agent,
        )
    )
    db.commit()

    return {
        "message": "A new verification link has been sent to your email. Check your spam folder if you don't see it."
    }


# --- Google Account Linking ---


@router.get("/connected-accounts")
async def get_connected_accounts(current_user: User = Depends(get_current_user_from_token)):
    """Get list of connected OAuth accounts for current user"""
    return {
        "google_linked": bool(current_user.google_oauth_id),
        "email": current_user.email,
        "has_password": bool(current_user.hashed_password),
    }


@router.post("/link-google-account")
async def link_google_account(
    request_data: LinkGoogleAccountRequest,
    request: Request,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Link a Google account to the current user's account"""
    # Require password to be set (security requirement for account management)
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set a password before linking a Google account. Please create a password first.",
        )

    # Verify password
    try:
        if not verify_password(request_data.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Error verifying password"
        )

    # Check if already linked
    if current_user.google_oauth_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Google account is already linked to this account",
        )

    # Verify Google token
    try:
        claims = verify_firebase_token(request_data.idToken)
        google_user_email = claims.get("email", "").lower()
        google_user_id = claims.get("user_id") or claims.get("sub", "")

        if not google_user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email not found in Google token"
            )

        # Security check: Ensure the Google email matches the current user's email (case-insensitive)
        if google_user_email != current_user.email.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email does not match your account email. Please use the same email address.",
            )

        # Check if this Google ID is already linked to another account
        existing_google_link = db.query(User).filter(User.google_oauth_id == google_user_id).first()
        if existing_google_link and existing_google_link.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This Google account is already linked to another user account",
            )

        # Link the Google account
        current_user.google_oauth_id = google_user_id
        db.commit()

        # Log action
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "Unknown Device")
        db.add(
            UserLog(
                user_id=current_user.id,
                action="google_linked",
                ip_address=ip_address,
                device_info=user_agent,
            )
        )
        db.commit()

        return {
            "message": "Google account successfully linked",
            "google_linked": True,
            "email": current_user.email,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {e!s}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error linking Google account: {e!s}",
        )


@router.post("/link-google-via-popup")
async def link_google_via_popup(
    request_data: LinkGoogleAccountRequest,
    request: Request,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Link a Google account to current user via popup flow.

    This endpoint is simpler than link-google-account:
    - User must provide password for identity verification
    - Google account can be from any email (not just current user's email)
    - Allows linking via the simple signInWithPopup flow from settings
    """
    # Require password to be set (security requirement for account management)
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set a password before linking a Google account. Please create a password first.",
        )

    # Verify password
    try:
        if not verify_password(request_data.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Error verifying password"
        )

    # Check if already linked
    if current_user.google_oauth_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Google account is already linked to this account",
        )

    # Verify Google token
    try:
        claims = verify_firebase_token(request_data.idToken)
        google_user_email = claims.get("email", "").lower()
        google_user_id = claims.get("user_id") or claims.get("sub", "")

        if not google_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account ID not found in token",
            )

        # Check if this Google ID is already linked to another account
        existing_google_link = db.query(User).filter(User.google_oauth_id == google_user_id).first()
        if existing_google_link and existing_google_link.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This Google account is already linked to another user account",
            )

        # Link the Google account
        current_user.google_oauth_id = google_user_id
        db.commit()

        # Log action
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "Unknown Device")
        db.add(
            UserLog(
                user_id=current_user.id,
                action="google_linked",
                ip_address=ip_address,
                device_info=user_agent,
            )
        )
        db.commit()

        return {
            "message": "Google account successfully linked",
            "google_linked": True,
            "email": current_user.email,
            "google_email": google_user_email,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {e!s}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error linking Google account: {e!s}",
        )


@router.post("/unlink-google-account")
async def unlink_google_account(
    request_data: UnlinkGoogleAccountRequest,
    request: Request,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Unlink Google account from current user's account"""
    # Check if Google is linked
    if not current_user.google_oauth_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No Google account is currently linked"
        )

    # Require password to be set (so user can still login after unlinking)
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set a password before unlinking your Google account, so you can continue to log in. Please create a password first in your security settings.",
        )

    # Verify password (security requirement)
    try:
        if not verify_password(request_data.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Error verifying password"
        )

    # Unlink the Google account
    current_user.google_oauth_id = None
    db.commit()

    # Log action
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown Device")
    db.add(
        UserLog(
            user_id=current_user.id,
            action="google_unlinked",
            ip_address=ip_address,
            device_info=user_agent,
        )
    )
    db.commit()

    return {
        "message": "Google account successfully unlinked",
        "google_linked": False,
        "email": current_user.email,
    }
