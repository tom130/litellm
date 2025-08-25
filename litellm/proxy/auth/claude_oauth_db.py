"""
Claude OAuth Database Storage

Handles storing and retrieving OAuth tokens from the database.
"""

import json
import time
from datetime import datetime
from typing import Dict, Optional, Any
from cryptography.fernet import Fernet

from litellm._logging import verbose_proxy_logger


class ClaudeOAuthDatabase:
    """
    Handles database operations for Claude OAuth tokens.
    """
    
    def __init__(self, prisma_client: Any, encryption_key: Optional[str] = None):
        """
        Initialize database handler.
        
        Args:
            prisma_client: Prisma database client
            encryption_key: Optional key for encrypting tokens
        """
        self.prisma_client = prisma_client
        
        # Setup encryption if key provided
        if encryption_key:
            # Use the provided key directly if it's valid, otherwise generate a new one
            try:
                # Try to use the provided key (Fernet requires base64 encoded 32-byte key)
                self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            except (ValueError, Exception) as e:
                # If the key is invalid, generate a new one
                import logging
                logging.warning(f"Invalid encryption key provided for database, generating a temporary key: {e}")
                self.fernet = Fernet(Fernet.generate_key())
        else:
            # No key provided, generate one
            self.fernet = Fernet(Fernet.generate_key())
    
    def _encrypt(self, data: str) -> str:
        """Encrypt a string."""
        if self.fernet and data:
            return self.fernet.encrypt(data.encode()).decode()
        return data
    
    def _decrypt(self, data: str) -> str:
        """Decrypt a string."""
        if self.fernet and data:
            try:
                return self.fernet.decrypt(data.encode()).decode()
            except Exception as e:
                verbose_proxy_logger.error(f"Failed to decrypt token: {e}")
                return data
        return data
    
    async def store_tokens(
        self,
        user_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_at: int,
        scopes: list,
        created_by: Optional[str] = None
    ) -> bool:
        """
        Store OAuth tokens in the database.
        
        Args:
            user_id: User ID
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            expires_at: Token expiration timestamp
            scopes: List of OAuth scopes
            created_by: User who created the tokens
            
        Returns:
            True if successful
        """
        try:
            # Encrypt tokens
            access_token_encrypted = self._encrypt(access_token)
            refresh_token_encrypted = self._encrypt(refresh_token) if refresh_token else None
            
            # Convert expires_at to datetime
            expires_datetime = datetime.fromtimestamp(expires_at)
            
            # Check if tokens already exist for user
            existing = await self.prisma_client.db.litellm_claudeoauthtokens.find_unique(
                where={"user_id": user_id}
            )
            
            if existing:
                # Update existing tokens
                await self.prisma_client.db.litellm_claudeoauthtokens.update(
                    where={"user_id": user_id},
                    data={
                        "access_token_encrypted": access_token_encrypted,
                        "refresh_token_encrypted": refresh_token_encrypted,
                        "expires_at": expires_datetime,
                        "scopes": scopes,
                        "refresh_count": existing.refresh_count + 1,
                        "updated_by": created_by or user_id,
                        "last_used": datetime.now()
                    }
                )
                verbose_proxy_logger.info(f"Updated OAuth tokens for user {user_id}")
            else:
                # Create new token record
                await self.prisma_client.db.litellm_claudeoauthtokens.create(
                    data={
                        "user_id": user_id,
                        "access_token_encrypted": access_token_encrypted,
                        "refresh_token_encrypted": refresh_token_encrypted,
                        "expires_at": expires_datetime,
                        "scopes": scopes,
                        "created_by": created_by or user_id,
                        "updated_by": created_by or user_id
                    }
                )
                verbose_proxy_logger.info(f"Stored new OAuth tokens for user {user_id}")
            
            # Update user table to mark OAuth as enabled
            await self.prisma_client.db.litellm_usertable.update(
                where={"user_id": user_id},
                data={
                    "claude_oauth_enabled": True,
                    "claude_oauth_connected_at": datetime.now()
                }
            )
            
            return True
            
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to store OAuth tokens: {e}")
            return False
    
    async def get_tokens(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve OAuth tokens from the database.
        
        Args:
            user_id: User ID
            
        Returns:
            Token data dictionary or None
        """
        try:
            token_record = await self.prisma_client.db.litellm_claudeoauthtokens.find_unique(
                where={"user_id": user_id}
            )
            
            if not token_record:
                return None
            
            # Decrypt tokens
            access_token = self._decrypt(token_record.access_token_encrypted)
            refresh_token = (self._decrypt(token_record.refresh_token_encrypted) 
                           if token_record.refresh_token_encrypted else None)
            
            # Convert expires_at to timestamp
            expires_at = int(token_record.expires_at.timestamp())
            
            # Update last_used
            await self.prisma_client.db.litellm_claudeoauthtokens.update(
                where={"user_id": user_id},
                data={"last_used": datetime.now()}
            )
            
            return {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresAt": expires_at,
                "scopes": token_record.scopes or [],
                "refreshCount": token_record.refresh_count
            }
            
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to retrieve OAuth tokens: {e}")
            return None
    
    async def delete_tokens(self, user_id: str) -> bool:
        """
        Delete OAuth tokens from the database.
        
        Args:
            user_id: User ID
            
        Returns:
            True if successful
        """
        try:
            # Delete token record
            await self.prisma_client.db.litellm_claudeoauthtokens.delete(
                where={"user_id": user_id}
            )
            
            # Update user table
            await self.prisma_client.db.litellm_usertable.update(
                where={"user_id": user_id},
                data={
                    "claude_oauth_enabled": False,
                    "claude_oauth_connected_at": None
                }
            )
            
            verbose_proxy_logger.info(f"Deleted OAuth tokens for user {user_id}")
            return True
            
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to delete OAuth tokens: {e}")
            return False
    
    async def get_expiring_tokens(self, minutes: int = 10) -> list:
        """
        Get tokens that will expire within the specified minutes.
        
        Args:
            minutes: Minutes until expiration
            
        Returns:
            List of user IDs with expiring tokens
        """
        try:
            from datetime import timedelta
            
            expiry_time = datetime.now() + timedelta(minutes=minutes)
            
            expiring = await self.prisma_client.db.litellm_claudeoauthtokens.find_many(
                where={
                    "expires_at": {"lte": expiry_time},
                    "refresh_token_encrypted": {"not": None}
                }
            )
            
            return [record.user_id for record in expiring]
            
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to get expiring tokens: {e}")
            return []
    
    async def update_token_expiry(
        self,
        user_id: str,
        new_access_token: str,
        new_expires_at: int
    ) -> bool:
        """
        Update token after refresh.
        
        Args:
            user_id: User ID
            new_access_token: New access token
            new_expires_at: New expiration timestamp
            
        Returns:
            True if successful
        """
        try:
            # Encrypt new token
            access_token_encrypted = self._encrypt(new_access_token)
            expires_datetime = datetime.fromtimestamp(new_expires_at)
            
            # Update record
            await self.prisma_client.db.litellm_claudeoauthtokens.update(
                where={"user_id": user_id},
                data={
                    "access_token_encrypted": access_token_encrypted,
                    "expires_at": expires_datetime,
                    "refresh_count": {"increment": 1},
                    "last_used": datetime.now()
                }
            )
            
            verbose_proxy_logger.info(f"Updated token expiry for user {user_id}")
            return True
            
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to update token expiry: {e}")
            return False