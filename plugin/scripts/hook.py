#!/usr/bin/env python3
"""Hook launcher: uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/hook.py" <event>  (hook JSON on stdin)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crewforge5.hooks import main

sys.exit(main(sys.argv[1:]))
