#!/usr/bin/env python3
"""Run database backup directly from CLI."""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.backup import perform_db_backup

if __name__ == "__main__":
    success = perform_db_backup()
    sys.exit(0 if success else 1)
