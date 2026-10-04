"""
Comprehensive data migration script.

Moves all data from LEGACY (flat, pre-unified) layout to the current
user-scoped layout under data/users/{user_id}/.

Legacy layout (old):
  data/uploads/{user_id}/{file}              # uploaded resource files
  data/resources/{rs_id}.md + JSONs          # extracted content
  data/extracted_images/{rs_id}/{img}        # extracted slide images
  data/generated/{rs_id}/{output}            # generated PDF/DOCX
  data/output/{rs_id}/{output}               # older generated output
  data/notes/{nt_id}.md                      # AI-generated notes
  data/exercises/{ex_id}.json               # exercise content
  data/user_uploads/{rs_id}/{img}            # user-uploaded annotation images
  app/data/user_{uid}/{ex_id}.pdf            # ROGUE: exercise uploads (CWD bug)

New layout:
  data/users/{uid}/uploads/{file}
  data/users/{uid}/resources/{rs_id}.md + JSONs
  data/users/{uid}/extracted_images/{rs_id}/{img}
  data/users/{uid}/exports/{rs_id}/{output}
  data/users/{uid}/notes/{nt_id}.md
  data/users/{uid}/exercises/{ex_id}.json
  data/users/{uid}/user_images/{rs_id}/{img}
"""

import logging
import os
import re
import shutil
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.paths import (
    DATA_DIR,
    USERS_DIR,
    LEGACY_UPLOADS_DIR,
    LEGACY_GENERATED_DIR,
    LEGACY_OUTPUT_DIR,
    LEGACY_RESOURCES_DIR,
    LEGACY_EXTRACTED_IMAGES_DIR,
)

logger = logging.getLogger(__name__)

# Rogue directory: app/data/user_{uid}/ (created by exercises.py CWD bug)
APP_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "data")


