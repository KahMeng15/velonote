"""Database utilities and session management"""

import logging
import os
import uuid
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models.db import Base

logger = logging.getLogger(__name__)

settings = get_settings()


# Create engine
engine_kwargs = {
    "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
    "pool_size": settings.DB_POOL_SIZE,
    "max_overflow": settings.DB_MAX_OVERFLOW,
    "pool_timeout": settings.DB_POOL_TIMEOUT_SECONDS,
    "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
    "pool_pre_ping": True,
}

logger.info("Creating SQLAlchemy engine for PostgreSQL...")
engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def generate_random_id(db: Session, model, length: int = 8) -> str:
    """Generate a unique hex-based ID with model-specific prefix.

    Args:
        db: Database session
        model: SQLAlchemy model class to check for ID uniqueness
        length: Number of hex digits to include (default 8)

    Returns:
        A unique prefixed hex ID derived from UUID4
    """
    from app.models.db import ChatMessage, Exercise, Note, Resource, Subject, SubjectGroup

    prefix = ""
    if model == SubjectGroup:
        prefix = "gp_"
    elif model == Subject:
        prefix = "sj_"
    elif model == Resource:
        prefix = "rs_"
    elif model == Note:
        prefix = "nt_"
    elif model == Exercise:
        prefix = "ex_"
    elif model == ChatMessage:
        prefix = "mg_"

    while True:
        needed_chars = length
        random_chunks = []
        while needed_chars > 0:
            random_chunks.append(uuid.uuid4().hex)
            needed_chars -= 32
        random_part = "".join(random_chunks)[:length]
        new_id = f"{prefix}{random_part}"
        if not db.query(model).filter(model.id == new_id).first():
            return new_id
        length += 1


