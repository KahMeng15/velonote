"""Database models"""

import logging
import os
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, relationship

logger = logging.getLogger(__name__)
Base = declarative_base()


class User(Base):
    """User accounts"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    nickname = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=True)  # Manual approval flow
    is_verified = Column(Boolean, default=False)  # Email verification flow
    tier = Column(String(50), default="free")  # free, pro, etc.
    ai_provider = Column(
        String(50), default="gemini"
    )  # gemini, chatgpt, claude, huggingface, openrouter, local
    ai_model = Column(String(100), nullable=True)
    ai_base_url = Column(String(255), nullable=True)
    use_global_ai_config = Column(
        Boolean, default=True
    )  # Whether to use global settings instead of personal
    google_oauth_id = Column(
        String(255), nullable=True, unique=True
    )  # Firebase UID for Google OAuth audit trail
    token_version = Column(
        Integer, default=0, nullable=False
    )  # Increment to revoke all existing JWT sessions

    # Security/Lockout
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)

    # Pomodoro Preferences
    pomo_study_mins = Column(Integer, default=25)
    pomo_break_mins = Column(Integer, default=5)
    pomo_long_break_mins = Column(Integer, default=15)

    # UI Preferences
    nav_sidebar_open = Column(Boolean, default=True)
    action_sidebar_open = Column(Boolean, default=True)
    sort_preference = Column(String(50), default="name_asc")

    # Chat Preferences
    last_chat_context = Column(String(50), default="global")
    last_chat_ai_mode = Column(String(50), default="normal")
    last_chat_output_format = Column(String(50), default="mix")

    # Conversation Preferences
    conv_response_mode = Column(String(50), default="voice")
    conv_input_mode = Column(String(50), default="push")
    conv_transcription_enabled = Column(Boolean, default=True)
    conv_grading_mode = Column(String(50), default="lenient")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subjects = relationship("Subject", back_populates="owner")
    study_sessions = relationship(
        "StudySession", back_populates="user", cascade="all, delete-orphan"
    )
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    subject_groups = relationship("SubjectGroup", back_populates="user")


class SubjectGroup(Base):
    """Group of subjects (e.g. Semester 1)"""

    __tablename__ = "subject_groups"

    id = Column(String(16), primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="subject_groups")
    subjects = relationship("Subject", back_populates="group", cascade="all, delete-orphan")
    chat_messages = relationship(
        "ChatMessage", back_populates="group", cascade="all, delete-orphan"
    )
    exercises = relationship("Exercise", back_populates="group", cascade="all, delete-orphan")


class Subject(Base):
    """Course/Subject organization"""

    __tablename__ = "subjects"

    id = Column(String(16), primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    group_id = Column(String(16), ForeignKey("subject_groups.id"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    color = Column(String(7), default="#3b82f6")  # hex color
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="subjects")
    group = relationship("SubjectGroup", back_populates="subjects")
    resources = relationship("Resource", back_populates="subject", cascade="all, delete-orphan")
    chat_messages = relationship(
        "ChatMessage", back_populates="subject", cascade="all, delete-orphan"
    )
    exercises = relationship("Exercise", back_populates="subject", cascade="all, delete-orphan")


class Resource(Base):
    """Resource/Document"""

    __tablename__ = "resources"

    id = Column(String(16), primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject_id = Column(String(16), ForeignKey("subjects.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_name = Column(String(255))
    file_type = Column(String(128))  # pdf, pptx, image, long MIME types
    file_size = Column(Integer)
    page_count = Column(Integer, default=0)
    output_pdf_path = Column(String(512))  # Path to generated OUTPUT.pdf
    processing_time_ms = Column(Integer, nullable=True)  # Processing time in milliseconds
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")
    subject = relationship("Subject", back_populates="resources")
    notes = relationship("Note", back_populates="resource", cascade="all, delete-orphan")
    embeddings = relationship(
        "ResourceEmbedding", back_populates="resource", cascade="all, delete-orphan"
    )
    study_sessions = relationship(
        "StudySession", back_populates="resource", cascade="all, delete-orphan"
    )
    chat_messages = relationship(
        "ChatMessage", back_populates="resource", cascade="all, delete-orphan"
    )
    snapshots = relationship(
        "ResourceSnapshot", back_populates="resource", cascade="all, delete-orphan"
    )
    exercises = relationship("Exercise", back_populates="resource", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="resource", cascade="all, delete-orphan")


class ExportTemplate(Base):
    """User-defined export templates"""

    __tablename__ = "export_templates"

    id = Column(String(16), primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )  # NULL = system default
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    config = Column(JSON, nullable=False)  # Full template configuration
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")


class Note(Base):
    """Generated study notes, cheat sheets, etc."""

    __tablename__ = "notes"

    id = Column(String(16), primary_key=True)
    version = Column(Integer, nullable=False, default=1)  # v1, v2, etc. per resource
    resource_id = Column(String(16), ForeignKey("resources.id"), nullable=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    summary_type = Column(String(50))  # cheatsheet, exercise, summary
    title = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    mode = Column(String(50), nullable=True)  # elaborate, quick, simple, eli5
    output_format = Column(String(50), nullable=True)  # sentence, pointform, numbered_list, table
    processing_method = Column(String(50), nullable=True)  # whole, section
    split_level = Column(
        String(10), nullable=True
    )  # h1, h2, h3 - header level for section splitting
    custom_prompt = Column(Text, nullable=True)  # Used for single parameter generation
    prompt_name = Column(String(255), nullable=True)
    prompt_icon = Column(String(50), nullable=True)
    processing_time = Column(Float, nullable=True)  # Processing time in seconds (legacy)
    processing_time_ms = Column(Integer, nullable=True)  # Processing time in milliseconds
    model = Column(String(100), nullable=True)  # AI model used
    is_user_edited = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resource_ids = Column(Text, nullable=True)
    exercise_ids = Column(Text, nullable=True)

    # Relationships
    resource = relationship("Resource", back_populates="notes")


class ResourceEmbedding(Base):
    """Pre-computed embeddings for resource chunks (vector DB)"""

    __tablename__ = "resource_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(String(16), ForeignKey("resources.id"), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)  # Original text of this chunk
    chunk_index = Column(Integer, nullable=False)  # Order of this chunk in resource
    embedding = Column(JSON, nullable=False)  # Embedding vector as list of floats
    position = Column(Integer)  # Character position in original text
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    resource = relationship("Resource", back_populates="embeddings")


class Exercise(Base):
    """Uploaded and Generated Exercises"""

    __tablename__ = "exercises"

    id = Column(String(16), primary_key=True)  # Will start with 'ex_'
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title = Column(String(255), nullable=False)

    # Can be linked to a group, subject, or a specific resource (if generated from one)
    group_id = Column(String(16), ForeignKey("subject_groups.id"), nullable=True, index=True)
    subject_id = Column(String(16), ForeignKey("subjects.id"), nullable=True, index=True)
    resource_id = Column(String(16), ForeignKey("resources.id"), nullable=True, index=True)

    # Source file info if uploaded
    file_path = Column(String(512), nullable=True)
    file_name = Column(String(255), nullable=True)
    content_path = Column(String(512), nullable=True)  # Path to the generated JSON file

    model = Column(String(100), nullable=True)  # AI model used if generated/parsed
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")
    group = relationship("SubjectGroup", back_populates="exercises")
    subject = relationship("Subject", back_populates="exercises")
    resource = relationship("Resource", back_populates="exercises")


class StudySession(Base):
    """Study session tracking"""

    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_id = Column(
        String(16), ForeignKey("exercises.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resource_id = Column(
        String(16), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_type = Column(String(50))  # exercise, chat, pomodoro_study, pomodoro_break, stopwatch
    duration_minutes = Column(Integer)
    questions_attempted = Column(Integer, default=0)
    questions_correct = Column(Integer, default=0)
    score = Column(Float)
    total_marks = Column(Integer, default=0)
    awarded_marks = Column(Integer, default=0)
    question_scores = Column(JSON, nullable=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    status = Column(String(50), default="completed")  # completed, interrupted
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="study_sessions")
    exercise = relationship("Exercise")
    resource = relationship("Resource", back_populates="study_sessions")


class Task(Base):
    """Background tasks tracking"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(128), unique=True, nullable=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_type = Column(String(100))  # ocr, embedding, generation
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    progress = Column(Integer, default=0)
    input_data = Column(Text)  # JSON
    result = Column(Text)  # JSON
    error_message = Column(Text)
    message = Column(Text)  # Status message for the progress bar
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="tasks")


