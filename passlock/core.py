"""
PassLock core encryption/decryption engine.
AES-256-CBC with PBKDF2 key derivation and HMAC-SHA256 integrity.
"""

import hashlib
import hmac
import os
import secrets
import struct
import tarfile
from io import BytesIO
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_padding
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# ── Constants ─────────────────────────────────────────────────────────

MAGIC = b"PLCK"
VERSION = 1
SALT_SIZE = 32
IV_SIZE = 16
KEY_SIZE = 32
HMAC_SIZE = 32
KDF_ITERATIONS = 600_000
ENCRYPTED_EXT = ".locked"


def _check_crypto():
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError(
            "The 'cryptography' package is required.\n"
            "Install it with:  pip install cryptography"
        )


# ── Key derivation ────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, KDF_ITERATIONS, dklen=KEY_SIZE
    )


# ── Low-level encrypt / decrypt ──────────────────────────────────────

def encrypt_bytes(data: bytes, password: str) -> bytes:
    _check_crypto()

    salt = secrets.token_bytes(SALT_SIZE)
    iv = secrets.token_bytes(IV_SIZE)
    key = derive_key(password, salt)

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    blob = MAGIC + struct.pack("B", VERSION) + salt + iv + ciphertext
    mac = hmac.new(key, blob, hashlib.sha256).digest()
    return blob + mac


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    _check_crypto()

    header_len = len(MAGIC) + 1 + SALT_SIZE + IV_SIZE
    if len(blob) < header_len + HMAC_SIZE:
        raise ValueError("File is too small or corrupted.")
    if blob[:4] != MAGIC:
        raise ValueError("Not a PassLock-encrypted file (bad magic bytes).")

    version = struct.unpack("B", blob[4:5])[0]
    if version != VERSION:
        raise ValueError(f"Unsupported file version: {version}")

    salt = blob[5: 5 + SALT_SIZE]
    iv = blob[5 + SALT_SIZE: 5 + SALT_SIZE + IV_SIZE]
    ciphertext = blob[header_len:-HMAC_SIZE]
    stored_mac = blob[-HMAC_SIZE:]

    key = derive_key(password, salt)

    expected_mac = hmac.new(key, blob[:-HMAC_SIZE], hashlib.sha256).digest()
    if not hmac.compare_digest(stored_mac, expected_mac):
        raise ValueError("Wrong password or the file has been tampered with.")

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


# ── File operations ──────────────────────────────────────────────────

def encrypt_file(filepath: Path, password: str, *, remove_original: bool = True) -> Path:
    data = filepath.read_bytes()
    encrypted = encrypt_bytes(data, password)
    out_path = filepath.with_suffix(filepath.suffix + ENCRYPTED_EXT)
    out_path.write_bytes(encrypted)
    if remove_original:
        filepath.unlink()
    return out_path


def decrypt_file(filepath: Path, password: str, *, remove_encrypted: bool = True) -> Path:
    blob = filepath.read_bytes()
    data = decrypt_bytes(blob, password)
    if filepath.name.endswith(ENCRYPTED_EXT):
        out_path = filepath.with_name(filepath.name[: -len(ENCRYPTED_EXT)])
    else:
        out_path = filepath.with_suffix("")
    out_path.write_bytes(data)
    if remove_encrypted:
        filepath.unlink()
    return out_path


# ── Folder operations ────────────────────────────────────────────────

def encrypt_folder(folder: Path, password: str, *, remove_original: bool = True) -> Path:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(folder), arcname=folder.name)
    encrypted = encrypt_bytes(buf.getvalue(), password)
    out_path = folder.with_name(folder.name + ENCRYPTED_EXT)
    out_path.write_bytes(encrypted)
    if remove_original:
        _remove_tree(folder)
    return out_path


def decrypt_folder(filepath: Path, password: str, *, remove_encrypted: bool = True) -> Path:
    blob = filepath.read_bytes()
    archive_bytes = decrypt_bytes(blob, password)
    buf = BytesIO(archive_bytes)
    dest = filepath.parent
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for member in tar.getmembers():
            member_path = os.path.normpath(member.name)
            if member_path.startswith("..") or os.path.isabs(member_path):
                raise ValueError(f"Unsafe path in archive: {member.name}")
        tar.extractall(path=str(dest))
    if remove_encrypted:
        filepath.unlink()
    folder_name = filepath.name
    if folder_name.endswith(ENCRYPTED_EXT):
        folder_name = folder_name[: -len(ENCRYPTED_EXT)]
    return dest / folder_name


def is_tar_archive(data: bytes) -> bool:
    """Check if decrypted data is a tar.gz archive (i.e. an encrypted folder)."""
    try:
        with tarfile.open(fileobj=BytesIO(data), mode="r:gz"):
            return True
    except (tarfile.TarError, Exception):
        return False


def smart_unlock(filepath: Path, password: str, *, remove_encrypted: bool = True) -> Path:
    """Auto-detect whether a .locked file is a file or folder and unlock it."""
    blob = filepath.read_bytes()
    data = decrypt_bytes(blob, password)

    if is_tar_archive(data):
        buf = BytesIO(data)
        dest = filepath.parent
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            for member in tar.getmembers():
                member_path = os.path.normpath(member.name)
                if member_path.startswith("..") or os.path.isabs(member_path):
                    raise ValueError(f"Unsafe path in archive: {member.name}")
            tar.extractall(path=str(dest))
        if remove_encrypted:
            filepath.unlink()
        inner_name = filepath.name
        if inner_name.endswith(ENCRYPTED_EXT):
            inner_name = inner_name[: -len(ENCRYPTED_EXT)]
        return dest / inner_name
    else:
        inner_name = filepath.name
        if inner_name.endswith(ENCRYPTED_EXT):
            inner_name = inner_name[: -len(ENCRYPTED_EXT)]
        out_path = filepath.with_name(inner_name) if inner_name != filepath.name else filepath.with_suffix("")
        out_path.write_bytes(data)
        if remove_encrypted:
            filepath.unlink()
        return out_path


def _remove_tree(path: Path) -> None:
    if path.is_file() or path.is_symlink():
        path.unlink()
    elif path.is_dir():
        for child in path.iterdir():
            _remove_tree(child)
        path.rmdir()
