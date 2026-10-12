"""
Lightweight path constants — no heavy imports.
Safe to import from scripts and any context.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_DIR = os.path.join(DATA_DIR, "users")

# Legacy directories (pre-migration flat layout)
LEGACY_UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
LEGACY_GENERATED_DIR = os.path.join(DATA_DIR, "generated")
LEGACY_OUTPUT_DIR = os.path.join(DATA_DIR, "output")
LEGACY_RESOURCES_DIR = os.path.join(DATA_DIR, "resources")
LEGACY_EXTRACTED_IMAGES_DIR = os.path.join(DATA_DIR, "extracted_images")