def generate_conversation_id(db: Session, length: int = 8) -> str:
    """Generate a unique conversation ID with 'cv_' prefix.

    Checks against ChatMessage.conversation_id for uniqueness.
    """
    from app.models.db import ChatMessage

    prefix = "cv_"

    while True:
        needed_chars = length
        random_chunks = []
        while needed_chars > 0:
            random_chunks.append(uuid.uuid4().hex)
            needed_chars -= 32
        random_part = "".join(random_chunks)[:length]
        new_id = f"{prefix}{random_part}"
        # Check uniqueness against conversation_id column
        if not db.query(ChatMessage).filter(ChatMessage.conversation_id == new_id).first():
            return new_id
        length += 1


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database with tables and apply simple migrations"""
    logger.info("Initializing database...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}", exc_info=True)
        raise

    # Apply migrations for type changes (e.g. ChatMessage ID change)
    try:
        apply_postgresql_migrations()
        apply_postgresql_user_security_migrations()
        apply_content_dissociation_migrations()
        apply_note_resource_ids_migration()
        apply_note_exercise_ids_migration()
        apply_backup_settings_migration()
        apply_invitation_label_migration()
        apply_chat_exercise_id_migration()
        apply_exercise_marks_migration()
        apply_conversation_preferences_migration()
        apply_invitation_email_unique_migration()
    except Exception as e:
        logger.error(f"Failed to apply PostgreSQL migrations: {e}")

    # Recover tasks stuck in "running" status from a previous server crash
    try:
        apply_stuck_tasks_recovery()
    except Exception as e:
        logger.error(f"Failed to recover stuck tasks: {e}")

    logger.info("Database initialized successfully")


def apply_conversation_preferences_migration():
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            # Check for conv_response_mode
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='conv_response_mode'"))
            if not res.fetchone():
                logger.info("Adding conv_response_mode to users table")
                conn.execute(text("ALTER TABLE users ADD COLUMN conv_response_mode VARCHAR(50) DEFAULT 'voice'"))

            # Check for conv_input_mode
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='conv_input_mode'"))
            if not res.fetchone():
                logger.info("Adding conv_input_mode to users table")
                conn.execute(text("ALTER TABLE users ADD COLUMN conv_input_mode VARCHAR(50) DEFAULT 'push'"))

            # Check for conv_transcription_enabled
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='conv_transcription_enabled'"))
            if not res.fetchone():
                logger.info("Adding conv_transcription_enabled to users table")
                conn.execute(text("ALTER TABLE users ADD COLUMN conv_transcription_enabled BOOLEAN DEFAULT true"))

            # Check for conv_grading_mode
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='conv_grading_mode'"))
            if not res.fetchone():
                logger.info("Adding conv_grading_mode to users table")
                conn.execute(text("ALTER TABLE users ADD COLUMN conv_grading_mode VARCHAR(50) DEFAULT 'lenient'"))
    except Exception as e:
        logger.error(f"Failed to migrate conversation preferences: {e}")

def apply_content_dissociation_migrations():
    """Programmatically alter constraints and nullability for account deletion logic"""
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            # 1. Tables where user_id should be NULLABLE for dissociation (SET NULL)
            dissociate_tables = [
                "subject_groups",
                "subjects",
                "resources",
                "chat_messages",
                "resource_snapshots",
                "export_templates",
                "exercises",
            ]

            for table in dissociate_tables:
                # Check if column is NOT NULL
                res = conn.execute(
                    text("""
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = :table AND column_name = 'user_id'
                """),
                    {"table": table},
                ).fetchone()

                if res and res[0] == "NO":
                    logger.info(f"Migration: Making {table}.user_id NULLABLE...")
                    conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN user_id DROP NOT NULL'))

                # Update Foreign Key to ON DELETE SET NULL
                # First find current constraint name
                fk_res = conn.execute(
                    text("""
                    SELECT conname
                    FROM pg_constraint c
                    JOIN pg_class r ON c.conrelid = r.oid
                    WHERE r.relname = :table AND c.contype = 'f'
                    AND pg_get_constraintdef(c.oid) LIKE '%user_id%REFERENCES users%'
                """),
                    {"table": table},
                ).fetchone()

                if fk_res:
                    fk_name = fk_res[0]
                    # Check if it already has SET NULL
                    def_res = conn.execute(
                        text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :fk_name"
                        ),
                        {"fk_name": fk_name},
                    ).fetchone()
                    if def_res and "SET NULL" not in def_res[0]:
                        logger.info(
                            f"Migration: Updating {table} FK {fk_name} to ON DELETE SET NULL..."
                        )
                        conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{fk_name}"'))
                        conn.execute(
                            text(
                                f'ALTER TABLE "{table}" ADD CONSTRAINT "{fk_name}" FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL'
                            )
                        )

            # 2. Tables where data should be CASCADED (Security/Logs/Sessions)
            cascade_tables = [
                "user_logs",
                "tasks",
                "study_sessions",
                "user_invitations",
                "password_reset_tokens",
                "email_verification_tokens",
                "password_change_confirmations",
            ]

            for table in cascade_tables:
                # Find FK to users table
                fk_res = conn.execute(
                    text("""
                    SELECT conname
                    FROM pg_constraint c
                    JOIN pg_class r ON c.conrelid = r.oid
                    WHERE r.relname = :table AND c.contype = 'f'
                    AND (pg_get_constraintdef(c.oid) LIKE '%user_id%REFERENCES users%'
                         OR pg_get_constraintdef(c.oid) LIKE '%invited_by%REFERENCES users%'
                         OR pg_get_constraintdef(c.oid) LIKE '%used_by%REFERENCES users%')
                """),
                    {"table": table},
                ).all()

                for row in fk_res:
                    fk_name = row[0]
                    # Check definition
                    def_res = conn.execute(
                        text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :fk_name"
                        ),
                        {"fk_name": fk_name},
                    ).fetchone()
                    if def_res and "CASCADE" not in def_res[0]:
                        logger.info(
                            f"Migration: Updating {table} FK {fk_name} to ON DELETE CASCADE..."
                        )

                        # Get full definition to know which column it is
                        full_def = def_res[0]
                        col_start = full_def.find("(") + 1
                        col_end = full_def.find(")")
                        column = full_def[col_start:col_end]

                        conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{fk_name}"'))
                        conn.execute(
                            text(
                                f'ALTER TABLE "{table}" ADD CONSTRAINT "{fk_name}" FOREIGN KEY ({column}) REFERENCES users(id) ON DELETE CASCADE'
                            )
                        )

        logger.info("Dissociation migrations applied successfully")
    except Exception as e:
        logger.error(f"Dissociation migration failed: {e}", exc_info=True)


def apply_postgresql_migrations():
    """Apply migrations specific to PostgreSQL (e.g. changing column types)"""
    from sqlalchemy import text

    try:
        # Check first without a heavy transaction
        with engine.connect() as conn:
            res = conn.execute(
                text("""
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'chat_messages' AND column_name = 'id'
            """)
            ).fetchone()

            needs_migration = res and res[0].lower() in ("integer", "bigint", "numeric")

        if needs_migration:
            logger.info(
                f"Migrating chat_messages table to use string IDs (current type: {res[0]})..."
            )

            # Now run migration in a proper transaction
            with engine.begin() as conn:
                # Find and drop all foreign keys pointing TO or FROM chat_messages
                fk_res = conn.execute(
                    text("""
                    SELECT conname, r.relname
                    FROM pg_constraint c
                    JOIN pg_class r ON c.conrelid = r.oid
                    WHERE r.relname = 'chat_messages' AND c.contype = 'f'
                """)
                ).all()

                for row in fk_res:
                    logger.info(f"Dropping constraint {row[0]} on {row[1]}")
                    conn.execute(
                        text(f'ALTER TABLE "{row[1]}" DROP CONSTRAINT IF EXISTS "{row[0]}"')
                    )

                fk_ref_res = conn.execute(
                    text("""
                    SELECT conname, r.relname
                    FROM pg_constraint c
                    JOIN pg_class r ON c.conrelid = r.oid
                    JOIN pg_class t ON c.confrelid = t.oid
                    WHERE t.relname = 'chat_messages' AND c.contype = 'f'
                """)
                ).all()

                for row in fk_ref_res:
                    logger.info(f"Dropping external constraint {row[0]} on {row[1]}")
                    conn.execute(
                        text(f'ALTER TABLE "{row[1]}" DROP CONSTRAINT IF EXISTS "{row[0]}"')
                    )

                # Change column types with explicit casting
                logger.info("Altering column types...")
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ALTER COLUMN id TYPE VARCHAR(16) USING id::varchar"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ALTER COLUMN reply_to_message_id TYPE VARCHAR(16) USING reply_to_message_id::varchar"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ALTER COLUMN conversation_id TYPE VARCHAR(64) USING conversation_id::varchar"
                    )
                )

                # Remove default nextval (sequence)
                conn.execute(text("ALTER TABLE chat_messages ALTER COLUMN id DROP DEFAULT"))

                # Restore constraints
                logger.info("Restoring constraints...")
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_reply_to_message_id_fkey FOREIGN KEY (reply_to_message_id) REFERENCES chat_messages(id)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES resources(id)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES subjects(id)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_group_id_fkey FOREIGN KEY (group_id) REFERENCES subject_groups(id)"
                    )
                )

            logger.info("Successfully migrated chat_messages to string IDs")
    except Exception as e:
        logger.error(f"PostgreSQL migration failed: {e}", exc_info=True)


def apply_postgresql_user_security_migrations():
    """Add security-related columns to users table if they are missing"""
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            # Check for failed_login_attempts
            res = conn.execute(
                text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'failed_login_attempts'
            """)
            ).fetchone()

            if not res:
                logger.info("Adding failed_login_attempts column to users table...")
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0 NOT NULL"
                    )
                )

            # Check for locked_until
            res = conn.execute(
                text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'locked_until'
            """)
            ).fetchone()

            if not res:
                logger.info("Adding locked_until column to users table...")
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN locked_until TIMESTAMP WITHOUT TIME ZONE")
                )

            # Check for is_verified
            res = conn.execute(
                text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'is_verified'
            """)
            ).fetchone()

            if not res:
                logger.info("Adding is_verified column to users table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE"))
                # Existing users might already be "verified" by virtue of being active
                conn.execute(text("UPDATE users SET is_verified = TRUE WHERE is_active = TRUE"))

        logger.info("PostgreSQL user security migrations applied successfully")
    except Exception as e:
        logger.error(f"PostgreSQL user security migration failed: {e}", exc_info=True)