class ChatMessage(Base):
    """Chat message history"""

    __tablename__ = "chat_messages"

    id = Column(String(16), primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resource_id = Column(
        String(16), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject_id = Column(
        String(16), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    group_id = Column(
        String(16), ForeignKey("subject_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    exercise_id = Column(
        String(16), ForeignKey("exercises.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    sources = Column(Text)  # JSON array of sources
    created_at = Column(DateTime, default=datetime.utcnow)

    # Conversation threading
    conversation_id = Column(
        String(64), nullable=True, index=True
    )  # cv_ prefix grouping messages into a conversation
    conversation_title = Column(String(255), nullable=True)  # AI-generated or derived title
    reply_to_message_id = Column(
        String(16), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )  # ID of the message being replied to
    replies = relationship(
        "ChatMessage", cascade="all, delete-orphan", backref=backref("parent", remote_side=[id])
    )
    ai_mode = Column(
        String(50), nullable=True, default="elaborate"
    )  # Which AI response mode was used
    output_format = Column(
        String(50), nullable=True, default="sentence"
    )  # Output format: sentence, pointform, numbered_list, table
    detailed_sources_json = Column(
        Text, nullable=True
    )  # JSON: full detailed source objects for history replay
    ai_model = Column(String(255), nullable=True)  # e.g. "GEMINI (gemini-1.5-flash)"
    timings_json = Column(Text, nullable=True)  # JSON: {retrieval_ms, model_ms, total_ms}
    is_pinned = Column(Boolean, default=False)
    is_favourite = Column(Boolean, default=False)
    rating = Column(Integer, nullable=True)  # 0 to 5 stars
    rating_comment = Column(Text, nullable=True)

    # Relationships
    user = relationship("User")
    resource = relationship("Resource", back_populates="chat_messages")
    subject = relationship("Subject", back_populates="chat_messages")
    group = relationship("SubjectGroup", back_populates="chat_messages")
    exercise = relationship("Exercise")


class ResourceSnapshot(Base):
    """Named snapshots of resource contents for version history"""

    __tablename__ = "resource_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(
        String(16), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")
    resource = relationship("Resource", back_populates="snapshots")


class SystemSettings(Base):
    """Global System Configuration"""

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)  # Usually just 1 row
    lockdown_mode = Column(Boolean, default=False)
    signup_config = Column(String(50), default="open")  # open, approval, invite
    maintenance_mode = Column(Boolean, default=False)
    footer_text = Column(String(255), nullable=True)
    domain_url = Column(String(255), nullable=True)  # Domain for invitation/reset links
    global_ai_provider = Column(String(50), default="gemini")
    global_ai_model = Column(String(100), nullable=True)
    global_ai_base_url = Column(String(255), nullable=True)
    ai_limit_per_user = Column(String(50), default="unlimited")  # sec, min, hour, day, unlimited

    # Session Management
    session_length = Column(Integer, default=24)
    session_unit = Column(String(20), default="hours")  # hours, days
    session_reset_on_activity = Column(Boolean, default=True)
    max_exercise_questions = Column(Integer, default=500)
    unnecessary_logins_enabled = Column(Boolean, default=False)

    # Backup Settings
    backup_enabled = Column(Boolean, default=True)
    backup_retention_days = Column(Integer, default=7)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GlobalPrompt(Base):
    """Admin-defined Global Prompts"""

    __tablename__ = "global_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    icon = Column(String(50), default="IconFileText")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserPrompt(Base):
    """User-defined Custom Prompts"""

    __tablename__ = "user_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")


class UserInvitation(Base):
    """Pending user invitations"""

    __tablename__ = "user_invitations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    token = Column(String(100), nullable=False, unique=True, index=True)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    used_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    tier = Column(String(50), default="free")
    label = Column(String(255), nullable=True)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    inviter = relationship("User", foreign_keys=[invited_by])
    accepted_by_user = relationship("User", foreign_keys=[used_by])


class PasswordResetToken(Base):
    """Password reset tokens for users who forgot their password"""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email = Column(String(255), nullable=False, index=True)
    token = Column(String(100), nullable=False, unique=True, index=True)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")


class EmailVerificationToken(Base):
    """Email verification tokens for new users"""

    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email = Column(String(255), nullable=False, index=True)
    token = Column(String(100), nullable=False, unique=True, index=True)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")


class PasswordChangeConfirmation(Base):
    """Password change confirmation tokens for users changing their password through settings"""

    __tablename__ = "password_change_confirmations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email = Column(String(255), nullable=False, index=True)
    confirmation_code = Column(String(10), nullable=False, unique=True, index=True)
    new_password_hash = Column(String(255), nullable=False)  # Hash of the new password attempt
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")


class UserLog(Base):
    """Audit logs for actions"""

    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )  # allow null for failed logins/global actions
    action = Column(
        String(100), nullable=False
    )  # login, signup, page_access, upload, processing, chat, etc.
    ip_address = Column(String(50), nullable=True)
    device_info = Column(Text, nullable=True)
    details = Column(Text, nullable=True)  # Extra info (JSON or string)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User")


class IPBlock(Base):
    """Temporary lockout for specific IP addresses due to failed logins"""

    __tablename__ = "ip_blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String(50), nullable=False, index=True, unique=True)
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IPFilter(Base):
    """IP Whitelist / Blacklist rules"""

    __tablename__ = "ip_filters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filter_type = Column(String(20), nullable=False)  # whitelist, blacklist
    rule_type = Column(String(20), nullable=False)  # country, specific_ip
    value = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RateLimitConfig(Base):
    """Specific rate limits for different modules"""

    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    per_user_api = Column(Integer, default=0)  # 0 means unlimited
    global_api = Column(Integer, default=0)
    chat_api = Column(Integer, default=0)
    processing_api = Column(Integer, default=0)
    concurrent_tasks_per_user = Column(Integer, default=1)
    sessions = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TierConfig(Base):
    """Tier configuration and limits"""

    __tablename__ = "tier_configs"

    id = Column(String(50), primary_key=True)  # unlimited, free, pro
    display_name = Column(String(100), nullable=False)  # "Unlimited", "Free", "Pro"
    max_resources = Column(Integer, default=-1)  # -1 = unlimited
    max_subjects = Column(Integer, default=-1)
    max_groups = Column(Integer, default=-1)
    max_conversations = Column(Integer, default=-1)
    max_messages = Column(Integer, default=-1)
    max_storage_gb = Column(Integer, default=-1)  # in GB, -1 = unlimited
    max_exercises = Column(Integer, default=-1)
    max_notes = Column(Integer, default=-1)
    # Reset periods: "week", "month", or None for cumulative limits
    conversations_reset_period = Column(String(20), nullable=True)  # week, month, or None
    messages_reset_period = Column(String(20), nullable=True)
    notes_reset_period = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --- Quiz Models ---
class Quiz(Base):
    """Quiz generated from a resource"""

    __tablename__ = "quizzes"

    id = Column(String(16), primary_key=True)
    title = Column(String(255), nullable=False)
    resource_id = Column(String(16), ForeignKey("resources.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    resource = relationship("Resource", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    """Questions belonging to a quiz"""

    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    quiz_id = Column(
        String(16), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    quiz = relationship("Quiz", back_populates="questions")


# --- Event Listeners for File Cleanup ---


@event.listens_for(Resource, "after_delete")
def receive_after_delete(mapper, connection, target):
    """Delete original file and generated PDF when a resource is deleted"""
    # Delete original file
    if target.file_path and os.path.exists(target.file_path):
        try:
            os.remove(target.file_path)
            logger.info(f"Deleted original file for resource {target.id}: {target.file_path}")
        except Exception as e:
            logger.warning(f"Error deleting original file for resource {target.id}: {e}")

    # Delete generated output PDF
    if target.output_pdf_path and os.path.exists(target.output_pdf_path):
        try:
            os.remove(target.output_pdf_path)
            logger.info(f"Deleted output PDF for resource {target.id}: {target.output_pdf_path}")
        except Exception as e:
            logger.warning(f"Error deleting output PDF for resource {target.id}: {e}")


@event.listens_for(Note, "after_delete")
def receive_note_after_delete(mapper, connection, target):
    """Delete the physical file associated with a note (PDF, DOCX, etc.)"""
    if target.file_path and os.path.exists(target.file_path):
        try:
            os.remove(target.file_path)
            logger.info(f"Deleted file for note {target.id}: {target.file_path}")
        except Exception as e:
            logger.warning(f"Error deleting file for note {target.id}: {e}")
