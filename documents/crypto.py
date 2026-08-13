from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _get_fernet():
    """
    Fernet (from the `cryptography` package) provides authenticated
    symmetric encryption: AES-128 in CBC mode for confidentiality, plus
    an HMAC-SHA256 signature so a tampered ciphertext is detected and
    rejected on decryption rather than silently decrypting to garbage.
    That authentication is why decrypt_bytes below can fail loudly on a
    corrupted or tampered file instead of returning wrong data.
    """
    key = settings.DOCUMENT_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured(
            "DOCUMENT_ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            "and add it to your .env file or your hosting provider's environment variables."
        )
    key_bytes = key.encode() if isinstance(key, str) else key
    return Fernet(key_bytes)


def encrypt_bytes(plaintext):
    return _get_fernet().encrypt(plaintext)


def decrypt_bytes(ciphertext):
    return _get_fernet().decrypt(ciphertext)
