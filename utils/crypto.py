"""
Credential encryption/decryption using Fernet symmetric encryption.

Usage:
    from utils.crypto import encrypt, decrypt

    token = "ghp_secret"
    blob = encrypt(token)          # store in DB
    original = decrypt(blob)       # retrieve for API calls
"""
import base64

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    from config.settings import settings  # local import avoids circular deps
    key = settings.encryption_key
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set in your .env file. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a base64-encoded ciphertext string."""
    fernet = _get_fernet()
    ciphertext_bytes = fernet.encrypt(plaintext.encode())
    return base64.urlsafe_b64encode(ciphertext_bytes).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string produced by encrypt(). Returns the original plaintext."""
    fernet = _get_fernet()
    try:
        raw = base64.urlsafe_b64decode(ciphertext.encode())
        return fernet.decrypt(raw).decode()
    except (InvalidToken, Exception) as exc:
        raise ValueError("Failed to decrypt credential – key mismatch or corrupted data.") from exc


def generate_key() -> str:
    """Generate a new Fernet key. Run once during setup."""
    return Fernet.generate_key().decode()