def apply_note_resource_ids_migration():
    """Add resource_ids column to notes table if it doesn't exist"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'notes' AND column_name = 'resource_ids'"
                )
            )
            if not result.fetchone():
                conn.execute(text("ALTER TABLE notes ADD COLUMN resource_ids TEXT"))
                conn.commit()
                logger.info("Added resource_ids column to notes table")
            else:
                logger.info("resource_ids column already exists in notes table")
    except Exception as e:
        logger.error(f"Failed to add resource_ids column: {e}", exc_info=True)


def apply_note_exercise_ids_migration():
    """Add exercise_ids and user_id columns to notes table, and make resource_id nullable"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            # Add exercise_ids column
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'notes' AND column_name = 'exercise_ids'"
                )
            )
            if not result.fetchone():
                conn.execute(text("ALTER TABLE notes ADD COLUMN exercise_ids TEXT"))
                logger.info("Added exercise_ids column to notes table")
            else:
                logger.info("exercise_ids column already exists in notes table")

            # Add user_id column
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'notes' AND column_name = 'user_id'"
                )
            )
            if not result.fetchone():
                conn.execute(
                    text(
                        "ALTER TABLE notes ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
                    )
                )
                logger.info("Added user_id column to notes table")
            else:
                logger.info("user_id column already exists in notes table")

            # Make resource_id nullable (in case it wasn't)
            result = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'notes' AND column_name = 'resource_id'"
                )
            )
            if result:
                row = result.fetchone()
                if row and row[0] == "NO":
                    conn.execute(text("ALTER TABLE notes ALTER COLUMN resource_id DROP NOT NULL"))
                    logger.info("Made resource_id nullable in notes table")
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to add exercise_ids/user_id columns: {e}", exc_info=True)


