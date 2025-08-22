"""
Claude OAuth Flow Implementation

Implements the OAuth 2.0 + PKCE flow for initial token acquisition from Claude.ai.
Based on the working implementation from claude-code-login.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx

from litellm._logging import verbose_proxy_logger


@dataclass
class OAuthState:
    """OAuth state data for PKCE flow."""
    state: str
    code_verifier: str
    timestamp: int
    expires_at: int


class ClaudeOAuthFlow:
    """
    Handles OAuth 2.0 + PKCE flow for Claude authentication.
    
    This class implements the initial token acquisition flow required when:
    - User has no tokens
    - Refresh token has expired
    - User wants to re-authenticate
    
    Based on the legitimate OAuth flow from claude-code-login.
    """
    
    # OAuth Configuration (from claude-code-login)
    CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
    TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
    REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
    SCOPES = ["org:create_api_key", "user:profile", "user:inference"]
    
    # State management
    STATE_FILE_PREFIX = "claude_oauth_state"
    STATE_EXPIRY_SECONDS = 600  # 10 minutes
    
    def __init__(self, state_dir: Optional[str] = None):
        """
        Initialize OAuth flow handler.
        
        Args:
            state_dir: Directory for storing OAuth state files.
                      Defaults to system temp directory.
        """
        self.state_dir = Path(state_dir) if state_dir else Path("/tmp")
        self.state_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate cryptographically secure random verifier (32 bytes)
        code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode('utf-8').rstrip('=')
        
        # Create SHA256 challenge
        challenge_bytes = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
        
        verbose_proxy_logger.debug("Generated PKCE pair for OAuth flow")
        
        return code_verifier, code_challenge
    
    def generate_state(self) -> str:
        """
        Generate secure random state for CSRF protection.
        
        Returns:
            Random state string (32 bytes hex encoded)
        """
        state = secrets.token_hex(32)
        verbose_proxy_logger.debug("Generated OAuth state parameter")
        return state
    
    def build_authorization_url(
        self,
        state: str,
        code_challenge: str,
        scopes: Optional[list] = None
    ) -> str:
        """
        Build the OAuth authorization URL.
        
        Args:
            state: State parameter for CSRF protection
            code_challenge: PKCE code challenge
            scopes: OAuth scopes (defaults to class SCOPES)
            
        Returns:
            Complete authorization URL
        """
        scopes = scopes or self.SCOPES
        
        params = {
            "code": "true",  # Required by Claude OAuth
            "client_id": self.CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self.REDIRECT_URI,
            "scope": " ".join(scopes),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state
        }
        
        auth_url = f"{self.AUTHORIZE_URL}?{urlencode(params)}"
        
        verbose_proxy_logger.info(
            f"Built authorization URL with scopes: {', '.join(scopes)}"
        )
        
        return auth_url
    
    async def save_state(
        self,
        state: str,
        code_verifier: str
    ) -> str:
        """
        Save OAuth state to file for later verification.
        
        Args:
            state: State parameter
            code_verifier: PKCE code verifier
            
        Returns:
            Path to saved state file
        """
        state_data = OAuthState(
            state=state,
            code_verifier=code_verifier,
            timestamp=int(time.time()),
            expires_at=int(time.time()) + self.STATE_EXPIRY_SECONDS
        )
        
        # Create state file path
        state_file = self.state_dir / f"{self.STATE_FILE_PREFIX}_{state}.json"
        
        # Save state data
        state_dict = {
            "state": state_data.state,
            "code_verifier": state_data.code_verifier,
            "timestamp": state_data.timestamp,
            "expires_at": state_data.expires_at
        }
        
        state_file.write_text(json.dumps(state_dict, indent=2))
        
        # Set restrictive permissions (owner read/write only)
        state_file.chmod(0o600)
        
        verbose_proxy_logger.debug(f"Saved OAuth state to {state_file}")
        
        return str(state_file)
    
    async def load_state(self, state: str) -> Optional[OAuthState]:
        """
        Load previously saved OAuth state.
        
        Args:
            state: State parameter to load
            
        Returns:
            OAuthState object if found and valid, None otherwise
        """
        state_file = self.state_dir / f"{self.STATE_FILE_PREFIX}_{state}.json"
        
        if not state_file.exists():
            verbose_proxy_logger.warning(f"State file not found: {state_file}")
            return None
        
        try:
            state_dict = json.loads(state_file.read_text())
            state_data = OAuthState(**state_dict)
            
            # Check if state has expired
            if time.time() > state_data.expires_at:
                verbose_proxy_logger.warning(
                    f"OAuth state expired (older than {self.STATE_EXPIRY_SECONDS} seconds)"
                )
                # Clean up expired state
                state_file.unlink(missing_ok=True)
                return None
            
            verbose_proxy_logger.debug(f"Loaded valid OAuth state from {state_file}")
            return state_data
            
        except Exception as e:
            verbose_proxy_logger.error(f"Failed to load OAuth state: {e}")
            return None
    
    async def exchange_code(
        self,
        authorization_code: str,
        state: str
    ) -> Dict[str, any]:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            authorization_code: The authorization code from callback
            state: State parameter for verification
            
        Returns:
            Token response with accessToken, refreshToken, expiresAt
            
        Raises:
            ValueError: If state is invalid or expired
            httpx.HTTPStatusError: If token exchange fails
        """
        # Clean up code (remove any fragments)
        clean_code = authorization_code.split('#')[0].split('&')[0]
        
        # Load and verify state
        state_data = await self.load_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")
        
        # Prepare token exchange request
        params = {
            "grant_type": "authorization_code",
            "client_id": self.CLIENT_ID,
            "code": clean_code,
            "redirect_uri": self.REDIRECT_URI,
            "code_verifier": state_data.code_verifier,
            "state": state
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://claude.ai/",
            "Origin": "https://claude.ai"
        }
        
        verbose_proxy_logger.info("Exchanging authorization code for tokens")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                json=params,
                headers=headers,
                timeout=30.0
            )
            
            if not response.is_success:
                error_text = response.text
                verbose_proxy_logger.error(
                    f"Token exchange failed: {response.status_code} - {error_text}"
                )
                response.raise_for_status()
            
            token_data = response.json()
        
        # Transform to expected format
        result = {
            "accessToken": token_data["access_token"],
            "refreshToken": token_data["refresh_token"],
            "expiresAt": int(time.time() + token_data.get("expires_in", 3600)),
            "scopes": token_data.get("scope", " ".join(self.SCOPES)).split(),
            "isMax": True  # Assuming OAuth tokens are for Claude Max
        }
        
        # Clean up state file after successful exchange
        state_file = self.state_dir / f"{self.STATE_FILE_PREFIX}_{state}.json"
        state_file.unlink(missing_ok=True)
        
        verbose_proxy_logger.info(
            f"Successfully exchanged code for tokens. "
            f"Token expires at: {result['expiresAt']}"
        )
        
        return result
    
    async def start_flow(self) -> Tuple[str, str]:
        """
        Start the OAuth flow by generating necessary parameters.
        
        Returns:
            Tuple of (authorization_url, state)
        """
        # Generate PKCE pair
        code_verifier, code_challenge = self.generate_pkce_pair()
        
        # Generate state
        state = self.generate_state()
        
        # Save state and verifier
        await self.save_state(state, code_verifier)
        
        # Build authorization URL
        auth_url = self.build_authorization_url(state, code_challenge)
        
        verbose_proxy_logger.info(
            "Started OAuth flow. User should visit authorization URL."
        )
        
        return auth_url, state
    
    async def complete_flow(
        self,
        authorization_code: str,
        state: str
    ) -> Dict[str, any]:
        """
        Complete the OAuth flow by exchanging code for tokens.
        
        Args:
            authorization_code: Code from OAuth callback
            state: State parameter for verification
            
        Returns:
            Token data with accessToken, refreshToken, expiresAt
        """
        return await self.exchange_code(authorization_code, state)
    
    def cleanup_expired_states(self) -> int:
        """
        Clean up expired OAuth state files.
        
        Returns:
            Number of files cleaned up
        """
        cleaned = 0
        current_time = time.time()
        
        for state_file in self.state_dir.glob(f"{self.STATE_FILE_PREFIX}_*.json"):
            try:
                state_dict = json.loads(state_file.read_text())
                if current_time > state_dict.get("expires_at", 0):
                    state_file.unlink()
                    cleaned += 1
                    verbose_proxy_logger.debug(f"Cleaned up expired state: {state_file.name}")
            except Exception as e:
                verbose_proxy_logger.warning(f"Error cleaning state file {state_file}: {e}")
        
        if cleaned > 0:
            verbose_proxy_logger.info(f"Cleaned up {cleaned} expired OAuth state files")
        
        return cleaned
    
    def get_manual_instructions(self, auth_url: str) -> str:
        """
        Get user-friendly instructions for manual OAuth flow.
        
        Args:
            auth_url: The authorization URL
            
        Returns:
            Instructions text
        """
        instructions = f"""
Claude OAuth Authentication Required
====================================

1. Open this URL in your browser:
   {auth_url}

2. Sign in to Claude and authorize the application

3. You'll be redirected to a URL like:
   https://console.anthropic.com/oauth/code/callback?code=CODE&state=STATE

4. Copy the CODE value from the URL

5. Complete authentication by providing the code

Note: The authorization code expires quickly, so complete this process promptly.
"""
        return instructions