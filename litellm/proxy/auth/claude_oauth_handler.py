"""
Claude OAuth Token Handler

Manages pre-existing Claude OAuth tokens (access_token, refresh_token, expires_at).
This does NOT implement an OAuth flow - tokens must be obtained from Claude.ai directly.
"""

import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.caching import DualCache
from litellm.proxy.utils import PrismaClient
from litellm.proxy.auth.claude_oauth_flow import ClaudeOAuthFlow
from litellm.proxy.auth.claude_oauth_db import ClaudeOAuthDatabase


class ClaudeOAuthHandler:
    """
    Handles Claude OAuth token management.
    
    This handler manages OAuth tokens obtained from Claude.ai.
    It integrates with ClaudeOAuthFlow for initial token acquisition.
    
    Features:
    - OAuth flow integration for initial setup
    - Secure token storage with encryption
    - Automatic token refresh before expiration
    - Multi-user token management
    """
    
    # Anthropic API endpoints
    TOKEN_REFRESH_URL = "https://api.anthropic.com/v1/oauth/refresh"
    API_BASE_URL = "https://api.anthropic.com/v1"
    
    # OAuth beta header required for OAuth requests
    OAUTH_BETA_HEADER = "oauth-2025-04-20"
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_at: Optional[int] = None,
        encryption_key: Optional[str] = None,
        prisma_client: Optional[PrismaClient] = None,
        cache: Optional[DualCache] = None,
        oauth_flow: Optional[ClaudeOAuthFlow] = None,
    ):
        """
        Initialize Claude OAuth handler with existing tokens.
        
        Args:
            access_token: Existing OAuth access token from Claude.ai
            refresh_token: Existing OAuth refresh token from Claude.ai
            expires_at: Token expiration timestamp (seconds since epoch)
            encryption_key: Key for encrypting stored tokens
            prisma_client: Database client for token storage
            cache: Cache client for temporary storage
        """
        # Load tokens from environment if not provided
        self.access_token = access_token or os.getenv("CLAUDE_ACCESS_TOKEN")
        self.refresh_token = refresh_token or os.getenv("CLAUDE_REFRESH_TOKEN")
        
        # Handle expires_at - can be string timestamp or int
        if expires_at:
            self.expires_at = int(expires_at) if isinstance(expires_at, (str, int)) else expires_at
        else:
            expires_at_env = os.getenv("CLAUDE_EXPIRES_AT")
            if expires_at_env:
                self.expires_at = int(expires_at_env)
            else:
                # Default to 1 hour from now if not provided
                self.expires_at = int(time.time()) + 3600
        
        # Initialize encryption
        encryption_key = encryption_key or os.getenv("CLAUDE_TOKEN_ENCRYPTION_KEY")
        if encryption_key:
            self.cipher_suite = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        else:
            # Generate a new key if not provided
            key = Fernet.generate_key()
            self.cipher_suite = Fernet(key)
            verbose_proxy_logger.warning(
                "No encryption key provided. Generated temporary key. Set CLAUDE_TOKEN_ENCRYPTION_KEY for production."
            )
        
        self.prisma_client = prisma_client
        self.cache = cache
        self.oauth_flow = oauth_flow or ClaudeOAuthFlow()
        
        # Setup database handler if prisma client available
        if self.prisma_client:
            self.db_handler = ClaudeOAuthDatabase(self.prisma_client, encryption_key)
        else:
            self.db_handler = None
        
        # Validate initial tokens if provided
        if self.access_token and not self.refresh_token:
            verbose_proxy_logger.warning(
                "Access token provided without refresh token. Token refresh will not be possible."
            )
        elif not self.access_token and not self.refresh_token:
            verbose_proxy_logger.info(
                "No OAuth tokens provided. OAuth flow will be required for initial setup. "
                "Run: litellm claude login"
            )
    
    def get_token_data(self) -> Dict[str, Any]:
        """
        Get current token data in the expected format.
        
        Returns:
            Dictionary with accessToken, refreshToken, expiresAt, etc.
        """
        return {
            "accessToken": self.access_token,
            "refreshToken": self.refresh_token,
            "expiresAt": self.expires_at,
            "scopes": ["org:create_api_key", "user:profile", "user:inference"],
            "isMax": True  # Assuming these are Claude Max tokens
        }
    
    def is_token_expired(self, buffer_seconds: int = 300) -> bool:
        """
        Check if the current token is expired or will expire soon.
        
        Args:
            buffer_seconds: Seconds before actual expiry to consider token expired
            
        Returns:
            True if token is expired or will expire within buffer
        """
        if not self.expires_at:
            return True
        
        current_time = int(time.time())
        return current_time >= (self.expires_at - buffer_seconds)
    
    async def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh the access token using the refresh token.
        
        Returns:
            New token data with updated access_token and expires_at
            
        Raises:
            HTTPException: If refresh fails
        """
        if not self.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No refresh token available"
            )
        
        import httpx
        from litellm.llms.custom_httpx.http_handler import get_async_httpx_client
        
        client = get_async_httpx_client()
        
        headers = {
            "Content-Type": "application/json",
            "anthropic-beta": self.OAUTH_BETA_HEADER
        }
        
        data = {
            "refresh_token": self.refresh_token
        }
        
        try:
            response = await client.post(
                self.TOKEN_REFRESH_URL,
                json=data,
                headers=headers
            )
            response.raise_for_status()
            
            token_response = response.json()
            
            # Update stored tokens
            self.access_token = token_response.get("access_token", token_response.get("accessToken"))
            
            # Update refresh token if a new one is provided
            if "refresh_token" in token_response:
                self.refresh_token = token_response["refresh_token"]
            elif "refreshToken" in token_response:
                self.refresh_token = token_response["refreshToken"]
            
            # Calculate new expiration time
            if "expires_in" in token_response:
                self.expires_at = int(time.time()) + token_response["expires_in"]
            elif "expiresAt" in token_response:
                self.expires_at = int(token_response["expiresAt"])
            else:
                # Default to 1 hour if not specified
                self.expires_at = int(time.time()) + 3600
            
            verbose_proxy_logger.info("Successfully refreshed Claude OAuth token")
            
            return self.get_token_data()
            
        except httpx.HTTPStatusError as e:
            verbose_proxy_logger.error(f"Token refresh failed: {e.response.text}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to refresh Claude OAuth token"
            )
        except Exception as e:
            verbose_proxy_logger.error(f"Token refresh error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token refresh failed"
            )
    
    def encrypt_token(self, token: str) -> str:
        """
        Encrypt a token for secure storage.
        
        Args:
            token: Plain text token
            
        Returns:
            Encrypted token as base64 string
        """
        encrypted = self.cipher_suite.encrypt(token.encode())
        return base64.b64encode(encrypted).decode('utf-8')
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt a stored token.
        
        Args:
            encrypted_token: Encrypted token as base64 string
            
        Returns:
            Decrypted plain text token
        """
        encrypted_bytes = base64.b64decode(encrypted_token)
        decrypted = self.cipher_suite.decrypt(encrypted_bytes)
        return decrypted.decode('utf-8')
    
    async def store_tokens(
        self,
        user_id: str,
        token_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Store OAuth tokens securely.
        
        Args:
            user_id: User ID for token association
            token_data: Optional token data to store (uses instance tokens if not provided)
        """
        if not token_data:
            token_data = self.get_token_data()
        
        # Store in cache for fast access
        if self.cache:
            cache_key = f"claude_oauth_token:{user_id}"
            ttl = max(60, self.expires_at - int(time.time())) if self.expires_at else 3600
            await self.cache.async_set_cache(cache_key, token_data, ttl=ttl)
        
        # Store encrypted tokens in database if available
        if self.db_handler:
            await self.db_handler.store_tokens(
                user_id=user_id,
                access_token=token_data.get("accessToken", self.access_token),
                refresh_token=token_data.get("refreshToken", self.refresh_token),
                expires_at=token_data.get("expiresAt", self.expires_at),
                scopes=token_data.get("scopes", []),
                created_by=user_id
            )
            verbose_proxy_logger.info(f"Stored OAuth tokens in database for user {user_id}")
    
    async def get_valid_token(
        self,
        user_id: Optional[str] = None,
        auto_refresh: bool = True,
        auto_oauth: bool = False
    ) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.
        
        Args:
            user_id: Optional user ID to retrieve cached tokens
            auto_refresh: Whether to automatically refresh expired tokens
            
        Returns:
            Valid access token or None if unavailable
        """
        # Try to load from database first if user_id provided
        if user_id and self.db_handler:
            db_data = await self.db_handler.get_tokens(user_id)
            if db_data:
                self.access_token = db_data.get("accessToken")
                self.refresh_token = db_data.get("refreshToken")
                self.expires_at = db_data.get("expiresAt")
                # Update cache
                if self.cache:
                    cache_key = f"claude_oauth_token:{user_id}"
                    ttl = max(60, self.expires_at - int(time.time())) if self.expires_at else 3600
                    await self.cache.async_set_cache(cache_key, db_data, ttl=ttl)
        # Otherwise try cache
        elif user_id and self.cache:
            cache_key = f"claude_oauth_token:{user_id}"
            cached_data = await self.cache.async_get_cache(cache_key)
            if cached_data:
                self.access_token = cached_data.get("accessToken")
                self.refresh_token = cached_data.get("refreshToken")
                self.expires_at = cached_data.get("expiresAt")
        
        # Check if token needs refresh
        if auto_refresh and self.is_token_expired():
            if self.refresh_token:
                try:
                    token_data = await self.refresh_access_token()
                    if user_id:
                        await self.store_tokens(user_id, token_data)
                    return self.access_token
                except Exception as e:
                    verbose_proxy_logger.error(f"Failed to refresh token: {e}")
                    return None
            else:
                verbose_proxy_logger.warning("Token expired but no refresh token available")
                return None
        
        # Check if we have a valid token
        if self.access_token and not self.is_token_expired(buffer_seconds=0):
            return self.access_token
        
        # No valid token and OAuth flow requested
        if auto_oauth and not self.access_token and not self.refresh_token:
            verbose_proxy_logger.info(
                "No OAuth tokens found. OAuth flow required. "
                "Please run: litellm claude login"
            )
            return None
        
        return None
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for Claude API requests.
        
        Returns:
            Dictionary of headers including Bearer token and beta header
        """
        if not self.access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No Claude OAuth token available. Please run: litellm claude login"
            )
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "anthropic-beta": self.OAUTH_BETA_HEADER
        }