"""Admin Dashboard Router"""

import datetime
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import LOGS_DIR
from app.models.db import (
    ChatMessage,
    Exercise,
    GlobalPrompt,
    IPFilter,
    Note,
    PasswordResetToken,
    RateLimitConfig,
    Resource,
    StudySession,
    Subject,
    SubjectGroup,
    SystemSettings,
    Task,
    TierConfig,
    User,
    UserInvitation,
    UserLog,
)
from app.routers.auth import get_current_user
from app.schemas.admin import (
    EmailConfigSchema,
    GlobalPromptCreate,
    GlobalPromptSchema,
    GlobalPromptUpdate,
    IPFilterCreate,
    IPFilterSchema,
    RateLimitConfigSchema,
    SystemSettingsSchema,
    TierConfigSchema,
    UserActionRequest,
    UserAdminResponse,
    UserInvitationCreate,
    UserInvitationResponse,
    UserInvitationUpdate,
    UserLogSchema,
)
from app.utils.auth import hash_password, validate_password_complexity
from app.utils.cache import clear_cache_pattern_sync
from app.utils.db import get_db
from app.utils.email import (
    send_account_approved_email,
    send_invitation_email,
    send_password_reset_email,
)
from app.utils.invitation_utils import build_link_only_email, is_link_only_email
from app.utils.observability import get_runtime_metrics_snapshot
from app.utils.quotas import ensure_default_tier_configs
from app.utils.storage import StorageManager
from app.utils.tasks import TaskManager

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def _prepare_system_settings_response(settings: SystemSettings) -> dict:
    return {
        "lockdown_mode": settings.lockdown_mode,
        "signup_config": settings.signup_config,
        "maintenance_mode": settings.maintenance_mode,
        "footer_text": settings.footer_text,
        "domain_url": settings.domain_url,
        "global_ai_provider": settings.global_ai_provider,
        "global_ai_model": settings.global_ai_model,
        "global_ai_base_url": settings.global_ai_base_url,
        "ai_limit_per_user": settings.ai_limit_per_user,
        "session_length": settings.session_length,
        "session_unit": settings.session_unit,
        "session_reset_on_activity": settings.session_reset_on_activity,
        "max_exercise_questions": settings.max_exercise_questions,
        "unnecessary_logins_enabled": settings.unnecessary_logins_enabled,
        "backup_enabled": settings.backup_enabled,
        "backup_retention_days": settings.backup_retention_days,
    }


def _get_domain(sys_settings: SystemSettings | None) -> str:
    domain = (
        sys_settings.domain_url
        if sys_settings and sys_settings.domain_url
        else "http://localhost:8000"
    )
    if not domain.startswith("http"):
        domain = f"http://{domain}"
    return domain.rstrip("/")


