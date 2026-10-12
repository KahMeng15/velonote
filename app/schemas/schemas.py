"""Request/Response schemas"""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, Field

# Constants for validation
NICKNAME_REGEX = r"^[a-zA-Z0-9_-]+$"
FULL_NAME_REGEX = r"^[a-zA-Z\s\-\'\.]+$"

# Reusable types with validation
NicknameStr = Annotated[str, Field(min_length=2, max_length=30, pattern=NICKNAME_REGEX)]
FullNameStr = Annotated[str, Field(min_length=2, max_length=100, pattern=FULL_NAME_REGEX)]


# ========== User Schemas ==========
class UserBase(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    full_name: FullNameStr | None = None
    nickname: NicknameStr | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nickname: NicknameStr
    full_name: FullNameStr | None = None
    agree_tos: bool = False
    agree_privacy: bool = False
    agree_fair_use: bool = False


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    full_name: FullNameStr | None = None
    nickname: NicknameStr | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None  # Ignored by backend, but accepted from frontend
    use_global_ai_config: bool | None = None
    nav_sidebar_open: bool | None = None
    action_sidebar_open: bool | None = None
    sort_preference: str | None = None
    last_chat_context: str | None = None
    last_chat_ai_mode: str | None = None
    last_chat_output_format: str | None = None
    conv_response_mode: str | None = None
    conv_input_mode: str | None = None
    conv_transcription_enabled: bool | None = None
    conv_grading_mode: str | None = None


class User(UserBase):
    id: int
    is_active: bool | None = True
    is_admin: bool = False
    is_approved: bool = True
    is_verified: bool = False
    tier: str = "free"
    ai_provider: str = "gemini"
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key_configured: bool = False
    use_global_ai_config: bool = True
    nav_sidebar_open: bool = True
    action_sidebar_open: bool = True
    sort_preference: str = "name_asc"
    last_chat_context: str = "global"
    last_chat_ai_mode: str = "elaborate"
    last_chat_output_format: str = "sentence"
    conv_response_mode: str = "voice"
    conv_input_mode: str = "push"
    conv_transcription_enabled: bool = True
    conv_grading_mode: str = "lenient"
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


# ========== Subject Schemas ==========


# ========== Subject Group Schemas ==========
class SubjectGroupBase(BaseModel):
    name: str


class SubjectGroupCreate(SubjectGroupBase):
    pass


class SubjectGroupUpdate(BaseModel):
    name: str | None = None


class SubjectGroup(SubjectGroupBase):
    id: str
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ========== Subject Schemas ==========
class SubjectBase(BaseModel):
    name: str
    description: str | None = None
    color: str = "#3b82f6"
    group_id: str | None = None


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    group_id: str | None = None


class Subject(SubjectBase):
    id: str
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SubjectResponse(Subject):
    """Response schema for subject endpoints"""

    group: SubjectGroup | None = None


class SubjectGroupResponse(SubjectGroup):
    subjects: list[SubjectResponse] = []


# ========== Resource Schemas ==========
class ResourceBase(BaseModel):
    title: str
    subject_id: str


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(BaseModel):
    title: str | None = None
    subject_id: str | None = None


class Resource(ResourceBase):
    id: str
    file_path: str
    file_type: str
    file_size: int
    file_name: str
    user_id: int
    page_count: int = 0
    extracted_text: str | None = None
    extracted_content_structured: str | None = None
    extracted_images_metadata: str | None = None
    output_pdf_path: str | None = None
    processing_time_ms: int | None = None
    timings: dict | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResourceResponse(Resource):
    """Response schema for resource endpoints"""

    subject: SubjectResponse | None = None


# ========== Note Schemas ==========
class NoteBase(BaseModel):
    title: str
    summary_type: str


class Note(NoteBase):
    id: str
    resource_id: str
    file_path: str
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Study Session Schemas ==========
class StudySessionCreate(BaseModel):
    resource_id: str | None = None
    session_type: str
    duration_minutes: int
    questions_attempted: int = 0
    questions_correct: int = 0
    score: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: str | None = "completed"


class StudySession(StudySessionCreate):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Task Schemas ==========
class TaskResponse(BaseModel):
    id: int
    task_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: str | None = None
    error_message: str | None = None

    class Config:
        from_attributes = True


# ========== Chat Schemas ==========
class ChatMessage(BaseModel):
    resource_id: str
    message: str


class ChatResponse(BaseModel):
    message: str
    response: str
    sources: list[str] | None = None


# ========== Resource Snapshot Schemas ==========
class ResourceSnapshotCreate(BaseModel):
    name: str
    content: str


class ResourceSnapshotResponse(BaseModel):
    id: int
    resource_id: str
    user_id: int
    name: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Resource Content Update ==========
class ResourceContentUpdate(BaseModel):
    extracted_text: str


# ========== Export Template Schemas ==========
class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    config: Any | None = None


class TemplateDuplicate(BaseModel):
    name: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: Any | None = None


# ========== User Prompt Schemas ==========
class UserPromptCreate(BaseModel):
    name: str
    content: str


class UserPromptUpdate(BaseModel):
    name: str | None = None
    content: str | None = None


class UserPromptResponse(BaseModel):
    id: int
    user_id: int
    name: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
