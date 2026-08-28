"""Command-line entry point: ``python3 -m app.aura <command>``.

Exit status:
    0   the command succeeded -- for `verify`, VERIFIED
    2   `verify`: TAMPERED
    3   `verify`: INVALID
    64  the command line could not be understood
    65  the command was understood, and the event could not be recorded
"""

from app.aura import main

if __name__ == "__main__":
    raise SystemExit(main())
