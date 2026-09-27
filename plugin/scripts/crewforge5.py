#!/usr/bin/env python3
"""Launcher: uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" <stage> <action> [arg] [--slug s]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crewforge5.cli import entry

sys.exit(entry())