def apply_stuck_tasks_recovery():
    """
    Reset tasks stuck in 'running' status back to 'pending' so they can be
    picked up by the worker again after a server crash.
    """
    from app.models.db import Task

    try:
        db = SessionLocal()
        try:
            stuck = db.query(Task).filter(Task.status == "running").all()
            if stuck:
                logger.warning(
                    f"Found {len(stuck)} task(s) stuck in 'running' status "
                    f"(likely from a prior crash). Resetting to 'pending'."
                )
                for task in stuck:
                    task.status = "pending"
                    task.error_message = "Recovered from stuck state (server restart)"
                db.commit()
            else:
                logger.info("No stuck tasks found")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to recover stuck tasks: {e}", exc_info=True)


def drop_all_tables():
    """Drop all tables (use with caution)"""
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.warning("All tables dropped")


def apply_backup_settings_migration():
    """Add backup settings columns to system_settings table"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            for col in ("backup_enabled", "backup_retention_days"):
                result = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'system_settings' AND column_name = :col"
                    ),
                    {"col": col},
                )
                if not result.fetchone():
                    if col == "backup_enabled":
                        conn.execute(
                            text(
                                "ALTER TABLE system_settings ADD COLUMN backup_enabled BOOLEAN DEFAULT TRUE"
                            )
                        )
                    else:
                        conn.execute(
                            text(
                                "ALTER TABLE system_settings ADD COLUMN backup_retention_days INTEGER DEFAULT 7"
                            )
                        )
                    logger.info(f"Added {col} column to system_settings table")
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to apply backup settings migration: {e}", exc_info=True)


def apply_invitation_label_migration():
    """Add label column to user_invitations table"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'user_invitations' AND column_name = 'label'"
                )
            )
            if not result.fetchone():
                conn.execute(text("ALTER TABLE user_invitations ADD COLUMN label VARCHAR(255)"))
                logger.info("Added label column to user_invitations table")
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to apply invitation label migration: {e}", exc_info=True)


