#!/usr/bin/env python3
"""
PassLock - Cross-platform file and folder password protection tool.
Encrypts and decrypts files/folders using AES-256 encryption with a user-provided password.
Works on Windows, macOS, and Linux.
"""

import argparse
import getpass
import hashlib
import hmac
import os
import secrets
import struct
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

# ── Crypto primitives (AES-CBC via cryptography library) ──────────────

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_padding
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# ── Constants ─────────────────────────────────────────────────────────

MAGIC = b"PLCK"          # file signature
VERSION = 1
SALT_SIZE = 32
IV_SIZE = 16
KEY_SIZE = 32             # AES-256
HMAC_SIZE = 32
KDF_ITERATIONS = 600_000  # PBKDF2 iterations
ENCRYPTED_EXT = ".locked"
CHUNK_SIZE = 64 * 1024    # 64 KB read chunks


# ── Key derivation ────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from password + salt using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, KDF_ITERATIONS, dklen=KEY_SIZE)


# ── Low-level encrypt / decrypt ──────────────────────────────────────

def _encrypt_bytes(data: bytes, password: str) -> bytes:
    """
    Encrypt *data* with *password*.

    Layout of the returned blob:
        MAGIC (4 B) | VERSION (1 B) | salt (32 B) | iv (16 B)
        | ciphertext (variable) | HMAC-SHA256 (32 B)
    """
    if not HAS_CRYPTOGRAPHY:
        raise SystemExit(
            "The 'cryptography' package is required.\n"
            "Install it with:  pip install cryptography"
        )

    salt = secrets.token_bytes(SALT_SIZE)
    iv = secrets.token_bytes(IV_SIZE)
    key = derive_key(password, salt)

    # PKCS7 pad → AES-CBC encrypt
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    # Build blob (without HMAC yet)
    blob = MAGIC + struct.pack("B", VERSION) + salt + iv + ciphertext

    # Append HMAC over the entire blob
    mac = hmac.new(key, blob, hashlib.sha256).digest()
    return blob + mac


def _decrypt_bytes(blob: bytes, password: str) -> bytes:
    """Decrypt a blob produced by *_encrypt_bytes*."""
    if not HAS_CRYPTOGRAPHY:
        raise SystemExit(
            "The 'cryptography' package is required.\n"
            "Install it with:  pip install cryptography"
        )

    header_len = len(MAGIC) + 1 + SALT_SIZE + IV_SIZE  # 4+1+32+16 = 53
    if len(blob) < header_len + HMAC_SIZE:
        raise ValueError("File is too small or corrupted.")

    if blob[:4] != MAGIC:
        raise ValueError("Not a PassLock-encrypted file (bad magic bytes).")

    version = struct.unpack("B", blob[4:5])[0]
    if version != VERSION:
        raise ValueError(f"Unsupported file version: {version}")

    salt = blob[5 : 5 + SALT_SIZE]
    iv = blob[5 + SALT_SIZE : 5 + SALT_SIZE + IV_SIZE]
    ciphertext = blob[header_len:-HMAC_SIZE]
    stored_mac = blob[-HMAC_SIZE:]

    key = derive_key(password, salt)

    # Verify HMAC first (encrypt-then-MAC)
    expected_mac = hmac.new(key, blob[:-HMAC_SIZE], hashlib.sha256).digest()
    if not hmac.compare_digest(stored_mac, expected_mac):
        raise ValueError("Wrong password or the file has been tampered with.")

    # Decrypt → unpad
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


# ── File-level operations ────────────────────────────────────────────

def encrypt_file(filepath: Path, password: str, *, remove_original: bool = True) -> Path:
    """Encrypt a single file. Returns the path to the .locked file."""
    data = filepath.read_bytes()
    encrypted = _encrypt_bytes(data, password)

    out_path = filepath.with_suffix(filepath.suffix + ENCRYPTED_EXT)
    out_path.write_bytes(encrypted)

    if remove_original:
        filepath.unlink()

    return out_path


def decrypt_file(filepath: Path, password: str, *, remove_encrypted: bool = True) -> Path:
    """Decrypt a .locked file. Returns the path to the restored file."""
    blob = filepath.read_bytes()
    data = _decrypt_bytes(blob, password)

    if filepath.name.endswith(ENCRYPTED_EXT):
        out_path = filepath.with_name(filepath.name[: -len(ENCRYPTED_EXT)])
    else:
        out_path = filepath.with_suffix("")

    out_path.write_bytes(data)

    if remove_encrypted:
        filepath.unlink()

    return out_path