def get_current_admin_user(current_user: User = Depends(get_current_user)):
    """Dependency to check if current user is an admin"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user


@router.get("/runtime-metrics")
def get_runtime_metrics(admin: User = Depends(get_current_admin_user)):
    """Get lightweight runtime metrics for production diagnostics."""
    return get_runtime_metrics_snapshot()


# --- System Settings ---
@router.get("/system-settings", response_model=SystemSettingsSchema)
def get_system_settings(
    db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    from app.config import get_settings

    app_settings = get_settings()

    settings = db.query(SystemSettings).first()
    if not settings:
        settings = SystemSettings(
            global_ai_provider=app_settings.GLOBAL_AI_PROVIDER,
            global_ai_model=app_settings.GLOBAL_AI_MODEL,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    else:
        # Prefill empty fields from .env if they are null/empty in DB
        updated = False
        if not settings.global_ai_provider:
            settings.global_ai_provider = app_settings.GLOBAL_AI_PROVIDER
            updated = True
        if not settings.global_ai_model:
            settings.global_ai_model = app_settings.GLOBAL_AI_MODEL
            updated = True

        if updated:
            db.commit()
            db.refresh(settings)

    return _prepare_system_settings_response(settings)


@router.put("/system-settings", response_model=SystemSettingsSchema)
def update_system_settings(
    update_data: SystemSettingsSchema,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    settings = db.query(SystemSettings).first()
    if not settings:
        settings = SystemSettings()
        db.add(settings)

    for key, value in update_data.model_dump().items():
        if key == "global_ai_api_key":
            continue
        else:
            setattr(settings, key, value)

    settings.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(settings)
    return _prepare_system_settings_response(settings)


# --- Email Config ---
@router.get("/email-config", response_model=EmailConfigSchema)
def get_email_config(admin: User = Depends(get_current_admin_user)):
    """Get SMTP configuration (read-only from environment)"""
    return {
        "smtp_provider": f"{settings.SMTP_HOST}:{settings.SMTP_PORT}",
        "email_address": settings.SMTP_USER,
        "sender_name": settings.SMTP_SENDER_NAME,
        "app_password": "********" if settings.SMTP_PASSWORD else None,
    }


@router.post("/email-config/test")
def test_email_config(
    request_body: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Send a test email to verify email configuration is working"""
    from pydantic import BaseModel, field_validator

    from app.utils.email import send_email

    class TestEmailRequest(BaseModel):
        test_email: str

        @field_validator("test_email")
        @classmethod
        def validate_email(cls, v):
            if not v or "@" not in v:
                raise ValueError("Invalid email address")
            return v.lower().strip()

    # Validate request
    try:
        validated = TestEmailRequest(**request_body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid email: {e!s}")

    # Check if settings are complete
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise HTTPException(
            status_code=400,
            detail="Email configuration is incomplete in .env. Please configure SMTP settings there.",
        )

    # Send test email
    test_subject = "velonote Email Configuration Test"
    test_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #3b82f6;">Email Configuration Test</h2>
            <p>This is a test email from velonote to verify your SMTP configuration is working correctly.</p>
            <div style="background-color: #f0f9ff; padding: 15px; border-radius: 8px; border-left: 4px solid #3b82f6; margin: 20px 0;">
                <p style="margin: 0;"><strong>✓ Good news!</strong> Your email configuration is working properly.</p>
            </div>
            <p style="font-size: 12px; color: #666; margin-top: 30px;">
                If you received this email, your system can now send:
                <ul style="margin: 10px 0;">
                    <li>User invitations</li>
                    <li>Password reset links</li>
                    <li>System notifications</li>
                </ul>
            </p>
            <p style="font-size: 11px; color: #999; margin-top: 20px;">
                Sent at {datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC
            </p>
        </body>
    </html>
    """

    success = send_email(db, validated.test_email, test_subject, test_body, is_html=True)

    if success:
        # Log action
        ip_address = request.client.host if request.client else None
        db.add(
            UserLog(
                user_id=admin.id,
                action="email_test",
                ip_address=ip_address,
                device_info=request.headers.get("user-agent", "Unknown"),
                details=f"Test email sent to {validated.test_email}",
            )
        )
        db.commit()

        return {
            "success": True,
            "message": f"Test email sent successfully to {validated.test_email}. Please check your inbox.",
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send test email. Check your SMTP configuration and try again.",
        )


# --- Rate Limit Config ---
@router.get("/rate-limits", response_model=RateLimitConfigSchema)
def get_rate_limits(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    limits = db.query(RateLimitConfig).first()
    if not limits:
        limits = RateLimitConfig()
        db.add(limits)
        db.commit()
        db.refresh(limits)
    return limits


@router.put("/rate-limits", response_model=RateLimitConfigSchema)
def update_rate_limits(
    update_data: RateLimitConfigSchema,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    limits = db.query(RateLimitConfig).first()
    if not limits:
        limits = RateLimitConfig()
        db.add(limits)

    for key, value in update_data.model_dump().items():
        setattr(limits, key, value)

    limits.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(limits)
    return limits


# --- Tier Configurations ---
@router.get("/tiers", response_model=list[TierConfigSchema])
def get_all_tiers(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """Get all tier configurations"""
    ensure_default_tier_configs(db)
    tiers = db.query(TierConfig).all()
    return tiers


@router.get("/tiers/{tier_id}", response_model=TierConfigSchema)
def get_tier(
    tier_id: str, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    """Get a specific tier configuration"""
    tier = db.query(TierConfig).filter(TierConfig.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")
    return tier


@router.put("/tiers/{tier_id}", response_model=TierConfigSchema)
def update_tier(
    tier_id: str,
    update_data: TierConfigSchema,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Update a tier configuration"""
    tier = db.query(TierConfig).filter(TierConfig.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")

    for key, value in update_data.model_dump(exclude={"created_at", "updated_at"}).items():
        if value is not None:
            setattr(tier, key, value)

    tier.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(tier)
    return tier


# --- IP Filters ---
@router.get("/ip-filters", response_model=list[IPFilterSchema])
def get_ip_filters(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    return db.query(IPFilter).all()


@router.post("/ip-filters", response_model=IPFilterSchema)
def create_ip_filter(
    filter_data: IPFilterCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    new_filter = IPFilter(**filter_data.model_dump())
    db.add(new_filter)
    db.commit()
    db.refresh(new_filter)
    return new_filter


@router.delete("/ip-filters/{filter_id}")
def delete_ip_filter(
    filter_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    db_filter = db.query(IPFilter).filter(IPFilter.id == filter_id).first()
    if not db_filter:
        raise HTTPException(status_code=404, detail="Filter not found")
    db.delete(db_filter)
    db.commit()
    return {"message": "Filter deleted"}


# --- Global Prompts ---
@router.get("/global-prompts", response_model=list[GlobalPromptSchema])
def get_global_prompts(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return db.query(GlobalPrompt).all()


@router.post("/global-prompts", response_model=GlobalPromptSchema)
def create_global_prompt(
    prompt_data: GlobalPromptCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    new_prompt = GlobalPrompt(**prompt_data.model_dump())
    db.add(new_prompt)
    db.commit()
    db.refresh(new_prompt)
    return new_prompt


@router.put("/global-prompts/{prompt_id}", response_model=GlobalPromptSchema)
def update_global_prompt(
    prompt_id: int,
    update_data: GlobalPromptUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    db_prompt = db.query(GlobalPrompt).filter(GlobalPrompt.id == prompt_id).first()
    if not db_prompt:
        raise HTTPException(status_code=404, detail="Global prompt not found")

    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(db_prompt, key, value)

    db_prompt.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(db_prompt)
    return db_prompt


@router.delete("/global-prompts/{prompt_id}")
def delete_global_prompt(
    prompt_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    db_prompt = db.query(GlobalPrompt).filter(GlobalPrompt.id == prompt_id).first()
    if not db_prompt:
        raise HTTPException(status_code=404, detail="Global prompt not found")
    db.delete(db_prompt)
    db.commit()
    return {"message": "Global prompt deleted"}


# --- Users Management ---
@router.get("/users", response_model=list[UserAdminResponse])
def get_all_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    users = db.query(User).all()
    results = []

    # Compute stats for each user
    for u in users:
        notes_count = (
            db.query(func.count(Note.id)).join(Resource).filter(Resource.user_id == u.id).scalar()
            or 0
        )
        subjects_count = (
            db.query(func.count(Subject.id)).filter(Subject.user_id == u.id).scalar() or 0
        )
        groups_count = (
            db.query(func.count(SubjectGroup.id)).filter(SubjectGroup.user_id == u.id).scalar() or 0
        )
        conv_count = (
            db.query(func.count(ChatMessage.id)).filter(ChatMessage.user_id == u.id).scalar() or 0
        )

        # Calculate storage used
        storage_bytes = (
            db.query(func.sum(Resource.file_size)).filter(Resource.user_id == u.id).scalar() or 0
        )
        storage_mb = round(storage_bytes / (1024 * 1024), 2)

        total_logins = (
            db.query(func.count(UserLog.id))
            .filter(UserLog.user_id == u.id, UserLog.action == "login")
            .scalar()
            or 0
        )
        # Calculate roughly sum of study sessions durations (or approximate)
        total_time_mins = (
            db.query(func.sum(StudySession.duration_minutes))
            .filter(StudySession.user_id == u.id)
            .scalar()
            or 0
        )

        user_dict = u.__dict__.copy()
        user_dict["ai_api_key"] = None
        user_dict["ai_api_key_configured"] = False
        user_dict.update(
            {
                "notes_count": notes_count,
                "subjects_count": subjects_count,
                "groups_count": groups_count,
                "conversations_count": conv_count,
                "questions_count": conv_count,  # roughly same as conv count in this context
                "storage_used": f"{storage_mb} MB",
                "total_logins": total_logins,
                "total_online_time": total_time_mins,
            }
        )
        results.append(UserAdminResponse(**user_dict))

    return results


@router.post("/users/action")
def user_action(
    request: UserActionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.action == "deactivate":
        user.is_active = False
    elif request.action == "activate":
        user.is_active = True
    elif request.action == "delete":
        db.delete(user)
    elif request.action == "reset_password":
        if not request.value:
            raise HTTPException(status_code=400, detail="New password required")
        validate_password_complexity(request.value)
        user.hashed_password = hash_password(request.value)
        user.token_version = int(user.token_version or 0) + 1
    elif request.action == "tier":
        if not request.value:
            raise HTTPException(status_code=400, detail="Tier value required")
        user.tier = request.value
    elif request.action == "admin":
        user.is_admin = request.value.lower() == "true" if request.value else True
    elif request.action == "approve":
        user.is_approved = True
        user.is_active = True
        sys_settings = db.query(SystemSettings).first()
        domain = _get_domain(sys_settings)
        login_url = f"{domain}/login"
        send_account_approved_email(db, user.email, user.full_name or user.nickname, login_url)
    elif request.action == "unapprove":
        user.is_approved = False
    elif request.action == "send_reset_link":
        reset_token = PasswordResetToken(
            user_id=user.id,
            email=user.email,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(hours=24),
        )
        db.add(reset_token)
        db.flush()
        sys_settings = db.query(SystemSettings).first()
        domain = _get_domain(sys_settings)
        reset_link = f"{domain}/login?reset_token={reset_token.token}"
        email_sent = send_password_reset_email(db, user.email, reset_link)
        if not email_sent:
            raise HTTPException(
                status_code=500,
                detail="Failed to send password reset email. Check SMTP configuration.",
            )
    elif request.action == "change_email":
        if not request.value:
            raise HTTPException(status_code=400, detail="New email address required")
        new_email = request.value.lower().strip()
        existing = (
            db.query(User).filter(func.lower(User.email) == new_email, User.id != user.id).first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use by another user")
        user.email = new_email
        user.username = new_email
        user.is_verified = False
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    db.commit()
    return {"message": "Action completed successfully"}


# --- Invitations ---
@router.post("/invitations", response_model=UserInvitationResponse)
def create_invitation(
    invite_data: UserInvitationCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    send_email = invite_data.send_email
    requested_email = invite_data.email.lower().strip() if invite_data.email else None
    target_email = requested_email if send_email else None

    # Targeted invites have existing users and invitations tied to the email address
    existing_invite = None
    if target_email:
        existing_user = (
            db.query(User).filter(func.lower(User.email) == func.lower(target_email)).first()
        )
        if existing_user:
            raise HTTPException(status_code=400, detail="User with this email already exists")

        existing_invite = (
            db.query(UserInvitation)
            .filter(
                func.lower(UserInvitation.email) == func.lower(target_email),
                ~UserInvitation.is_used,
            )
            .first()
        )

    expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=7)
    token = secrets.token_urlsafe(32)
    email_value = target_email or build_link_only_email(token)

    if existing_invite:
        existing_invite.token = token
        existing_invite.expires_at = expires_at
        existing_invite.tier = invite_data.tier
        existing_invite.email = email_value
        existing_invite.label = invite_data.label
        db.commit()
        db.refresh(existing_invite)
        invite = existing_invite
    else:
        invite = UserInvitation(
            email=email_value,
            token=token,
            invited_by=admin.id,
            tier=invite_data.tier,
            label=invite_data.label,
            expires_at=expires_at,
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

    # Generate link
    settings = db.query(SystemSettings).first()
    domain = settings.domain_url if settings and settings.domain_url else "http://localhost:8000"
    if not domain.startswith("http"):
        domain = f"http://{domain}"

    invitation_link = f"{domain.rstrip('/')}/signup?token={invite.token}"

    # Send email only when requested
    if send_email and target_email:
        send_invitation_email(db, target_email, invitation_link)

    response = UserInvitationResponse.model_validate(invite)
    response.invitation_link = invitation_link
    response.send_email = send_email
    return response


@router.get("/invitations", response_model=list[UserInvitationResponse])
def get_invitations(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    invites = db.query(UserInvitation).order_by(desc(UserInvitation.created_at)).all()
    results = []

    settings = db.query(SystemSettings).first()
    domain = settings.domain_url if settings and settings.domain_url else "http://localhost:8000"
    if not domain.startswith("http"):
        domain = f"http://{domain}"

    for i in invites:
        resp = UserInvitationResponse.model_validate(i)
        resp.send_email = not is_link_only_email(i.email)
        resp.invitation_link = f"{domain.rstrip('/')}/signup?token={i.token}"

        # Get accepted user info if invitation was used
        if i.used_by:
            accepted_user = db.query(User).filter(User.id == i.used_by).first()
            if accepted_user:
                resp.accepted_by_email = accepted_user.email
                resp.accepted_by_name = accepted_user.full_name or accepted_user.nickname or "N/A"

        results.append(resp)

    return results


@router.delete("/invitations/{token}")
def revoke_invitation(
    token: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    invite = db.query(UserInvitation).filter(UserInvitation.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.is_used:
        raise HTTPException(status_code=400, detail="Cannot revoke a used invitation")
    db.delete(invite)
    db.commit()
    return {"message": "Invitation revoked"}


@router.put("/invitations/{token}", response_model=UserInvitationResponse)
def update_invitation(
    token: str,
    update_data: UserInvitationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    invite = db.query(UserInvitation).filter(UserInvitation.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if update_data.label is not None:
        invite.label = update_data.label

    db.commit()
    db.refresh(invite)

    settings = db.query(SystemSettings).first()
    domain = settings.domain_url if settings and settings.domain_url else "http://localhost:8000"
    if not domain.startswith("http"):
        domain = f"http://{domain}"

    resp = UserInvitationResponse.model_validate(invite)
    resp.send_email = not is_link_only_email(invite.email)
    resp.invitation_link = f"{domain.rstrip('/')}/signup?token={invite.token}"

    if invite.used_by:
        accepted_user = db.query(User).filter(User.id == invite.used_by).first()
        if accepted_user:
            resp.accepted_by_email = accepted_user.email
            resp.accepted_by_name = accepted_user.full_name or accepted_user.nickname or "N/A"

    return resp


# --- User Logs ---
@router.get("/logs", response_model=list[UserLogSchema])
def get_user_logs(
    user_id: int | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    query = db.query(UserLog)
    if user_id:
        query = query.filter(UserLog.user_id == user_id)
    if action:
        query = query.filter(UserLog.action == action)

    logs = query.order_by(desc(UserLog.timestamp)).offset(offset).limit(limit).all()
    return logs


# --- File-based Logs ---
@router.get("/log-files")
def list_log_files(admin: User = Depends(get_current_admin_user)):
    """List all .log files in the logs directory with sizes."""
    import os

    files = []
    log_dir = os.path.normpath(os.path.abspath(LOGS_DIR))
    if not os.path.isdir(log_dir):
        return files
    for f in sorted(os.listdir(log_dir)):
        if not f.endswith(".log"):
            continue
        fpath = os.path.join(log_dir, f)
        try:
            size = os.path.getsize(fpath)
        except OSError:
            size = 0
        files.append({"name": f, "size_bytes": size})
    return files


@router.get("/log-files/{filename}")
def read_log_file(filename: str, limit: int = 200, admin: User = Depends(get_current_admin_user)):
    """Read the last N lines from a specific log file."""
    import os
    import re

    fpath = os.path.normpath(os.path.join(LOGS_DIR, filename))
    if not fpath.startswith(os.path.normpath(os.path.abspath(LOGS_DIR))):
        raise HTTPException(status_code=403, detail="Invalid log file path")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"Log file not found: {filename}")
    max_bytes = min(max(os.path.getsize(fpath), 1), 5 * 1024 * 1024)
    lines = []
    with open(fpath, encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        file_size = f.tell()
        start = max(0, file_size - max_bytes)
        f.seek(start)
        if start > 0:
            f.readline()
        all_lines = f.readlines()
    for raw_line in all_lines[-limit:]:
        line = raw_line.rstrip("\n\r")
        m = re.match(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)\s+\[(\w+)\]\s+([\w\.]+):\s+(.*)", line
        )
        if m:
            lines.append(
                {
                    "timestamp": m.group(1),
                    "level": m.group(2),
                    "logger": m.group(3),
                    "message": m.group(4),
                }
            )
        else:
            lines.append(
                {
                    "timestamp": None,
                    "level": None,
                    "logger": None,
                    "message": line,
                }
            )
    return {"filename": filename, "lines": lines, "total_bytes": file_size}


# --- Database Inspection ---
@router.get("/db/tables")
def list_db_tables(admin: User = Depends(get_current_admin_user)):
    """List all available tables in the database"""
    from app.models.db import Base

    return sorted(Base.metadata.tables.keys())


@router.get("/db/table/{table_name}")
def get_table_data(
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Fetch raw data from a specific table"""
    from sqlalchemy import text

    from app.models.db import Base

    if table_name not in Base.metadata.tables:
        raise HTTPException(status_code=404, detail="Table not found")

    # Use raw SQL to fetch data for any table generically
    query = text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset")  # nosec - table_name is validated against metadata
    result = db.execute(query, {"limit": limit, "offset": offset})

    # Get column names
    columns = result.keys()

    # Convert rows to list of dicts
    data = []
    for row in result:
        row_dict = {}
        for i, col in enumerate(columns):
            val = row[i]
            # Convert datetime and other non-serializable types to string
            if isinstance(val, (datetime.datetime, datetime.date)):
                val = val.isoformat()
            elif isinstance(val, bytes):
                val = f"<binary data: {len(val)} bytes>"
            row_dict[col] = val
        data.append(row_dict)

    return {"table": table_name, "columns": list(columns), "data": data, "count": len(data)}


# --- Database Backups ---
@router.get("/backups")
def get_backups(admin: User = Depends(get_current_admin_user)):
    """List all available database backups."""
    from app.utils.backup import list_backups

    return list_backups()


@router.post("/backups/create")
def trigger_backup(admin: User = Depends(get_current_admin_user)):
    """Trigger an immediate database backup."""
    from app.utils.backup import create_manual_backup

    try:
        backup_info = create_manual_backup()
        return {
            "success": True,
            "message": "Database backup created successfully",
            "backup": backup_info,
        }
    except Exception as e:
        logger.error(f"Manual database backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups/{filename}/download")
def download_backup(filename: str, admin: User = Depends(get_current_admin_user)):
    """Download a database backup file."""
    from app.utils.backup import get_backup_file_path

    try:
        file_path = get_backup_file_path(filename)
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type="application/sql",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Download backup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/backups/{filename}")
def delete_backup(filename: str, admin: User = Depends(get_current_admin_user)):
    """Delete a specific database backup file."""
    from app.utils.backup import delete_backup_file

    try:
        deleted = delete_backup_file(filename)
        if not deleted:
            raise HTTPException(status_code=404, detail="Backup file not found")
        return {"success": True, "message": f"Backup '{filename}' deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Delete backup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- HTTP Status Codes Diagnostics ---
@router.get("/http-status-codes")
def get_http_status_codes(admin: User = Depends(get_current_admin_user)):
    """Get a list of common HTTP status codes for the diagnostics page"""
    status_codes = {
        "1xx Informational": [
            {
                "code": 100,
                "text": "Continue",
                "description": "Request received, proceeding with upload",
            },
            {
                "code": 101,
                "text": "Switching Protocols",
                "description": "Switching to a different protocol",
            },
        ],
        "2xx Success": [
            {"code": 200, "text": "OK", "description": "Request succeeded"},
            {"code": 201, "text": "Created", "description": "Resource created successfully"},
            {"code": 202, "text": "Accepted", "description": "Request accepted for processing"},
            {"code": 204, "text": "No Content", "description": "Request succeeded with no content"},
        ],
        "3xx Redirection": [
            {
                "code": 300,
                "text": "Multiple Choices",
                "description": "Multiple options for the requested resource",
            },
            {"code": 301, "text": "Moved Permanently", "description": "Resource permanently moved"},
            {"code": 302, "text": "Found", "description": "Resource temporarily moved"},
            {"code": 304, "text": "Not Modified", "description": "Cached resource is still valid"},
        ],
        "4xx Client Error": [
            {"code": 400, "text": "Bad Request", "description": "Invalid request syntax"},
            {"code": 401, "text": "Unauthorized", "description": "Authentication required"},
            {"code": 403, "text": "Forbidden", "description": "Access denied"},
            {"code": 404, "text": "Not Found", "description": "Resource not found"},
            {
                "code": 409,
                "text": "Conflict",
                "description": "Request conflicts with current state",
            },
            {"code": 429, "text": "Too Many Requests", "description": "Rate limit exceeded"},
        ],
        "5xx Server Error": [
            {
                "code": 500,
                "text": "Internal Server Error",
                "description": "Server encountered an error",
            },
            {
                "code": 501,
                "text": "Not Implemented",
                "description": "Server doesn't support the functionality",
            },
            {
                "code": 502,
                "text": "Bad Gateway",
                "description": "Invalid response from upstream server",
            },
            {
                "code": 503,
                "text": "Service Unavailable",
                "description": "Server temporarily unavailable",
            },
        ],
    }
    return status_codes


# ─────────────────────────────────────────────────────────────────────────────
# Admin User Content Viewer — Read-Only + Delete/Reprocess
# ─────────────────────────────────────────────────────────────────────────────


def _get_target_user(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# --- Groups ---


@router.get("/users/{user_id}/groups")
def admin_get_user_groups(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    _get_target_user(user_id, db)
    groups = db.query(SubjectGroup).filter(SubjectGroup.user_id == user_id).all()
    result = []
    for g in groups:
        subjects = db.query(Subject).filter(Subject.group_id == g.id).all()
        result.append(
            {
                "id": g.id,
                "name": g.name,
                "user_id": g.user_id,
                "subjects": [{"id": s.id, "name": s.name, "color": s.color} for s in subjects],
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
            }
        )
    return result


@router.delete("/users/{user_id}/groups/{group_id}")
def admin_delete_user_group(
    user_id: int,
    group_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    group = (
        db.query(SubjectGroup)
        .filter(SubjectGroup.id == group_id, SubjectGroup.user_id == user_id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    db.query(Subject).filter(Subject.group_id == group_id).delete()
    db.delete(group)
    db.commit()
    clear_cache_pattern_sync(f"cache_resp:/groups*:u{user_id}*")
    clear_cache_pattern_sync(f"cache_resp:/subjects*:u{user_id}*")
    return {"message": "Group deleted"}


# --- Subjects ---


@router.get("/users/{user_id}/subjects")
def admin_get_user_subjects(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    _get_target_user(user_id, db)
    subjects = db.query(Subject).filter(Subject.user_id == user_id).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "color": s.color,
            "group_id": s.group_id,
            "user_id": s.user_id,
            "resource_count": db.query(func.count(Resource.id))
            .filter(Resource.subject_id == s.id)
            .scalar()
            or 0,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in subjects
    ]


@router.delete("/users/{user_id}/subjects/{subject_id}")
def admin_delete_user_subject(
    user_id: int,
    subject_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.user_id == user_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    resources = db.query(Resource).filter(Resource.subject_id == subject_id).all()
    for r in resources:
        if r.file_path:
            try:
                os.remove(r.file_path)
            except Exception:
                pass
        StorageManager.delete_resource_files(r.id)
    db.query(Resource).filter(Resource.subject_id == subject_id).delete()
    db.delete(subject)
    db.commit()
    clear_cache_pattern_sync(f"cache_resp:/subjects*:u{user_id}*")
    clear_cache_pattern_sync(f"cache_resp:/resources*:u{user_id}*")
    return {"message": "Subject deleted"}


# --- Resources ---


@router.get("/users/{user_id}/resources")
def admin_get_user_resources(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    _get_target_user(user_id, db)
    resources = db.query(Resource).filter(Resource.user_id == user_id).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "file_name": r.file_name,
            "file_type": r.file_type,
            "file_size": r.file_size,
            "page_count": r.page_count,
            "subject_id": r.subject_id,
            "processing_time_ms": r.processing_time_ms,
            "has_output_pdf": bool(r.output_pdf_path),
            "notes_count": db.query(func.count(Note.id)).filter(Note.resource_id == r.id).scalar()
            or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in resources
    ]


@router.get("/users/{user_id}/resources/{resource_id}")
def admin_get_user_resource_detail(
    user_id: int,
    resource_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    r = db.query(Resource).filter(Resource.id == resource_id, Resource.user_id == user_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    text = StorageManager.get_resource_text(resource_id)
    structured = StorageManager.get_resource_json(resource_id, "structured")
    images = StorageManager.get_resource_json(resource_id, "images")
    timings = StorageManager.get_resource_json(resource_id, "timings")
    return {
        "id": r.id,
        "title": r.title,
        "file_name": r.file_name,
        "file_type": r.file_type,
        "file_size": r.file_size,
        "page_count": r.page_count,
        "file_path": r.file_path,
        "output_pdf_path": r.output_pdf_path,
        "processing_time_ms": r.processing_time_ms,
        "subject_id": r.subject_id,
        "content_length": len(text) if text else 0,
        "extracted_text": text,
        "structured_content": structured,
        "images_metadata": images,
        "timings": timings,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.post("/users/{user_id}/resources/{resource_id}/reprocess")
def admin_reprocess_resource(
    user_id: int,
    resource_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    r = db.query(Resource).filter(Resource.id == resource_id, Resource.user_id == user_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not r.file_path or not os.path.exists(r.file_path):
        raise HTTPException(status_code=400, detail="Original file not found on disk")
    task_id = f"ocr_{user_id}_{resource_id}_{int(datetime.datetime.utcnow().timestamp())}"
    TaskManager.submit_task(
        task_id, "resource_processing", user_id, resource_id=resource_id, file_name=r.file_name
    )
    return {"message": "Reprocessing submitted", "task_id": task_id}


@router.delete("/users/{user_id}/resources/{resource_id}")
def admin_delete_user_resource(
    user_id: int,
    resource_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    r = db.query(Resource).filter(Resource.id == resource_id, Resource.user_id == user_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.file_path:
        try:
            os.remove(r.file_path)
        except Exception:
            pass
    StorageManager.delete_resource_files(r.id)
    db.delete(r)
    db.commit()
    # Invalidate the target user's resource cache
    clear_cache_pattern_sync(f"cache_resp:/resources*:u{user_id}*")
    return {"message": "Resource deleted"}


# --- Exercises ---


@router.get("/users/{user_id}/exercises")
def admin_get_user_exercises(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    _get_target_user(user_id, db)
    exercises = (
        db.query(Exercise)
        .filter(Exercise.user_id == user_id)
        .order_by(Exercise.created_at.desc())
        .all()
    )
    result = []
    for ex in exercises:
        questions = StorageManager.get_exercise_json(ex.id) or []
        q_count = len(questions) if isinstance(questions, list) else 0
        params = StorageManager.get_resource_json(ex.id, "parameters")
        result.append(
            {
                "id": ex.id,
                "title": ex.title,
                "subject_id": ex.subject_id,
                "group_id": ex.group_id,
                "resource_id": ex.resource_id,
                "file_name": ex.file_name,
                "model": ex.model,
                "processing_time_ms": ex.processing_time_ms,
                "question_count": q_count,
                "has_file": bool(ex.file_path),
                "has_content": bool(ex.content_path),
                "parameters": params,
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
                "updated_at": ex.updated_at.isoformat() if ex.updated_at else None,
            }
        )
    return result


@router.get("/users/{user_id}/exercises/{exercise_id}")
def admin_get_user_exercise_detail(
    user_id: int,
    exercise_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    ex = db.query(Exercise).filter(Exercise.id == exercise_id, Exercise.user_id == user_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Exercise not found")
    questions = StorageManager.get_exercise_json(ex.id) or []
    params = StorageManager.get_resource_json(ex.id, "parameters")
    return {
        "id": ex.id,
        "title": ex.title,
        "subject_id": ex.subject_id,
        "group_id": ex.group_id,
        "resource_id": ex.resource_id,
        "file_path": ex.file_path,
        "file_name": ex.file_name,
        "content_path": ex.content_path,
        "model": ex.model,
        "processing_time_ms": ex.processing_time_ms,
        "questions": questions if isinstance(questions, list) else [],
        "parameters": params,
        "created_at": ex.created_at.isoformat() if ex.created_at else None,
        "updated_at": ex.updated_at.isoformat() if ex.updated_at else None,
    }


@router.post("/users/{user_id}/exercises/{exercise_id}/reprocess")
def admin_reprocess_exercise(
    user_id: int,
    exercise_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    ex = db.query(Exercise).filter(Exercise.id == exercise_id, Exercise.user_id == user_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Exercise not found")
    params = StorageManager.get_resource_json(ex.id, "parameters")
    if ex.file_path and os.path.exists(ex.file_path):
        task_id = f"extract_{exercise_id}_{int(datetime.datetime.utcnow().timestamp())}"
        TaskManager.submit_task(
            task_id, "exercise_extraction", user_id, exercise_id=exercise_id, title=ex.title
        )
    elif params:
        task_id = f"generate_{exercise_id}_{int(datetime.datetime.utcnow().timestamp())}"
        TaskManager.submit_task(
            task_id,
            "exercise_generation",
            user_id,
            exercise_id=exercise_id,
            req_data=params,
            title=ex.title,
        )
    else:
        raise HTTPException(
            status_code=400, detail="Cannot reprocess: missing file or generation parameters"
        )
    return {"message": "Reprocessing submitted", "task_id": task_id}


@router.delete("/users/{user_id}/exercises/{exercise_id}")
def admin_delete_user_exercise(
    user_id: int,
    exercise_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    ex = db.query(Exercise).filter(Exercise.id == exercise_id, Exercise.user_id == user_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Exercise not found")
    if ex.file_path:
        try:
            os.remove(ex.file_path)
        except Exception:
            pass
    StorageManager.delete_exercise_files(exercise_id)
    db.delete(ex)
    db.commit()
    return {"message": "Exercise deleted"}


# --- Notes ---


@router.get("/users/{user_id}/notes")
def admin_get_user_notes(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    _get_target_user(user_id, db)
    notes = db.query(Note).filter(Note.user_id == user_id).order_by(Note.created_at.desc()).all()
    return [
        {
            "id": n.id,
            "title": n.title,
            "version": n.version,
            "summary_type": n.summary_type,
            "resource_id": n.resource_id,
            "mode": n.mode,
            "output_format": n.output_format,
            "processing_method": n.processing_method,
            "model": n.model,
            "processing_time_ms": n.processing_time_ms,
            "processing_time": n.processing_time,
            "is_user_edited": n.is_user_edited,
            "is_pinned": n.is_pinned,
            "prompt_name": n.prompt_name,
            "has_content": bool(StorageManager.get_note_text(n.id)),
            "file_path": n.file_path,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        }
        for n in notes
    ]


@router.get("/users/{user_id}/notes/{note_id}")
def admin_get_user_note_detail(
    user_id: int,
    note_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    n = db.query(Note).filter(Note.id == note_id, Note.user_id == user_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    text = StorageManager.get_note_text(note_id)
    quickread = StorageManager.get_note_text(note_id, is_quickread=True)
    return {
        "id": n.id,
        "title": n.title,
        "version": n.version,
        "summary_type": n.summary_type,
        "resource_id": n.resource_id,
        "mode": n.mode,
        "output_format": n.output_format,
        "processing_method": n.processing_method,
        "split_level": n.split_level,
        "model": n.model,
        "processing_time_ms": n.processing_time_ms,
        "processing_time": n.processing_time,
        "is_user_edited": n.is_user_edited,
        "is_pinned": n.is_pinned,
        "custom_prompt": n.custom_prompt,
        "prompt_name": n.prompt_name,
        "prompt_icon": n.prompt_icon,
        "resource_ids": n.resource_ids,
        "exercise_ids": n.exercise_ids,
        "file_path": n.file_path,
        "content": text,
        "quickread": quickread,
        "content_length": len(text) if text else 0,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


@router.delete("/users/{user_id}/notes/{note_id}")
def admin_delete_user_note(
    user_id: int,
    note_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    n = db.query(Note).filter(Note.id == note_id, Note.user_id == user_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    StorageManager.delete_note_files(note_id)
    db.delete(n)
    db.commit()
    clear_cache_pattern_sync(f"cache_resp:/notes*:u{user_id}*")
    return {"message": "Note deleted"}


# --- Conversations ---


@router.get("/users/{user_id}/conversations")
def admin_get_user_conversations(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    _get_target_user(user_id, db)
    convs = (
        db.query(
            ChatMessage.conversation_id,
            ChatMessage.conversation_title,
            func.count(ChatMessage.id).label("message_count"),
            func.max(ChatMessage.created_at).label("last_message_at"),
        )
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id.isnot(None),
        )
        .group_by(
            ChatMessage.conversation_id,
            ChatMessage.conversation_title,
        )
        .order_by(func.max(ChatMessage.created_at).desc())
        .all()
    )

    return [
        {
            "conversation_id": c.conversation_id,
            "title": c.conversation_title or "Untitled Conversation",
            "message_count": c.message_count,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
        }
        for c in convs
    ]


@router.get("/users/{user_id}/conversations/{conversation_id}")
def admin_get_user_conversation_detail(
    user_id: int,
    conversation_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    _get_target_user(user_id, db)
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == conversation_id,
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    return [
        {
            "id": m.id,
            "message": m.message,
            "response": m.response,
            "sources": m.sources,
            "ai_mode": m.ai_mode,
            "output_format": m.output_format,
            "ai_model": m.ai_model,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "resource_id": m.resource_id,
            "subject_id": m.subject_id,
            "group_id": m.group_id,
            "is_pinned": m.is_pinned,
            "is_favourite": m.is_favourite,
            "rating": m.rating,
            "rating_comment": m.rating_comment,
        }
        for m in messages
    ]


# --- Tasks ---


@router.get("/users/{user_id}/tasks")
def admin_get_user_tasks(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    _get_target_user(user_id, db)
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id)
        .order_by(Task.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": t.id,
            "task_id": t.task_id,
            "task_type": t.task_type,
            "status": t.status,
            "progress": t.progress,
            "error_message": t.error_message,
            "message": t.message,
            "is_hung": t.status in ("pending", "running")
            and t.updated_at
            and (datetime.datetime.utcnow() - t.updated_at).total_seconds() > 3600,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in tasks
    ]


@router.post("/tasks/{task_id}/cancel")
def admin_cancel_task(
    task_id: str, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    """Cancel a hung or stuck task. Admin override — no user_id check."""
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Task already {task.status}")
    task.status = "cancelled"
    task.error_message = "Cancelled by admin"
    task.updated_at = datetime.datetime.utcnow()
    db.commit()
    return {"message": "Task cancelled", "task_id": task_id}
