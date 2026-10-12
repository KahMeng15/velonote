"""Quota and tier limit enforcement utilities"""

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import (
    ChatMessage,
    Exercise,
    Note,
    Resource,
    Subject,
    SubjectGroup,
    TierConfig,
    User,
)

DEFAULT_TIER_CONFIGS = {
    "unlimited": {
        "display_name": "Unlimited",
        "max_resources": -1,
        "max_subjects": -1,
        "max_groups": -1,
        "max_conversations": -1,
        "max_messages": -1,
        "max_storage_gb": -1,
        "max_exercises": -1,
        "max_notes": -1,
        "conversations_reset_period": None,
        "messages_reset_period": None,
        "notes_reset_period": None,
    },
    "free": {
        "display_name": "Free",
        "max_resources": 50,
        "max_subjects": 10,
        "max_groups": 5,
        "max_conversations": 100,
        "max_messages": 500,
        "max_storage_gb": 5,
        "max_exercises": 20,
        "max_notes": 50,
        "conversations_reset_period": "month",
        "messages_reset_period": "month",
        "notes_reset_period": "month",
    },
    "pro": {
        "display_name": "Pro",
        "max_resources": 500,
        "max_subjects": 100,
        "max_groups": 50,
        "max_conversations": -1,
        "max_messages": -1,
        "max_storage_gb": 100,
        "max_exercises": 200,
        "max_notes": 500,
        "conversations_reset_period": "month",
        "messages_reset_period": "month",
        "notes_reset_period": "month",
    },
    "early_tester": {
        "display_name": "Early Tester",
        "max_resources": -1,
        "max_subjects": -1,
        "max_groups": -1,
        "max_conversations": -1,
        "max_messages": -1,
        "max_storage_gb": -1,
        "max_exercises": -1,
        "max_notes": -1,
        "conversations_reset_period": None,
        "messages_reset_period": None,
        "notes_reset_period": None,
    },
}


def ensure_default_tier_configs(db: Session):
    existing_ids = {tier.id for tier in db.query(TierConfig).all()}
    missing_tiers = [tier_id for tier_id in DEFAULT_TIER_CONFIGS if tier_id not in existing_ids]
    if not missing_tiers:
        return

    for tier_id in missing_tiers:
        data = DEFAULT_TIER_CONFIGS[tier_id]
        db.add(TierConfig(id=tier_id, **data))

    db.commit()


def ensure_tier_config_exists(tier_id: str, db: Session):
    tier = db.query(TierConfig).filter(TierConfig.id == tier_id).first()
    if tier:
        return tier

    defaults = DEFAULT_TIER_CONFIGS.get(tier_id)
    if not defaults:
        return None

    new_tier = TierConfig(id=tier_id, **defaults)
    db.add(new_tier)
    db.commit()
    db.refresh(new_tier)
    return new_tier


def get_period_start(reset_period: str) -> datetime:
    """Get the start of the current period based on reset_period type"""
    now = datetime.utcnow()

    if reset_period == "day":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif reset_period == "week":
        # Monday of current week
        days_since_monday = now.weekday()
        period_start = now - timedelta(days=days_since_monday)
        period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif reset_period == "month":
        # First day of current month
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # No reset period - return epoch (will count all time)
        period_start = datetime.utcfromtimestamp(0)

    return period_start


def get_user_tier_config(user: User, db: Session) -> TierConfig:
    """Get the tier configuration for a user"""
    tier_config = db.query(TierConfig).filter(TierConfig.id == user.tier).first()
    if not tier_config:
        tier_config = ensure_tier_config_exists(user.tier, db)
    if not tier_config:
        tier_config = db.query(TierConfig).filter(TierConfig.id == "free").first()
    return tier_config


def get_user_resource_count(user: User, db: Session) -> int:
    """Get the number of resources a user has"""
    count = db.query(func.count(Resource.id)).filter(Resource.user_id == user.id).scalar() or 0
    return count


def get_user_subject_count(user: User, db: Session) -> int:
    """Get the number of subjects a user has"""
    count = db.query(func.count(Subject.id)).filter(Subject.user_id == user.id).scalar() or 0
    return count


def get_user_group_count(user: User, db: Session) -> int:
    """Get the number of subject groups a user has"""
    count = (
        db.query(func.count(SubjectGroup.id)).filter(SubjectGroup.user_id == user.id).scalar() or 0
    )
    return count


