"""Token encryption utilities for secure storage.

This module provides encryption/decryption for OAuth tokens using
Fernet (symmetric encryption) to protect credentials at rest.
"""

from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class TokenEncryption:
    """
    Handles encryption and decryption of OAuth tokens.

    Uses Fernet (symmetric encryption based on AES-128-CBC) for
    secure token storage. Encryption keys should be stored securely
    in environment variables or a secrets management system.

    Attributes:
        cipher: Fernet cipher instance
    """

    def __init__(self, encryption_key: str) -> None:
        """
        Initialize token encryption.

        Args:
            encryption_key: Base64-encoded Fernet encryption key

        Raises:
            ValueError: If encryption key is invalid
        """
        if not encryption_key:
            raise ValueError("Encryption key is required")

        try:
            self.cipher = Fernet(encryption_key.encode())
            logger.info("Token encryption initialized")
        except Exception as e:
            logger.error("Failed to initialize encryption", error=str(e))
            raise ValueError(f"Invalid encryption key: {e}")

    def encrypt(self, token: str) -> str:
        """
        Encrypt a token for secure storage.

        Args:
            token: Plaintext token to encrypt

        Returns:
            Base64-encoded encrypted token

        Raises:
            ValueError: If token is None or empty
        """
        if not token:
            raise ValueError("Cannot encrypt empty token")

        try:
            encrypted = self.cipher.encrypt(token.encode())
            logger.debug("Token encrypted successfully")
            return encrypted.decode()
        except Exception as e:
            logger.error("Failed to encrypt token", error=str(e))
            raise

    def decrypt(self, encrypted_token: str) -> str:
        """
        Decrypt a token from storage.

        Args:
            encrypted_token: Base64-encoded encrypted token

        Returns:
            Decrypted plaintext token

        Raises:
            ValueError: If encrypted_token is None or empty
            InvalidToken: If decryption fails (wrong key or corrupted data)
        """
        if not encrypted_token:
            raise ValueError("Cannot decrypt empty token")

        try:
            decrypted = self.cipher.decrypt(encrypted_token.encode())
            logger.debug("Token decrypted successfully")
            return decrypted.decode()
        except InvalidToken as e:
            logger.error("Failed to decrypt token - invalid key or corrupted data")
            raise InvalidToken("Failed to decrypt token - invalid key or corrupted data")
        except Exception as e:
            logger.error("Failed to decrypt token", error=str(e))
            raise

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.

        Returns:
            Base64-encoded encryption key

        Usage:
            >>> key = TokenEncryption.generate_key()
            >>> print(f"Add to .env: TOKEN_ENCRYPTION_KEY={key}")
        """
        key = Fernet.generate_key()
        return key.decode()


# Singleton instance - initialized on first use
_encryption_instance: Optional[TokenEncryption] = None


def get_token_encryption() -> TokenEncryption:
    """
    Get or create the global TokenEncryption instance.

    Returns:
        TokenEncryption singleton instance

    Raises:
        ValueError: If encryption key not configured
    """
    global _encryption_instance

    if _encryption_instance is None:
        from src.config import settings

        if not settings.token_encryption_key:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY not configured. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        _encryption_instance = TokenEncryption(settings.token_encryption_key)

    return _encryption_instance
