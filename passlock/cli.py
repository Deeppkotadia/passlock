#!/usr/bin/env python3
"""PassLock CLI entry point."""

import argparse
import getpass
import sys
from pathlib import Path

from passlock import __version__
from passlock.core import encrypt_file, encrypt_folder, smart_unlock


def _get_password_for_encrypt() -> str:
    pw = getpass.getpass("Enter password: ")
    if len(pw) < 4:
        raise SystemExit("Password must be at least 4 characters.")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        raise SystemExit("Passwords do not match.")
    return pw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="passlock",
        description="PassLock — password-protect files and folders (cross-platform).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    lock_p = sub.add_parser("lock", help="Encrypt (lock) a file or folder.")
    lock_p.add_argument("target", type=str, help="Path to the file or folder to lock.")
    lock_p.add_argument("--keep", action="store_true", help="Keep the original after encrypting.")

    unlock_p = sub.add_parser("unlock", help="Decrypt (unlock) a .locked file or folder.")
    unlock_p.add_argument("target", type=str, help="Path to the .locked file to unlock.")
    unlock_p.add_argument("--keep", action="store_true", help="Keep the .locked file after decrypting.")

    sub.add_parser("gui", help="Launch the graphical interface.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "gui":
        from passlock.gui import launch_gui
        launch_gui()
        return

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"Error: '{target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if args.command == "lock":
        password = _get_password_for_encrypt()
        if target.is_file():
            out = encrypt_file(target, password, remove_original=not args.keep)
            print(f"Locked file → {out}")
        elif target.is_dir():
            out = encrypt_folder(target, password, remove_original=not args.keep)
            print(f"Locked folder → {out}")
        else:
            print("Error: target is neither a regular file nor a directory.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "unlock":
        if not target.is_file():
            print("Error: unlock target must be a .locked file.", file=sys.stderr)
            sys.exit(1)
        password = getpass.getpass("Enter password: ")
        try:
            out = smart_unlock(target, password, remove_encrypted=not args.keep)
            print(f"Unlocked → {out}")
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