def get_user_conversation_count(user: User, db: Session, reset_period: str | None = None) -> int:
    """Get the number of unique conversations a user has (optionally filtered by period)"""
    query = db.query(func.count(ChatMessage.conversation_id.distinct())).filter(
        ChatMessage.user_id == user.id
    )

    if reset_period:
        period_start = get_period_start(reset_period)
        query = query.filter(ChatMessage.created_at >= period_start)

    count = query.scalar() or 0
    return count


def get_user_message_count(user: User, db: Session, reset_period: str | None = None) -> int:
    """Get the total number of chat messages a user has sent (optionally filtered by period)"""
    query = db.query(func.count(ChatMessage.id)).filter(ChatMessage.user_id == user.id)

    if reset_period:
        period_start = get_period_start(reset_period)
        query = query.filter(ChatMessage.created_at >= period_start)

    count = query.scalar() or 0
    return count


def get_user_exercise_count(user: User, db: Session) -> int:
    """Get the number of exercises a user has"""
    count = db.query(func.count(Exercise.id)).filter(Exercise.user_id == user.id).scalar() or 0
    return count


def get_user_note_count(user: User, db: Session, reset_period: str | None = None) -> int:
    """Get the number of notes a user has (optionally filtered by period)"""
    query = db.query(func.count(Note.id)).filter(
        Note.resource_id.in_(db.query(Resource.id).filter(Resource.user_id == user.id))
    )

    if reset_period:
        period_start = get_period_start(reset_period)
        query = query.filter(Note.created_at >= period_start)

    count = query.scalar() or 0
    return count


def get_user_storage_used_bytes(user: User, db: Session) -> int:
    """Get total storage used by a user in bytes"""
    total_bytes = (
        db.query(func.sum(Resource.file_size)).filter(Resource.user_id == user.id).scalar() or 0
    )
    return total_bytes


def get_user_storage_used_gb(user: User, db: Session) -> float:
    """Get total storage used by a user in GB"""
    bytes_used = get_user_storage_used_bytes(user, db)
    return bytes_used / (1024 * 1024 * 1024)


def check_quota_resources(user: User, db: Session) -> bool:
    """Check if user can create another resource"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_resources == -1:  # Unlimited
        return True
    current_count = get_user_resource_count(user, db)
    return current_count < tier_config.max_resources


def check_quota_subjects(user: User, db: Session) -> bool:
    """Check if user can create another subject"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_subjects == -1:  # Unlimited
        return True
    current_count = get_user_subject_count(user, db)
    return current_count < tier_config.max_subjects


def check_quota_groups(user: User, db: Session) -> bool:
    """Check if user can create another group"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_groups == -1:  # Unlimited
        return True
    current_count = get_user_group_count(user, db)
    return current_count < tier_config.max_groups


def check_quota_conversations(user: User, db: Session) -> bool:
    """Check if user can create another conversation"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_conversations == -1:  # Unlimited
        return True
    current_count = get_user_conversation_count(user, db, tier_config.conversations_reset_period)
    return current_count < tier_config.max_conversations


def check_quota_messages(user: User, db: Session) -> bool:
    """Check if user can send another message"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_messages == -1:  # Unlimited
        return True
    current_count = get_user_message_count(user, db, tier_config.messages_reset_period)
    return current_count < tier_config.max_messages


def check_quota_exercises(user: User, db: Session) -> bool:
    """Check if user can create another exercise"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_exercises == -1:  # Unlimited
        return True
    current_count = get_user_exercise_count(user, db)
    return current_count < tier_config.max_exercises