# ── Folder-level operations ──────────────────────────────────────────

def encrypt_folder(folder: Path, password: str, *, remove_original: bool = True) -> Path:
    """
    Archive the folder into a tar stream, encrypt the stream, and write
    a single .locked file next to the folder.
    """
    # Create tar archive in memory
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(folder), arcname=folder.name)
    archive_bytes = buf.getvalue()

    encrypted = _encrypt_bytes(archive_bytes, password)
    out_path = folder.with_name(folder.name + ENCRYPTED_EXT)
    out_path.write_bytes(encrypted)

    if remove_original:
        _remove_tree(folder)

    return out_path


def decrypt_folder(filepath: Path, password: str, *, remove_encrypted: bool = True) -> Path:
    """Decrypt a .locked folder archive and extract it."""
    blob = filepath.read_bytes()
    archive_bytes = _decrypt_bytes(blob, password)

    buf = BytesIO(archive_bytes)
    dest = filepath.parent

    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        # Security: prevent path traversal in tar entries
        for member in tar.getmembers():
            member_path = os.path.normpath(member.name)
            if member_path.startswith("..") or os.path.isabs(member_path):
                raise ValueError(f"Unsafe path in archive: {member.name}")
        tar.extractall(path=str(dest))

    if remove_encrypted:
        filepath.unlink()

    # Determine the extracted folder name
    folder_name = filepath.name
    if folder_name.endswith(ENCRYPTED_EXT):
        folder_name = folder_name[: -len(ENCRYPTED_EXT)]
    return dest / folder_name


def _remove_tree(path: Path) -> None:
    """Recursively remove a directory tree (cross-platform)."""
    if path.is_file() or path.is_symlink():
        path.unlink()
    elif path.is_dir():
        for child in path.iterdir():
            _remove_tree(child)
        path.rmdir()


# ── Password input helpers ───────────────────────────────────────────

def _get_password_for_encrypt() -> str:
    pw = getpass.getpass("Enter password: ")
    if len(pw) < 4:
        raise SystemExit("Password must be at least 4 characters.")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        raise SystemExit("Passwords do not match.")
    return pw


def _get_password_for_decrypt() -> str:
    return getpass.getpass("Enter password: ")


# ── CLI ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="passlock",
        description="PassLock — password-protect files and folders (cross-platform).",
    )
    sub = parser.add_subparsers(dest="command")

    # lock
    lock_p = sub.add_parser("lock", help="Encrypt (lock) a file or folder.")
    lock_p.add_argument("target", type=str, help="Path to the file or folder to lock.")
    lock_p.add_argument(
        "--keep", action="store_true",
        help="Keep the original file/folder after encrypting.",
    )

    # unlock
    unlock_p = sub.add_parser("unlock", help="Decrypt (unlock) a .locked file or folder.")
    unlock_p.add_argument("target", type=str, help="Path to the .locked file to unlock.")
    unlock_p.add_argument(
        "--keep", action="store_true",
        help="Keep the .locked file after decrypting.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

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

        password = _get_password_for_decrypt()

        # Heuristic: if the name minus .locked still has an extension, treat as file
        inner_name = target.name
        if inner_name.endswith(ENCRYPTED_EXT):
            inner_name = inner_name[: -len(ENCRYPTED_EXT)]

        # Try to detect whether the encrypted content is a tar archive
        try:
            blob = target.read_bytes()
            data = _decrypt_bytes(blob, password)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        buf = BytesIO(data)
        is_tar = False
        try:
            with tarfile.open(fileobj=buf, mode="r:gz") as _:
                is_tar = True
        except (tarfile.TarError, Exception):
            is_tar = False

        if is_tar:
            # Re-read because _decrypt_bytes was already called
            buf = BytesIO(data)
            dest = target.parent
            with tarfile.open(fileobj=buf, mode="r:gz") as tar:
                for member in tar.getmembers():
                    member_path = os.path.normpath(member.name)
                    if member_path.startswith("..") or os.path.isabs(member_path):
                        raise ValueError(f"Unsafe path in archive: {member.name}")
                tar.extractall(path=str(dest))
            if not args.keep:
                target.unlink()
            print(f"Unlocked folder → {dest / inner_name}")
        else:
            out_path = target.with_name(inner_name) if inner_name != target.name else target.with_suffix("")
            out_path.write_bytes(data)
            if not args.keep:
                target.unlink()
            print(f"Unlocked file → {out_path}")


if __name__ == "__main__":
    main()
