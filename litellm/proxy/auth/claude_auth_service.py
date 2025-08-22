"""
Claude Authentication Service Orchestrator

Provides a unified interface for Claude authentication that:
- Uses existing valid tokens when available
- Automatically refreshes expired tokens
- Initiates OAuth flow when tokens are unavailable or refresh fails
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

from litellm._logging import verbose_proxy_logger
from litellm.proxy.auth.claude_oauth_flow import ClaudeOAuthFlow
from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler
from litellm.proxy.auth.claude_token_manager import ClaudeTokenManager, ClaudeTokenInfo


class ClaudeAuthService:
    """
    Orchestrates Claude authentication by coordinating OAuth flow and token management.
    
    This service provides a seamless authentication experience by:
    1. Using cached valid tokens when available
    2. Refreshing tokens automatically before expiration
    3. Initiating OAuth flow when necessary
    4. Managing token persistence across sessions
    """
    
    def __init__(
        self,
        token_file: Optional[Path] = None,
        encryption_key: Optional[str] = None,
        prisma_client: Optional[Any] = None,
        cache: Optional[Any] = None
    ):
        """
        Initialize the authentication service.
        
        Args:
            token_file: Path to store tokens (defaults to ~/.litellm/claude_tokens.json)
            encryption_key: Key for encrypting stored tokens
            prisma_client: Database client for token storage
            cache: Cache client for temporary storage
        """
        # Token storage location
        self.token_file = token_file or (Path.home() / ".litellm" / "claude_tokens.json")
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.oauth_flow = ClaudeOAuthFlow()
        self.token_manager = ClaudeTokenManager()
        self.oauth_handler = ClaudeOAuthHandler(
            encryption_key=encryption_key,
            prisma_client=prisma_client,
            cache=cache,
            oauth_flow=self.oauth_flow
        )
        
        # Load tokens on initialization
        self._load_tokens()
    
    def _load_tokens(self) -> bool:
        """
        Load tokens from file or environment.
        
        Returns:
            True if tokens were loaded successfully
        """
        # Try loading from file first
        if self.token_file.exists():
            try:
                token_data = json.loads(self.token_file.read_text())
                self.oauth_handler.access_token = token_data.get("accessToken")
                self.oauth_handler.refresh_token = token_data.get("refreshToken")
                self.oauth_handler.expires_at = token_data.get("expiresAt")
                
                verbose_proxy_logger.info(f"Loaded tokens from {self.token_file}")
                return True
            except Exception as e:
                verbose_proxy_logger.warning(f"Failed to load tokens from file: {e}")
        
        # Fall back to environment variables
        if all([
            os.getenv("CLAUDE_ACCESS_TOKEN"),
            os.getenv("CLAUDE_REFRESH_TOKEN"),
            os.getenv("CLAUDE_EXPIRES_AT")
        ]):
            self.oauth_handler.access_token = os.getenv("CLAUDE_ACCESS_TOKEN")
            self.oauth_handler.refresh_token = os.getenv("CLAUDE_REFRESH_TOKEN")
            self.oauth_handler.expires_at = int(os.getenv("CLAUDE_EXPIRES_AT"))
            
            verbose_proxy_logger.info("Loaded tokens from environment variables")
            return True
        
        verbose_proxy_logger.info("No existing tokens found")
        return False
    
    def _save_tokens(self, token_data: Dict[str, Any]) -> None:
        """
        Save tokens to file for persistence.
        
        Args:
            token_data: Token data to save
        """
        try:
            self.token_file.write_text(json.dumps(token_data, indent=2))
            self.token_file.chmod(0o600)  # Restrict permissions
            
            # Update handler with new tokens
            self.oauth_handler.access_token = token_data.get("accessToken")
            self.oauth_handler.refresh_token = token_data.get("refreshToken")
            self.oauth_handler.expires_at = token_data.get("expiresAt")
            
            verbose_proxy_logger.info(f"Saved tokens to {self.token_file}")
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to save tokens: {e}")
    
    async def get_access_token(
        self,
        user_id: Optional[str] = None,
        auto_refresh: bool = True,
        require_oauth: bool = False
    ) -> Optional[str]:
        """
        Get a valid access token, handling all authentication scenarios.
        
        Args:
            user_id: Optional user ID for multi-user scenarios
            auto_refresh: Whether to automatically refresh expired tokens
            require_oauth: Whether to require OAuth flow if no tokens exist
            
        Returns:
            Valid access token or None if authentication fails
        """
        # Try to get valid token from handler
        token = await self.oauth_handler.get_valid_token(
            user_id=user_id,
            auto_refresh=auto_refresh,
            auto_oauth=False  # We handle OAuth flow here
        )
        
        if token:
            return token
        
        # Check if we should initiate OAuth flow
        if require_oauth and not self.oauth_handler.refresh_token:
            verbose_proxy_logger.info(
                "No valid tokens available and OAuth flow required. "
                "Please run: litellm claude login"
            )
            return None
        
        # Try to refresh if we have a refresh token
        if self.oauth_handler.refresh_token:
            try:
                token_data = await self.oauth_handler.refresh_access_token()
                self._save_tokens(token_data)
                return self.oauth_handler.access_token
            except Exception as e:
                verbose_proxy_logger.error(f"Token refresh failed: {e}")
                
                if require_oauth:
                    verbose_proxy_logger.info(
                        "Token refresh failed. OAuth flow required. "
                        "Please run: litellm claude login"
                    )
        
        return None
    
    async def start_oauth_flow(self) -> Dict[str, str]:
        """
        Start the OAuth authentication flow.
        
        Returns:
            Dictionary with authorization_url and state
        """
        auth_url, state = await self.oauth_flow.start_flow()
        
        return {
            "authorization_url": auth_url,
            "state": state,
            "instructions": self.oauth_flow.get_manual_instructions(auth_url)
        }
    
    async def complete_oauth_flow(
        self,
        authorization_code: str,
        state: str
    ) -> Dict[str, Any]:
        """
        Complete the OAuth flow with the authorization code.
        
        Args:
            authorization_code: Code from OAuth callback
            state: State parameter for verification
            
        Returns:
            Token data with access and refresh tokens
        """
        # Exchange code for tokens
        token_data = await self.oauth_flow.complete_flow(authorization_code, state)
        
        # Save tokens
        self._save_tokens(token_data)
        
        # Store in handler's cache if available
        if self.oauth_handler.cache:
            await self.oauth_handler.store_tokens("default", token_data)
        
        return token_data
    
    async def refresh_tokens(self) -> Optional[Dict[str, Any]]:
        """
        Manually refresh tokens.
        
        Returns:
            New token data or None if refresh fails
        """
        if not self.oauth_handler.refresh_token:
            verbose_proxy_logger.warning("No refresh token available")
            return None
        
        try:
            token_data = await self.oauth_handler.refresh_access_token()
            self._save_tokens(token_data)
            return token_data
        except Exception as e:
            verbose_proxy_logger.error(f"Manual token refresh failed: {e}")
            return None
    
    def get_token_info(self) -> ClaudeTokenInfo:
        """
        Get information about current tokens.
        
        Returns:
            Token information including expiration status
        """
        return self.token_manager.get_token_info(
            access_token=self.oauth_handler.access_token,
            refresh_token=self.oauth_handler.refresh_token,
            expires_at=self.oauth_handler.expires_at
        )
    
    def clear_tokens(self) -> None:
        """Clear all stored tokens."""
        # Clear from handler
        self.oauth_handler.access_token = None
        self.oauth_handler.refresh_token = None
        self.oauth_handler.expires_at = None
        
        # Clear from file
        if self.token_file.exists():
            self.token_file.unlink()
            verbose_proxy_logger.info(f"Removed token file: {self.token_file}")
        
        # Clear OAuth state files
        self.oauth_flow.cleanup_expired_states()
        
        verbose_proxy_logger.info("All tokens cleared")
    
    async def ensure_authenticated(
        self,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Ensure user is authenticated, initiating OAuth if necessary.
        
        Args:
            user_id: Optional user ID for multi-user scenarios
            
        Returns:
            True if authentication is successful
        """
        # Try to get access token
        token = await self.get_access_token(
            user_id=user_id,
            auto_refresh=True,
            require_oauth=False
        )
        
        if token:
            verbose_proxy_logger.info("Authentication successful with existing tokens")
            return True
        
        # No valid tokens - OAuth flow required
        verbose_proxy_logger.info(
            "Authentication required. Please run: litellm claude login"
        )
        return False
    
    def get_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests.
        
        Returns:
            Headers with Bearer token and beta header
            
        Raises:
            ValueError: If no valid token is available
        """
        if not self.oauth_handler.access_token:
            raise ValueError(
                "No access token available. Please authenticate first: litellm claude login"
            )
        
        return self.oauth_handler.get_auth_headers()


# Singleton instance for easy access
_auth_service: Optional[ClaudeAuthService] = None


def get_auth_service(
    token_file: Optional[Path] = None,
    encryption_key: Optional[str] = None,
    prisma_client: Optional[Any] = None,
    cache: Optional[Any] = None
) -> ClaudeAuthService:
    """
    Get or create the singleton auth service instance.
    
    Args:
        token_file: Path to store tokens
        encryption_key: Key for encrypting stored tokens
        prisma_client: Database client for token storage
        cache: Cache client for temporary storage
        
    Returns:
        ClaudeAuthService instance
    """
    global _auth_service
    
    if _auth_service is None:
        _auth_service = ClaudeAuthService(
            token_file=token_file,
            encryption_key=encryption_key,
            prisma_client=prisma_client,
            cache=cache
        )
    
    return _auth_service


async def quick_authenticate() -> Optional[str]:
    """
    Quick authentication helper for simple use cases.
    
    Returns:
        Valid access token or None if authentication fails
    """
    service = get_auth_service()
    return await service.get_access_token(
        auto_refresh=True,
        require_oauth=False
    )