def check_quota_notes(user: User, db: Session) -> bool:
    """Check if user can create another note"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_notes == -1:  # Unlimited
        return True
    current_count = get_user_note_count(user, db, tier_config.notes_reset_period)
    return current_count < tier_config.max_notes


def check_quota_storage(user: User, file_size_bytes: int, db: Session) -> bool:
    """Check if user can upload a file of given size"""
    tier_config = get_user_tier_config(user, db)
    if tier_config.max_storage_gb == -1:  # Unlimited
        return True

    current_usage_gb = get_user_storage_used_gb(user, db)
    max_storage_gb = tier_config.max_storage_gb
    new_usage_gb = current_usage_gb + (file_size_bytes / (1024 * 1024 * 1024))

    return new_usage_gb <= max_storage_gb


def enforce_quota_resources(user: User, db: Session):
    """Enforce resource quota - raise exception if exceeded"""
    if not check_quota_resources(user, db):
        tier_config = get_user_tier_config(user, db)
        current = get_user_resource_count(user, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Resource quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_resources} resources. You have {current}.",
        )


def enforce_quota_subjects(user: User, db: Session):
    """Enforce subject quota - raise exception if exceeded"""
    if not check_quota_subjects(user, db):
        tier_config = get_user_tier_config(user, db)
        current = get_user_subject_count(user, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Subject quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_subjects} subjects. You have {current}.",
        )


def enforce_quota_groups(user: User, db: Session):
    """Enforce group quota - raise exception if exceeded"""
    if not check_quota_groups(user, db):
        tier_config = get_user_tier_config(user, db)
        current = get_user_group_count(user, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Group quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_groups} groups. You have {current}.",
        )


def enforce_quota_conversations(user: User, db: Session):
    """Enforce conversation quota - raise exception if exceeded"""
    if not check_quota_conversations(user, db):
        tier_config = get_user_tier_config(user, db)
        current = get_user_conversation_count(user, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Conversation quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_conversations} conversations. You have {current}.",
        )


def enforce_quota_messages(user: User, db: Session):
    """Enforce message quota - raise exception if exceeded"""
    if not check_quota_messages(user, db):
        tier_config = get_user_tier_config(user, db)
        current = get_user_message_count(user, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Message quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_messages} messages. You have {current}.",
        )


def enforce_quota_exercises(user: User, db: Session):
    """Enforce exercise quota - raise exception if exceeded"""
    if not check_quota_exercises(user, db):
        tier_config = get_user_tier_config(user, db)
        current = get_user_exercise_count(user, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Exercise quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_exercises} exercises. You have {current}.",
        )


def enforce_quota_notes(user: User, db: Session):
    """Enforce note quota - raise exception if exceeded"""
    if not check_quota_notes(user, db):
        tier_config = get_user_tier_config(user, db)
        current = get_user_note_count(user, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Note quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_notes} notes. You have {current}.",
        )


def enforce_quota_storage(user: User, file_size_bytes: int, db: Session):
    """Enforce storage quota - raise exception if exceeded"""
    if not check_quota_storage(user, file_size_bytes, db):
        tier_config = get_user_tier_config(user, db)
        current_gb = get_user_storage_used_gb(user, db)
        file_size_gb = file_size_bytes / (1024 * 1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
            detail=f"Storage quota exceeded. Your {user.tier.upper()} tier allows {tier_config.max_storage_gb}GB. You've used {current_gb:.2f}GB and this file is {file_size_gb:.2f}GB.",
        )


def get_user_quota_status(user: User, db: Session) -> dict:
    """Get comprehensive quota status for a user"""
    tier_config = get_user_tier_config(user, db)

    return {
        "tier": user.tier,
        "tier_name": tier_config.display_name,
        "quotas": {
            "resources": {
                "used": get_user_resource_count(user, db),
                "limit": tier_config.max_resources,
                "unlimited": tier_config.max_resources == -1,
                "reset_period": None,
            },
            "subjects": {
                "used": get_user_subject_count(user, db),
                "limit": tier_config.max_subjects,
                "unlimited": tier_config.max_subjects == -1,
                "reset_period": None,
            },
            "groups": {
                "used": get_user_group_count(user, db),
                "limit": tier_config.max_groups,
                "unlimited": tier_config.max_groups == -1,
                "reset_period": None,
            },
            "conversations": {
                "used": get_user_conversation_count(
                    user, db, tier_config.conversations_reset_period
                ),
                "limit": tier_config.max_conversations,
                "unlimited": tier_config.max_conversations == -1,
                "reset_period": tier_config.conversations_reset_period,
            },
            "messages": {
                "used": get_user_message_count(user, db, tier_config.messages_reset_period),
                "limit": tier_config.max_messages,
                "unlimited": tier_config.max_messages == -1,
                "reset_period": tier_config.messages_reset_period,
            },
            "exercises": {
                "used": get_user_exercise_count(user, db),
                "limit": tier_config.max_exercises,
                "unlimited": tier_config.max_exercises == -1,
                "reset_period": None,
            },
            "notes": {
                "used": get_user_note_count(user, db, tier_config.notes_reset_period),
                "limit": tier_config.max_notes,
                "unlimited": tier_config.max_notes == -1,
                "reset_period": tier_config.notes_reset_period,
            },
            "storage_gb": {
                "used": round(get_user_storage_used_gb(user, db), 2),
                "limit": tier_config.max_storage_gb,
                "unlimited": tier_config.max_storage_gb == -1,
                "reset_period": None,
            },
        },
    }
