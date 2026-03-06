"""Allow running as `python -m passlock` (launches GUI) or `python -m passlock lock/unlock` (CLI)."""

import sys

if len(sys.argv) > 1 and sys.argv[1] in ("lock", "unlock", "--help", "-h", "--version"):
    from passlock.cli import main
    main()
else:
    from passlock.gui import launch_gui
    launch_gui()
