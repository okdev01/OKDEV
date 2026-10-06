#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main entry point for OKDEV (delegates to main package)
"""

import sys
from pathlib import Path

# Ensure the project root is in sys.path for proper package resolution
# This fixes import issues when running from different directories
# Only needed in development mode (PyInstaller handles paths automatically)
if not getattr(sys, 'frozen', False):
    _project_root = Path(__file__).parent.absolute()
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# Keep packaged backend verification independent of all window/game startup.
if __name__ == '__main__' and '--hub-self-check' in sys.argv:
    from hub.selfcheck import run
    report_path = sys.argv[sys.argv.index('--hub-self-check') + 1]
    raise SystemExit(run(report_path))

# The desktop window runs separately from the game integration process.
if __name__ == '__main__' and '--guide-companion' in sys.argv:
    from hub.companion import run
    run()
    raise SystemExit(0)

if __name__ == '__main__' and '--hub' in sys.argv:
    from hub.desktop import run
    smoke_path = sys.argv[sys.argv.index('--hub-smoke') + 1] if '--hub-smoke' in sys.argv else None
    run(smoke_path)
    raise SystemExit(0)

# Import from the modularized main package
from main import main

if __name__ == "__main__":
        main()
