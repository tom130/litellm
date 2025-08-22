"""
Claude Token Manager

Manages OAuth token lifecycle including storage, retrieval, refresh, and validation.
Works with pre-existing Claude OAuth tokens obtained from Claude.ai.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from litellm._logging import verbose_proxy_logger
from litellm.caching import DualCache
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.utils import PrismaClient


@dataclass
class ClaudeTokenInfo:
    """Token information for a Claude OAuth session."""
    user_id: str
    access_token: str
    refresh_token: Optional[str]
    expires_at: int  # Unix timestamp
    scopes: List[str]
    is_max: bool = True
    refresh_count: int = 0
    last_used: Optional[int] = None  # Unix timestamp


class ClaudeTokenManager:
    """
    Manages Claude OAuth tokens with automatic refresh and lifecycle management.
    
    Features:
    - Automatic token refresh before expiration
    - Token validation
    - Multi-user token isolation
    - Performance monitoring
    """
    
    def __init__(
        self,
        oauth_handler: Any,  # ClaudeOAuthHandler instance
        prisma_client: Optional[PrismaClient] = None,
        cache: Optional[DualCache] = None,
        auto_refresh: bool = True,
        refresh_threshold: int = 300,  # seconds before expiry to refresh
    ):
        """
        Initialize token manager.
        
        Args:
            oauth_handler: ClaudeOAuthHandler instance
            prisma_client: Database client for persistent storage
            cache: Cache client for fast access
            auto_refresh: Enable automatic token refresh
            refresh_threshold: Seconds before expiry to trigger refresh
        """
        self.oauth_handler = oauth_handler
        self.prisma_client = prisma_client
        self.cache = cache
        self.auto_refresh = auto_refresh
        self.refresh_threshold = refresh_threshold
        
        # Track active tokens in memory for fast access
        self.active_tokens: Dict[str, ClaudeTokenInfo] = {}
        
        # Track tokens being refreshed to prevent duplicate refreshes
        self.refreshing_tokens: Set[str] = set()
        
        # Background refresh task
        self.refresh_task: Optional[asyncio.Task] = None
        
        if auto_refresh:
            self.start_refresh_monitor()
    
    def start_refresh_monitor(self) -> None:
        """Start background task to monitor and refresh tokens."""
        try:
            if self.refresh_task is None or self.refresh_task.done():
                self.refresh_task = asyncio.create_task(self._refresh_monitor())
                verbose_proxy_logger.info("Started Claude token refresh monitor")
        except RuntimeError:
            # No event loop available yet
            verbose_proxy_logger.debug("Cannot start refresh monitor - no event loop")
    
    async def _refresh_monitor(self) -> None:
        """Background task to monitor and refresh expiring tokens."""
        while self.auto_refresh:
            try:
                await self._check_and_refresh_tokens()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                verbose_proxy_logger.error(f"Token refresh monitor error: {e}")
                await asyncio.sleep(60)
    
    async def _check_and_refresh_tokens(self) -> None:
        """Check all active tokens and refresh those near expiration."""
        current_time = int(time.time())
        refresh_threshold_time = current_time + self.refresh_threshold
        
        tokens_to_refresh = []
        
        for user_id, token_info in self.active_tokens.items():
            if token_info.expires_at <= refresh_threshold_time:
                if user_id not in self.refreshing_tokens and token_info.refresh_token:
                    tokens_to_refresh.append((user_id, token_info))
        
        # Refresh tokens concurrently
        if tokens_to_refresh:
            refresh_tasks = [
                self._refresh_token_with_retry(user_id, token_info)
                for user_id, token_info in tokens_to_refresh
            ]
            await asyncio.gather(*refresh_tasks, return_exceptions=True)
    
    async def _refresh_token_with_retry(
        self,
        user_id: str,
        token_info: ClaudeTokenInfo,
        max_retries: int = 3
    ) -> bool:
        """
        Refresh a token with retry logic.
        
        Args:
            user_id: User ID
            token_info: Current token information
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if refresh successful
        """
        if user_id in self.refreshing_tokens:
            return False
        
        self.refreshing_tokens.add(user_id)
        
        try:
            for attempt in range(max_retries):
                try:
                    verbose_proxy_logger.debug(
                        f"Refreshing token for user {user_id} (attempt {attempt + 1}/{max_retries})"
                    )
                    
                    # Set current tokens in handler
                    self.oauth_handler.access_token = token_info.access_token
                    self.oauth_handler.refresh_token = token_info.refresh_token
                    self.oauth_handler.expires_at = token_info.expires_at
                    
                    # Call OAuth handler to refresh
                    new_token_response = await self.oauth_handler.refresh_access_token()
                    
                    # Update token info with new format
                    new_token_info = ClaudeTokenInfo(
                        user_id=user_id,
                        access_token=new_token_response["accessToken"],
                        refresh_token=new_token_response.get("refreshToken", token_info.refresh_token),
                        expires_at=new_token_response["expiresAt"],
                        scopes=new_token_response.get("scopes", token_info.scopes),
                        is_max=new_token_response.get("isMax", True),
                        refresh_count=token_info.refresh_count + 1,
                        last_used=token_info.last_used
                    )
                    
                    # Store updated token
                    await self.store_token(user_id, new_token_info)
                    
                    verbose_proxy_logger.info(
                        f"Successfully refreshed token for user {user_id} "
                        f"(refresh count: {new_token_info.refresh_count})"
                    )
                    
                    return True
                    
                except Exception as e:
                    if attempt == max_retries - 1:
                        verbose_proxy_logger.error(
                            f"Failed to refresh token for user {user_id} after {max_retries} attempts: {e}"
                        )
                        # Remove invalid token
                        await self.revoke_token(user_id)
                        return False
                    
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        finally:
            self.refreshing_tokens.discard(user_id)
        
        return False
    
    async def store_token(
        self,
        user_id: str,
        token_info: ClaudeTokenInfo
    ) -> None:
        """
        Store a token in cache and database.
        
        Args:
            user_id: User ID
            token_info: Token information to store
        """
        # Store in memory
        self.active_tokens[user_id] = token_info
        
        # Store in cache - use new format
        if self.cache:
            cache_key = f"claude_token:{user_id}"
            cache_data = {
                "accessToken": token_info.access_token,
                "refreshToken": token_info.refresh_token,
                "expiresAt": token_info.expires_at,
                "scopes": token_info.scopes,
                "isMax": token_info.is_max,
                "refresh_count": token_info.refresh_count,
                "last_used": token_info.last_used
            }
            
            ttl = max(60, token_info.expires_at - int(time.time()))
            await self.cache.async_set_cache(cache_key, cache_data, ttl=ttl)
        
        # Store in database (encrypted)
        if self.prisma_client:
            # This would use the actual Prisma schema
            verbose_proxy_logger.debug(f"Storing token in database for user {user_id}")
    
    async def get_token(
        self,
        user_id: str,
        auto_refresh: bool = True
    ) -> Optional[str]:
        """
        Get a valid access token for a user.
        
        Args:
            user_id: User ID
            auto_refresh: Whether to auto-refresh if near expiration
            
        Returns:
            Valid access token or None
        """
        # Check memory first
        token_info = self.active_tokens.get(user_id)
        
        # Check cache if not in memory
        if not token_info and self.cache:
            cache_key = f"claude_token:{user_id}"
            cache_data = await self.cache.async_get_cache(cache_key)
            
            if cache_data:
                token_info = ClaudeTokenInfo(
                    user_id=user_id,
                    access_token=cache_data["accessToken"],
                    refresh_token=cache_data.get("refreshToken"),
                    expires_at=cache_data["expiresAt"],
                    scopes=cache_data.get("scopes", ["org:create_api_key", "user:profile", "user:inference"]),
                    is_max=cache_data.get("isMax", True),
                    refresh_count=cache_data.get("refresh_count", 0),
                    last_used=cache_data.get("last_used")
                )
                self.active_tokens[user_id] = token_info
        
        if not token_info:
            return None
        
        # Update last used time
        token_info.last_used = int(time.time())
        
        # Check if token needs refresh
        current_time = int(time.time())
        
        if auto_refresh and self.auto_refresh:
            refresh_threshold_time = current_time + self.refresh_threshold
            
            if token_info.expires_at <= refresh_threshold_time:
                # Trigger refresh asynchronously
                if user_id not in self.refreshing_tokens and token_info.refresh_token:
                    asyncio.create_task(
                        self._refresh_token_with_retry(user_id, token_info)
                    )
        
        # Return token if still valid
        if token_info.expires_at > current_time:
            return token_info.access_token
        
        return None
    
    async def validate_token(self, token: str) -> Optional[UserAPIKeyAuth]:
        """
        Validate a Claude OAuth token.
        
        Args:
            token: Access token to validate
            
        Returns:
            UserAPIKeyAuth object if valid, None otherwise
        """
        # Find user by token
        user_id = None
        for uid, token_info in self.active_tokens.items():
            if token_info.access_token == token:
                user_id = uid
                break
        
        if user_id:
            # Verify token is not expired
            token_info = self.active_tokens.get(user_id)
            if token_info and token_info.expires_at > int(time.time()):
                # Determine available models based on isMax flag
                models = ["claude-3-sonnet", "claude-3-opus"] if token_info.is_max else ["claude-3-sonnet"]
                
                return UserAPIKeyAuth(
                    api_key=token,
                    user_id=user_id,
                    user_role="claude_oauth_user",
                    team_id=None,
                    models=models
                )
        
        return None
    
    async def revoke_token(self, user_id: str) -> bool:
        """
        Revoke a user's token.
        
        Args:
            user_id: User ID
            
        Returns:
            True if successful
        """
        # Remove from memory
        self.active_tokens.pop(user_id, None)
        
        # Remove from refreshing set
        self.refreshing_tokens.discard(user_id)
        
        # Remove from cache
        if self.cache:
            cache_key = f"claude_token:{user_id}"
            await self.cache.async_delete_cache(cache_key)
        
        # Remove from database
        if self.prisma_client:
            verbose_proxy_logger.debug(f"Removing token from database for user {user_id}")
        
        verbose_proxy_logger.info(f"Revoked token for user {user_id}")
        
        return True
    
    async def get_token_stats(self) -> Dict[str, Any]:
        """
        Get statistics about managed tokens.
        
        Returns:
            Dictionary with token statistics
        """
        current_time = int(time.time())
        
        active_count = len(self.active_tokens)
        expiring_soon = sum(
            1 for token_info in self.active_tokens.values()
            if token_info.expires_at <= current_time + self.refresh_threshold
        )
        
        expired = sum(
            1 for token_info in self.active_tokens.values()
            if token_info.expires_at <= current_time
        )
        
        total_refreshes = sum(
            token_info.refresh_count for token_info in self.active_tokens.values()
        )
        
        max_users = sum(
            1 for token_info in self.active_tokens.values()
            if token_info.is_max
        )
        
        return {
            "active_tokens": active_count,
            "expiring_soon": expiring_soon,
            "expired": expired,
            "refreshing": len(self.refreshing_tokens),
            "total_refreshes": total_refreshes,
            "max_users": max_users,
            "auto_refresh_enabled": self.auto_refresh,
            "refresh_threshold_seconds": self.refresh_threshold
        }
    
    async def cleanup_expired_tokens(self) -> int:
        """
        Remove expired tokens from storage.
        
        Returns:
            Number of tokens cleaned up
        """
        current_time = int(time.time())
        expired_users = [
            user_id for user_id, token_info in self.active_tokens.items()
            if token_info.expires_at <= current_time and not token_info.refresh_token
        ]
        
        for user_id in expired_users:
            await self.revoke_token(user_id)
        
        verbose_proxy_logger.info(f"Cleaned up {len(expired_users)} expired tokens")
        
        return len(expired_users)
    
    def shutdown(self) -> None:
        """Shutdown the token manager and cleanup resources."""
        self.auto_refresh = False
        
        if self.refresh_task and not self.refresh_task.done():
            self.refresh_task.cancel()
        
        verbose_proxy_logger.info("Claude token manager shut down")