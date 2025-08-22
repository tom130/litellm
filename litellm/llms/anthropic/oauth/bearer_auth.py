"""
Claude OAuth Bearer Authentication for Anthropic Provider

Handles OAuth bearer token authentication for Claude API requests.
"""

import os
from typing import Any, Dict, Optional

from litellm._logging import verbose_logger


class ClaudeOAuthBearer:
    """
    Handles OAuth bearer token authentication for Claude API requests.
    
    This class modifies request headers to use OAuth tokens instead of API keys
    when OAuth authentication is enabled.
    """
    
    @staticmethod
    def is_oauth_request(
        api_key: Optional[str],
        metadata: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Check if this request should use OAuth authentication.
        
        Args:
            api_key: API key from request
            metadata: Request metadata
            
        Returns:
            True if OAuth should be used
        """
        # Check metadata flags
        if metadata:
            if metadata.get("using_claude_oauth"):
                return True
            if metadata.get("claude_oauth_token"):
                return True
        
        # Check if api_key looks like an OAuth token (Bearer token)
        if api_key and api_key.startswith("Bearer "):
            token = api_key.replace("Bearer ", "")
            # OAuth tokens don't start with 'sk-ant-' like Anthropic API keys
            if not token.startswith("sk-ant-"):
                return True
        
        # Check environment variable
        if os.getenv("CLAUDE_ACCESS_TOKEN"):
            return True
        
        return False
    
    @staticmethod
    def prepare_oauth_headers(
        headers: Dict[str, str],
        api_key: Optional[str],
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Prepare headers for OAuth authentication.
        
        Args:
            headers: Existing request headers
            api_key: API key or OAuth token
            metadata: Request metadata
            
        Returns:
            Modified headers with OAuth authentication
        """
        # Get OAuth token from various sources
        oauth_token = None
        
        # Priority order: metadata > api_key > environment
        if metadata and metadata.get("claude_oauth_token"):
            oauth_token = metadata["claude_oauth_token"]
        elif api_key and api_key.startswith("Bearer "):
            oauth_token = api_key.replace("Bearer ", "")
        elif not api_key or not api_key.startswith("sk-ant-"):
            # Check environment if no valid API key
            oauth_token = os.getenv("CLAUDE_ACCESS_TOKEN")
        
        if oauth_token:
            # Use OAuth bearer token instead of x-api-key
            headers["Authorization"] = f"Bearer {oauth_token}"
            
            # Remove x-api-key header if present (OAuth takes precedence)
            headers.pop("x-api-key", None)
            
            # Add OAuth beta header - REQUIRED for OAuth
            headers["anthropic-beta"] = "oauth-2025-04-20"
            
            verbose_logger.debug("Using OAuth bearer token for Claude API request")
        
        return headers
    
    @staticmethod
    def handle_oauth_response_error(
        error_response: Dict[str, Any]
    ) -> Optional[str]:
        """
        Handle OAuth-specific error responses.
        
        Args:
            error_response: Error response from API
            
        Returns:
            Error message if OAuth-related, None otherwise
        """
        error_type = error_response.get("error", {}).get("type", "")
        error_message = error_response.get("error", {}).get("message", "")
        
        # Check for OAuth-specific errors
        oauth_errors = {
            "invalid_token": "OAuth token is invalid or expired",
            "insufficient_scope": "OAuth token lacks required scopes",
            "token_expired": "OAuth token has expired",
            "unauthorized": "OAuth authentication failed"
        }
        
        for error_key, message in oauth_errors.items():
            if error_key in error_type.lower() or error_key in error_message.lower():
                return f"{message}: {error_message}"
        
        # Check for 401 status which often indicates auth issues
        if "401" in str(error_response.get("status_code", "")):
            return f"OAuth authentication failed: {error_message}"
        
        return None
    
    @staticmethod
    def should_refresh_token(
        error_response: Dict[str, Any]
    ) -> bool:
        """
        Check if the error indicates token should be refreshed.
        
        Args:
            error_response: Error response from API
            
        Returns:
            True if token should be refreshed
        """
        error_type = error_response.get("error", {}).get("type", "")
        error_message = error_response.get("error", {}).get("message", "")
        status_code = error_response.get("status_code")
        
        # Errors that indicate token refresh needed
        refresh_indicators = [
            "token_expired",
            "invalid_token",
            "expired",
            "unauthorized"
        ]
        
        error_text = f"{error_type} {error_message}".lower()
        
        for indicator in refresh_indicators:
            if indicator in error_text:
                return True
        
        # 401 status usually means auth failed
        if status_code == 401:
            return True
        
        return False
    
    @staticmethod
    def extract_token_from_headers(
        headers: Dict[str, str]
    ) -> Optional[str]:
        """
        Extract OAuth token from request headers.
        
        Args:
            headers: Request headers
            
        Returns:
            OAuth token if found
        """
        # Check Authorization header
        auth_header = headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "")
        
        # Check custom header
        return headers.get("X-Claude-OAuth-Token")