def move(src: str, dst: str, description: str = ""):
    """Move a file or directory from src to dst. Skip if src missing or dst exists."""
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        logger.warning(f"SKIP (dest exists): {src} -> {dst}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    label = description or os.path.basename(src)
    logger.info(f"Moved {label}: {src} -> {dst}")


def migrate_resource_content(db, resource):
    """Migrate a single resource's content files from legacy dirs."""
    uid = str(resource.user_id)
    rid = resource.id

    # -- resources (extracted markdown + JSONs) --
    user_res_dir = os.path.join(USERS_DIR, uid, "resources")
    for ext in ["md", "json"]:
        for suffix in ["", "_structured", "_images", "_image_map", "_timings"]:
            src = os.path.join(LEGACY_RESOURCES_DIR, f"{rid}{suffix}.{ext}")
            dst = os.path.join(user_res_dir, f"{rid}{suffix}.{ext}")
            move(src, dst, f"resource {rid}{suffix}.{ext}")

    # -- extracted images --
    src_dir = os.path.join(LEGACY_EXTRACTED_IMAGES_DIR, rid)
    dst_dir = os.path.join(USERS_DIR, uid, "extracted_images", rid)
    if os.path.isdir(src_dir):
        # Move individual files to avoid directory-move conflicts
        for fname in os.listdir(src_dir):
            move(
                os.path.join(src_dir, fname),
                os.path.join(dst_dir, fname),
                f"extracted image {rid}/{fname}",
            )
        # Remove empty source dir
        try:
            os.rmdir(src_dir)
        except OSError:
            pass  # not empty, leave it

    # -- generated exports (PDF/DOCX) --
    for legacy_dir in [LEGACY_GENERATED_DIR, LEGACY_OUTPUT_DIR]:
        src_dir = os.path.join(legacy_dir, rid)
        dst_dir = os.path.join(USERS_DIR, uid, "exports", rid)
        if os.path.isdir(src_dir):
            for fname in os.listdir(src_dir):
                move(
                    os.path.join(src_dir, fname),
                    os.path.join(dst_dir, fname),
                    f"export {rid}/{fname}",
                )
            try:
                os.rmdir(src_dir)
            except OSError:
                pass

    # -- user_images (legacy user_uploads) --
    old_user_img = os.path.join(DATA_DIR, "user_uploads", rid)
    new_user_img_dir = os.path.join(USERS_DIR, uid, "user_images", rid)
    if os.path.isdir(old_user_img):
        for fname in os.listdir(old_user_img):
            move(
                os.path.join(old_user_img, fname),
                os.path.join(new_user_img_dir, fname),
                f"user image {rid}/{fname}",
            )
        try:
            os.rmdir(old_user_img)
        except OSError:
            pass

    # -- fix upload file_path in DB --
    if resource.file_path and "data/users" not in resource.file_path:
        # Old path like: .../data/uploads/{uid}/{filename}
        # Extract the filename and build new path
        old_path = resource.file_path
        filename = os.path.basename(old_path)
        new_path = os.path.join(USERS_DIR, uid, "uploads", filename)

        # Also move the actual file if it's still at the old location
        if os.path.exists(old_path) and not os.path.exists(new_path):
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.move(old_path, new_path)
            logger.info(f"Moved upload: {old_path} -> {new_path}")

        resource.file_path = new_path


def migrate_uploads():
    """Migrate legacy data/uploads/{uid}/* → data/users/{uid}/uploads/* and fix DB paths."""
    from app.utils.db import SessionLocal
    from app.models.db import Resource

    if not os.path.isdir(LEGACY_UPLOADS_DIR):
        return

    with SessionLocal() as db:
        for uid_str in os.listdir(LEGACY_UPLOADS_DIR):
            legacy_upload_dir = os.path.join(LEGACY_UPLOADS_DIR, uid_str)
            if not os.path.isdir(legacy_upload_dir):
                continue

            new_upload_dir = os.path.join(USERS_DIR, uid_str, "uploads")
            os.makedirs(new_upload_dir, exist_ok=True)

            for fname in os.listdir(legacy_upload_dir):
                src = os.path.join(legacy_upload_dir, fname)
                dst = os.path.join(new_upload_dir, fname)
                if os.path.isfile(src):
                    move(src, dst, f"upload {fname}")

            # Remove empty legacy upload dir
            try:
                os.rmdir(legacy_upload_dir)
            except OSError:
                pass

        # Fix resource.file_path for any remaining old-style paths
        for resource in db.query(Resource).all():
            if resource.file_path and "data/users" not in resource.file_path:
                filename = os.path.basename(resource.file_path)
                new_path = os.path.join(USERS_DIR, str(resource.user_id), "uploads", filename)
                resource.file_path = new_path
                logger.info(f"Fixed DB path: {resource.id} -> {new_path}")

        db.commit()


def migrate_rogue_exercise_uploads():
    """Move rogue app/data/user_{uid}/* → data/users/{uid}/uploads/exercises/"""
    if not os.path.isdir(APP_DATA_DIR):
        return

    for entry in os.listdir(APP_DATA_DIR):
        if not entry.startswith("user_"):
            continue
        uid = entry.replace("user_", "")
        src_dir = os.path.join(APP_DATA_DIR, entry)
        if not os.path.isdir(src_dir):
            continue

        dst_dir = os.path.join(USERS_DIR, uid, "uploads")
        os.makedirs(dst_dir, exist_ok=True)

        for fname in os.listdir(src_dir):
            move(
                os.path.join(src_dir, fname),
                os.path.join(dst_dir, fname),
                f"rogue exercise upload {fname}",
            )

        try:
            os.rmdir(src_dir)
            logger.info(f"Removed empty rogue dir: {src_dir}")
        except OSError:
            pass

    # Remove app/data dir if empty
    try:
        os.rmdir(APP_DATA_DIR)
        logger.info(f"Removed empty: {APP_DATA_DIR}")
    except OSError:
        pass


def migrate_notes(db):
    """Migrate legacy data/notes/* → data/users/{uid}/notes/"""
    if not os.path.isdir(os.path.join(DATA_DIR, "notes")):
        return

    from app.models.db import Note, Resource

    for n in db.query(Note).all():
        r = db.query(Resource).filter(Resource.id == n.resource_id).first()
        if not r:
            continue
        uid = str(r.user_id)
        user_notes_dir = os.path.join(USERS_DIR, uid, "notes")

        for suffix in ["", "_quickread"]:
            src = os.path.join(DATA_DIR, "notes", f"{n.id}{suffix}.md")
            dst = os.path.join(user_notes_dir, f"{n.id}{suffix}.md")
            move(src, dst, f"note {n.id}{suffix}.md")

        # Fix DB paths
        if n.output_pdf_path and "data/users" not in n.output_pdf_path:
            old = n.output_pdf_path
            n.output_pdf_path = old.replace("data/generated", f"data/users/{uid}/exports").replace(
                "data/output", f"data/users/{uid}/exports"
            )
        if n.output_docx_path and "data/users" not in n.output_docx_path:
            old = n.output_docx_path
            n.output_docx_path = old.replace(
                "data/generated", f"data/users/{uid}/exports"
            ).replace("data/output", f"data/users/{uid}/exports")


def migrate_exercises(db):
    """Migrate legacy data/exercises/* → data/users/{uid}/exercises/"""
    legacy_ex_dir = os.path.join(DATA_DIR, "exercises")
    if not os.path.isdir(legacy_ex_dir):
        return

    from app.models.db import Exercise, Resource

    for e in db.query(Exercise).all():
        r = db.query(Resource).filter(Resource.id == e.resource_id).first()
        if not r:
            continue
        uid = str(r.user_id)
        user_ex_dir = os.path.join(USERS_DIR, uid, "exercises")
        os.makedirs(user_ex_dir, exist_ok=True)

        for fname in os.listdir(legacy_ex_dir):
            if fname.startswith(e.id):
                move(
                    os.path.join(legacy_ex_dir, fname),
                    os.path.join(user_ex_dir, fname),
                    f"exercise {fname}",
                )


def cleanup_orphans(db):
    """Remove orphaned files in legacy dirs for resources NOT in the DB."""
    from app.models.db import Resource
    known_ids = {r.id for r in db.query(Resource.id).all()}

    # Orphan resource content files (data/resources/{rs_id}.*)
    if os.path.isdir(LEGACY_RESOURCES_DIR):
        _RS_ID = re.compile(r"^(rs_[a-f0-9]+)")
        for fname in os.listdir(LEGACY_RESOURCES_DIR):
            m = _RS_ID.match(fname)
            if m and m.group(1) not in known_ids:
                path = os.path.join(LEGACY_RESOURCES_DIR, fname)
                os.remove(path)
                logger.info(f"Removed orphan: {path}")

    # Orphan extracted image dirs (data/extracted_images/{rs_id}/)
    if os.path.isdir(LEGACY_EXTRACTED_IMAGES_DIR):
        for entry in os.listdir(LEGACY_EXTRACTED_IMAGES_DIR):
            if entry.startswith("rs_") and entry not in known_ids:
                path = os.path.join(LEGACY_EXTRACTED_IMAGES_DIR, entry)
                shutil.rmtree(path, ignore_errors=True)
                logger.info(f"Removed orphan dir: {path}")


def cleanup_empty_legacy_dirs():
    """Remove empty legacy top-level directories."""
    legacy_dirs = [
        LEGACY_UPLOADS_DIR,
        LEGACY_RESOURCES_DIR,
        LEGACY_EXTRACTED_IMAGES_DIR,
        LEGACY_GENERATED_DIR,
        LEGACY_OUTPUT_DIR,
        os.path.join(DATA_DIR, "notes"),
        os.path.join(DATA_DIR, "exercises"),
        os.path.join(DATA_DIR, "user_uploads"),
    ]
    for d in legacy_dirs:
        try:
            if os.path.isdir(d):
                if not os.listdir(d):
                    os.rmdir(d)
                    logger.info(f"Removed empty legacy dir: {d}")
        except OSError as e:
            logger.warning(f"Could not remove {d}: {e}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    logger.info("=== Phase 3: Data Migration ===")
    logger.info(f"  DATA_DIR = {DATA_DIR}")
    logger.info(f"  USERS_DIR = {USERS_DIR}")
    logger.info(f"  APP_DATA_DIR = {APP_DATA_DIR}")
    logger.info("")

    # -- Step 1: Migrate rogue exercise uploads --
    logger.info("--- Step 1: Migrate rogue exercise uploads ---")
    migrate_rogue_exercise_uploads()

    # -- Step 2: Migrate legacy uploads and fix DB paths --
    logger.info("--- Step 2: Migrate legacy uploads ---")
    migrate_uploads()

    # -- Step 3: Migrate resource content, images, exports --
    logger.info("--- Step 3: Migrate resource content ---")
    from app.utils.db import SessionLocal
    from app.models.db import Resource

    with SessionLocal() as db:
        for resource in db.query(Resource).all():
            migrate_resource_content(db, resource)
        db.commit()

        # -- Step 4: Migrate notes --
        logger.info("--- Step 4: Migrate notes ---")
        migrate_notes(db)
        db.commit()

        # -- Step 5: Migrate exercises --
        logger.info("--- Step 5: Migrate exercises ---")
        migrate_exercises(db)
        db.commit()

        # -- Step 6: Remove orphan files (not in DB) --
        logger.info("--- Step 6: Remove orphan files ---")
        cleanup_orphans(db)

    # -- Step 7: Clean up empty legacy dirs --
    logger.info("--- Step 7: Clean up empty legacy dirs ---")
    cleanup_empty_legacy_dirs()

    logger.info("")
    logger.info("=== Migration complete ===")


if __name__ == "__main__":
    main()
