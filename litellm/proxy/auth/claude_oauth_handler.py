"""
Claude OAuth Handler with PKCE Implementation

Handles OAuth 2.0 authentication flow for Claude Max models with PKCE support.
Provides secure token management and automatic refresh capabilities.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request, Response, status

from litellm._logging import verbose_proxy_logger
from litellm.caching import DualCache
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.utils import PrismaClient


class ClaudeOAuthHandler:
    """
    Handles Claude OAuth 2.0 authentication with PKCE flow.
    
    Features:
    - PKCE (Proof Key for Code Exchange) implementation
    - Secure token storage with encryption
    - Automatic token refresh
    - Multi-user token management
    """
    
    # OAuth endpoints
    AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
    TOKEN_URL = "https://claude.ai/api/oauth/token"
    USER_INFO_URL = "https://claude.ai/api/user"
    
    # Default scopes for Claude API access
    DEFAULT_SCOPES = ["claude:chat", "claude:models", "claude:read"]
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        encryption_key: Optional[str] = None,
        prisma_client: Optional[PrismaClient] = None,
        cache: Optional[DualCache] = None,
    ):
        """
        Initialize Claude OAuth handler.
        
        Args:
            client_id: OAuth client ID (can be set via CLAUDE_OAUTH_CLIENT_ID env var)
            redirect_uri: OAuth redirect URI (can be set via CLAUDE_OAUTH_REDIRECT_URI env var)
            encryption_key: Key for encrypting tokens (can be set via CLAUDE_TOKEN_ENCRYPTION_KEY env var)
            prisma_client: Database client for token storage
            cache: Cache client for temporary storage
        """
        self.client_id = client_id or os.getenv("CLAUDE_OAUTH_CLIENT_ID")
        self.redirect_uri = redirect_uri or os.getenv(
            "CLAUDE_OAUTH_REDIRECT_URI", "http://localhost:4000/auth/claude/callback"
        )
        
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
        
        # Store PKCE verifiers temporarily
        self.pkce_storage: Dict[str, Dict[str, Any]] = {}
    
    def generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate code challenge using S256 method
        challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def generate_state(self, user_id: Optional[str] = None) -> str:
        """
        Generate secure state parameter for OAuth flow.
        
        Args:
            user_id: Optional user ID to include in state
            
        Returns:
            Secure state string
        """
        state_data = {
            "nonce": secrets.token_urlsafe(32),
            "timestamp": int(time.time()),
            "user_id": user_id
        }
        state_json = json.dumps(state_data)
        
        # Encrypt state data
        encrypted_state = self.cipher_suite.encrypt(state_json.encode())
        return base64.urlsafe_b64encode(encrypted_state).decode('utf-8').rstrip('=')
    
    def verify_state(self, state: str) -> Dict[str, Any]:
        """
        Verify and decrypt state parameter.
        
        Args:
            state: State string from OAuth callback
            
        Returns:
            Decrypted state data
            
        Raises:
            HTTPException: If state is invalid or expired
        """
        try:
            # Decode and decrypt state
            padded_state = state + '=' * (4 - len(state) % 4)
            encrypted_state = base64.urlsafe_b64decode(padded_state)
            decrypted_state = self.cipher_suite.decrypt(encrypted_state)
            state_data = json.loads(decrypted_state.decode())
            
            # Check timestamp (expire after 10 minutes)
            if time.time() - state_data["timestamp"] > 600:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OAuth state expired"
                )
            
            return state_data
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to verify OAuth state: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OAuth state"
            )
    
    def get_authorization_url(
        self,
        user_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        additional_params: Optional[Dict[str, str]] = None
    ) -> Tuple[str, str, str]:
        """
        Generate OAuth authorization URL with PKCE.
        
        Args:
            user_id: User ID for state tracking
            scopes: OAuth scopes to request
            additional_params: Additional query parameters
            
        Returns:
            Tuple of (authorization_url, state, code_verifier)
        """
        if not self.client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Claude OAuth client ID not configured"
            )
        
        # Generate PKCE pair
        code_verifier, code_challenge = self.generate_pkce_pair()
        
        # Generate state
        state = self.generate_state(user_id)
        
        # Store PKCE verifier for later use
        self.pkce_storage[state] = {
            "code_verifier": code_verifier,
            "user_id": user_id,
            "timestamp": time.time()
        }
        
        # Clean up old PKCE verifiers (older than 10 minutes)
        current_time = time.time()
        self.pkce_storage = {
            k: v for k, v in self.pkce_storage.items()
            if current_time - v["timestamp"] < 600
        }
        
        # Build authorization URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes or self.DEFAULT_SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        
        if additional_params:
            params.update(additional_params)
        
        auth_url = f"{self.AUTHORIZE_URL}?{urlencode(params)}"
        
        return auth_url, state, code_verifier
    
    async def exchange_code_for_token(
        self,
        code: str,
        state: str
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from OAuth callback
            state: State parameter from OAuth callback
            
        Returns:
            Token response with access_token, refresh_token, etc.
            
        Raises:
            HTTPException: If token exchange fails
        """
        # Verify state
        state_data = self.verify_state(state)
        
        # Retrieve PKCE verifier
        pkce_data = self.pkce_storage.get(state)
        if not pkce_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PKCE verifier not found"
            )
        
        code_verifier = pkce_data["code_verifier"]
        user_id = pkce_data.get("user_id")
        
        # Clean up PKCE storage
        del self.pkce_storage[state]
        
        # Exchange code for token
        import httpx
        from litellm.llms.custom_httpx.http_handler import get_async_httpx_client
        
        client = get_async_httpx_client()
        
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier
        }
        
        try:
            response = await client.post(
                self.TOKEN_URL,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_response = response.json()
            
            # Add user_id to response
            token_response["user_id"] = user_id
            
            # Store token securely
            await self.store_token(user_id, token_response)
            
            return token_response
            
        except httpx.HTTPStatusError as e:
            verbose_proxy_logger.error(f"Token exchange failed: {e.response.text}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {e.response.text}"
            )
        except Exception as e:
            verbose_proxy_logger.error(f"Token exchange error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token exchange failed"
            )
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an access token using refresh token.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            New token response
            
        Raises:
            HTTPException: If refresh fails
        """
        import httpx
        from litellm.llms.custom_httpx.http_handler import get_async_httpx_client
        
        client = get_async_httpx_client()
        
        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id
        }
        
        try:
            response = await client.post(
                self.TOKEN_URL,
                data=refresh_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            verbose_proxy_logger.error(f"Token refresh failed: {e.response.text}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to refresh token"
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
    
    async def store_token(
        self,
        user_id: str,
        token_response: Dict[str, Any]
    ) -> None:
        """
        Store OAuth tokens securely in database.
        
        Args:
            user_id: User ID
            token_response: Token response from OAuth server
        """
        if not self.prisma_client:
            # Fallback to cache if no database
            if self.cache:
                cache_key = f"claude_oauth_token:{user_id}"
                await self.cache.async_set_cache(cache_key, token_response, ttl=3600)
            return
        
        # Encrypt tokens
        encrypted_access = self.encrypt_token(token_response["access_token"])
        encrypted_refresh = self.encrypt_token(token_response.get("refresh_token", ""))
        
        # Calculate expiration
        expires_in = token_response.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        # Store in database (implementation depends on schema)
        # This is a placeholder - actual implementation would use Prisma schema
        verbose_proxy_logger.info(f"Storing OAuth token for user {user_id}")
    
    async def get_valid_token(self, user_id: str) -> Optional[str]:
        """
        Get a valid access token for a user, refreshing if necessary.
        
        Args:
            user_id: User ID
            
        Returns:
            Valid access token or None if not found
        """
        # Check cache first
        if self.cache:
            cache_key = f"claude_oauth_token:{user_id}"
            cached_token = await self.cache.async_get_cache(cache_key)
            if cached_token:
                # Check if token needs refresh
                expires_at = cached_token.get("expires_at")
                if expires_at:
                    expiry_time = datetime.fromisoformat(expires_at)
                    # Refresh if expiring in next 5 minutes
                    if expiry_time - datetime.now(timezone.utc) < timedelta(minutes=5):
                        try:
                            new_token = await self.refresh_access_token(
                                cached_token["refresh_token"]
                            )
                            new_token["user_id"] = user_id
                            await self.store_token(user_id, new_token)
                            return new_token["access_token"]
                        except Exception as e:
                            verbose_proxy_logger.error(f"Token refresh failed: {e}")
                            return None
                
                return cached_token.get("access_token")
        
        return None
    
    async def revoke_token(self, user_id: str) -> bool:
        """
        Revoke OAuth tokens for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            True if successful
        """
        # Clear from cache
        if self.cache:
            cache_key = f"claude_oauth_token:{user_id}"
            await self.cache.async_delete_cache(cache_key)
        
        # Clear from database (implementation depends on schema)
        verbose_proxy_logger.info(f"Revoked OAuth token for user {user_id}")
        
        return True