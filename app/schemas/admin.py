from datetime import datetime

from pydantic import BaseModel, EmailStr, model_validator

from app.schemas.schemas import User


class SystemSettingsSchema(BaseModel):
    lockdown_mode: bool
    signup_config: str
    maintenance_mode: bool
    footer_text: str | None = None
    domain_url: str | None = None
    global_ai_provider: str
    global_ai_model: str | None = None
    global_ai_base_url: str | None = None
    ai_limit_per_user: str
    session_length: int = 24
    session_unit: str = "hours"
    session_reset_on_activity: bool = True
    max_exercise_questions: int = 500
    unnecessary_logins_enabled: bool = False
    backup_enabled: bool = True
    backup_retention_days: int = 7

    class Config:
        from_attributes = True


class GlobalPromptBase(BaseModel):
    name: str
    content: str
    icon: str | None = "IconFileText"


class GlobalPromptCreate(GlobalPromptBase):
    pass


class GlobalPromptUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    icon: str | None = None


class GlobalPromptSchema(GlobalPromptBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserInvitationCreate(BaseModel):
    email: EmailStr | None = None
    tier: str = "free"
    send_email: bool = True
    label: str | None = None

    @model_validator(mode="after")
    def ensure_email_when_sending(self):
        if self.send_email and not self.email:
            raise ValueError("Email is required when sending an invitation email.")
        return self


class UserInvitationUpdate(BaseModel):
    label: str | None = None


class UserInvitationResponse(BaseModel):
    id: int
    email: str
    token: str
    invited_by: int
    tier: str
    label: str | None = None
    is_used: bool
    used_by: int | None = None
    accepted_by_email: str | None = None
    accepted_by_name: str | None = None
    expires_at: datetime
    created_at: datetime
    send_email: bool = False
    invitation_link: str | None = None

    class Config:
        from_attributes = True


class EmailConfigSchema(BaseModel):
    smtp_provider: str | None = None
    email_address: str | None = None
    sender_name: str | None = None
    app_password: str | None = None

    class Config:
        from_attributes = True


class IPFilterSchema(BaseModel):
    id: int
    filter_type: str
    rule_type: str
    value: str
    created_at: datetime

    class Config:
        from_attributes = True


class IPFilterCreate(BaseModel):
    filter_type: str
    rule_type: str
    value: str


class RateLimitConfigSchema(BaseModel):
    per_user_api: int
    global_api: int
    chat_api: int
    processing_api: int
    concurrent_tasks_per_user: int
    sessions: int

    class Config:
        from_attributes = True


class UserLogSchema(BaseModel):
    id: int
    user_id: int | None
    action: str
    ip_address: str | None
    device_info: str | None
    details: str | None
    timestamp: datetime

    class Config:
        from_attributes = True


class UserAdminResponse(User):
    # Overriding fields to plain str to allow viewing users with invalid data formats in admin
    username: str | None = None
    email: str | None = None
    full_name: str | None = None
    nickname: str | None = None
    # Extending User with extra stats
    google_oauth_id: str | None = None
    notes_count: int = 0
    subjects_count: int = 0
    groups_count: int = 0
    conversations_count: int = 0
    questions_count: int = 0
    storage_used: str = "0 MB"
    total_logins: int = 0
    total_online_time: int = 0


class UserActionRequest(BaseModel):
    user_id: int
    action: str  # deactivate, delete, reset_password, tier
    value: str | None = None


class TierConfigSchema(BaseModel):
    id: str  # unlimited, free, pro
    display_name: str
    max_resources: int = -1
    max_notes: int = -1
    max_subjects: int = -1
    max_groups: int = -1
    max_conversations: int = -1
    max_messages: int = -1
    max_storage_gb: int = -1
    max_exercises: int = -1
    # Reset periods: "week", "month", or None for cumulative
    conversations_reset_period: str | None = None
    messages_reset_period: str | None = None
    notes_reset_period: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
