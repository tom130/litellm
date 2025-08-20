"""
Claude OAuth Middleware

Middleware to inject OAuth tokens into requests to Claude/Anthropic models.
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.claude_token_manager import ClaudeTokenManager


class ClaudeOAuthMiddleware:
    """
    Middleware to handle OAuth token injection for Claude model requests.
    
    This middleware:
    1. Detects requests to Claude models
    2. Retrieves OAuth tokens for authenticated users
    3. Injects tokens into request headers
    4. Handles token refresh transparently
    """
    
    def __init__(
        self,
        token_manager: ClaudeTokenManager,
        enabled: bool = True,
        fallback_to_api_key: bool = True
    ):
        """
        Initialize middleware.
        
        Args:
            token_manager: Claude token manager instance
            enabled: Whether OAuth is enabled
            fallback_to_api_key: Whether to fallback to API key if OAuth unavailable
        """
        self.token_manager = token_manager
        self.enabled = enabled
        self.fallback_to_api_key = fallback_to_api_key
        
        # Claude model patterns
        self.claude_models = {
            "claude-3-opus",
            "claude-3-sonnet", 
            "claude-3-haiku",
            "claude-2.1",
            "claude-2.0",
            "claude-instant",
            "anthropic/claude",  # Generic pattern
        }
    
    def is_claude_model(self, model: str) -> bool:
        """
        Check if the model is a Claude model.
        
        Args:
            model: Model name from request
            
        Returns:
            True if this is a Claude model
        """
        if not model:
            return False
        
        model_lower = model.lower()
        
        # Check exact matches and patterns
        for pattern in self.claude_models:
            if pattern in model_lower or model_lower.startswith(pattern):
                return True
        
        # Check for Anthropic prefix
        if model_lower.startswith("anthropic/"):
            return True
        
        return False
    
    async def process_request(
        self,
        request: Request,
        request_data: Dict[str, Any],
        user_api_key_dict: UserAPIKeyAuth
    ) -> Dict[str, Any]:
        """
        Process a request and inject OAuth token if needed.
        
        Args:
            request: FastAPI request object
            request_data: Parsed request data
            user_api_key_dict: User authentication information
            
        Returns:
            Modified request data with OAuth token injected
        """
        if not self.enabled:
            return request_data
        
        # Check if this is a Claude model request
        model = request_data.get("model")
        if not self.is_claude_model(model):
            return request_data
        
        # Get user ID
        user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias
        
        if not user_id:
            verbose_proxy_logger.debug("No user ID found for OAuth token injection")
            return request_data
        
        try:
            # Get valid OAuth token
            oauth_token = await self.token_manager.get_token(user_id)
            
            if oauth_token:
                verbose_proxy_logger.debug(f"Injecting OAuth token for user {user_id}")
                
                # Add OAuth token to request
                if "metadata" not in request_data:
                    request_data["metadata"] = {}
                
                # Store OAuth token in metadata for the Anthropic handler
                request_data["metadata"]["claude_oauth_token"] = oauth_token
                
                # Also set as authorization header if needed
                if "api_key" not in request_data or not request_data.get("api_key"):
                    request_data["api_key"] = f"Bearer {oauth_token}"
                
                # Mark that OAuth is being used
                request_data["metadata"]["using_claude_oauth"] = True
                
                verbose_proxy_logger.info(
                    f"OAuth token injected for Claude model request: {model}"
                )
            elif not self.fallback_to_api_key:
                # No OAuth token and no fallback
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Claude OAuth token required but not found. Please authenticate at /auth/claude/authorize"
                )
            else:
                verbose_proxy_logger.debug(
                    f"No OAuth token found for user {user_id}, using API key fallback"
                )
        
        except HTTPException:
            raise
        except Exception as e:
            verbose_proxy_logger.error(f"Error injecting OAuth token: {e}")
            if not self.fallback_to_api_key:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to process OAuth token"
                )
        
        return request_data
    
    async def check_oauth_requirement(
        self,
        model: str,
        user_api_key_dict: UserAPIKeyAuth
    ) -> Optional[str]:
        """
        Check if OAuth is required for a model and user.
        
        Args:
            model: Model name
            user_api_key_dict: User authentication
            
        Returns:
            Error message if OAuth required but not available, None otherwise
        """
        if not self.enabled:
            return None
        
        if not self.is_claude_model(model):
            return None
        
        # Check if OAuth is mandatory (no fallback)
        if not self.fallback_to_api_key:
            user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias
            
            if user_id:
                token = await self.token_manager.get_token(user_id, auto_refresh=False)
                if not token:
                    return (
                        f"Claude OAuth authentication required for model '{model}'. "
                        f"Please authenticate at /auth/claude/authorize"
                    )
        
        return None
    
    async def validate_oauth_token(
        self,
        token: str
    ) -> Optional[UserAPIKeyAuth]:
        """
        Validate an OAuth token.
        
        Args:
            token: OAuth access token
            
        Returns:
            UserAPIKeyAuth object if valid, None otherwise
        """
        return await self.token_manager.validate_token(token)
    
    def extract_oauth_token(
        self,
        request: Request,
        request_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract OAuth token from request.
        
        Args:
            request: FastAPI request
            request_data: Request data
            
        Returns:
            OAuth token if found
        """
        # Check metadata first
        metadata = request_data.get("metadata", {})
        if metadata.get("claude_oauth_token"):
            return metadata["claude_oauth_token"]
        
        # Check authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            # Validate it's an OAuth token (not an API key)
            if not token.startswith("sk-"):
                return token
        
        # Check custom header
        claude_token = request.headers.get("x-claude-oauth-token")
        if claude_token:
            return claude_token
        
        return None