def apply_chat_exercise_id_migration():
    """Add exercise_id column to chat_messages table"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'chat_messages' AND column_name = 'exercise_id'"
                )
            )
            if not result.fetchone():
                conn.execute(
                    text(
                        "ALTER TABLE chat_messages ADD COLUMN exercise_id VARCHAR(16) "
                        "REFERENCES exercises(id) ON DELETE SET NULL"
                    )
                )
                logger.info("Added exercise_id column to chat_messages table")
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to apply chat exercise_id migration: {e}", exc_info=True)


def apply_exercise_marks_migration():
    """Add marks columns to study_sessions table"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            for col in ["total_marks", "awarded_marks"]:
                result = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'study_sessions' AND column_name = :col"
                    ),
                    {"col": col},
                )
                if not result.fetchone():
                    conn.execute(
                        text(
                            f"ALTER TABLE study_sessions ADD COLUMN {col} INTEGER DEFAULT 0"
                        )
                    )
                    logger.info(f"Added {col} column to study_sessions table")
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'study_sessions' AND column_name = 'question_scores'"
                )
            )
            if not result.fetchone():
                conn.execute(
                    text(
                        "ALTER TABLE study_sessions ADD COLUMN question_scores JSON"
                    )
                )
                logger.info("Added question_scores column to study_sessions table")
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'study_sessions' AND column_name = 'exercise_id'"
                )
            )
            if not result.fetchone():
                conn.execute(
                    text(
                        "ALTER TABLE study_sessions ADD COLUMN exercise_id VARCHAR(16) "
                        "REFERENCES exercises(id) ON DELETE SET NULL"
                    )
                )
                logger.info("Added exercise_id column to study_sessions table")
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to apply exercise marks migration: {e}", exc_info=True)


def apply_invitation_email_unique_migration():
    """Drop global UNIQUE constraint on user_invitations.email.

    Replaces it with a partial unique index that only enforces uniqueness for
    active (unused) invites — allowing admins to re-invite the same email
    address after their previous invite has already been used.
    """
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            # 1. Drop the global unique constraint / index if it still exists.
            #    PostgreSQL exposes unique constraints as indexes, so we try both
            #    the constraint name and the auto-generated index name.
            for obj_name in (
                "user_invitations_email_key",  # auto-generated unique constraint
                "ix_user_invitations_email",   # SQLAlchemy-generated unique index
            ):
                try:
                    conn.execute(text(f"ALTER TABLE user_invitations DROP CONSTRAINT IF EXISTS {obj_name}"))
                    conn.execute(text(f"DROP INDEX IF EXISTS {obj_name}"))
                except Exception:
                    pass  # constraint / index may not exist under this name

            # 2. Re-create a non-unique plain index for lookup performance
            #    (CREATE INDEX IF NOT EXISTS is idempotent).
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_user_invitations_email "
                    "ON user_invitations (email)"
                )
            )

            # 3. Add a partial unique index so that at most one *active* invite
            #    can exist per email at any time.
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_invitations_email_active "
                    "ON user_invitations (email) WHERE is_used = FALSE"
                )
            )

            conn.commit()
            logger.info(
                "Replaced global UNIQUE on user_invitations.email with "
                "a partial unique index (active invites only)"
            )
    except Exception as e:
        logger.error(f"Failed to apply invitation email unique migration: {e}", exc_info=True)
