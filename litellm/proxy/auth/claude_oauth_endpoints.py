"""
Claude OAuth API Endpoints

FastAPI endpoints for Claude OAuth authentication flow.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status, Body
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler
from litellm.proxy.auth.claude_token_manager import ClaudeTokenManager
from litellm.proxy.auth.claude_oauth_flow import ClaudeOAuthFlow

# Request models
class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


router = APIRouter(prefix="/auth/claude", tags=["Claude OAuth"])


# Global instances (will be initialized by proxy server)
oauth_handler: Optional[ClaudeOAuthHandler] = None
token_manager: Optional[ClaudeTokenManager] = None
oauth_flow: Optional[ClaudeOAuthFlow] = None


def initialize_oauth_endpoints(
    prisma_client: Optional[Any] = None,
    encryption_key: Optional[str] = None,
    cache: Optional[Any] = None
):
    """Initialize OAuth endpoints with database and cache connections."""
    global oauth_handler, token_manager, oauth_flow
    
    # Initialize OAuth handler with database support
    oauth_handler = ClaudeOAuthHandler(
        prisma_client=prisma_client,
        encryption_key=encryption_key
    )
    
    # Initialize token manager
    token_manager = ClaudeTokenManager(
        oauth_handler=oauth_handler,
        prisma_client=prisma_client,
        cache=cache
    )
    
    # Initialize OAuth flow
    oauth_flow = ClaudeOAuthFlow()
    
    verbose_proxy_logger.info("Claude OAuth endpoints initialized")


def get_oauth_handler() -> ClaudeOAuthHandler:
    """Get OAuth handler instance."""
    if not oauth_handler:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Claude OAuth not configured"
        )
    return oauth_handler


def get_token_manager() -> ClaudeTokenManager:
    """Get token manager instance."""
    if not token_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Claude token manager not configured"
        )
    return token_manager


@router.post("/start")
async def start_oauth(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Start Claude OAuth flow and return authorization URL.
    
    Returns:
        JSON with authorization_url and state for the client to handle.
    """
    if not oauth_flow:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth flow not initialized"
        )
    
    # Get user ID from authenticated session
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias or "default_user"
    
    try:
        # Start OAuth flow
        auth_url, state = await oauth_flow.start_flow()
        
        # Store state with user association (could use cache or session)
        if oauth_handler:
            # Store state temporarily for validation
            await oauth_handler.store_state(state, user_id)
        
        return JSONResponse({
            "authorization_url": auth_url,
            "state": state,
            "message": "Visit the authorization URL to complete authentication"
        })
        
    except Exception as e:
        verbose_proxy_logger.error(f"Failed to start OAuth flow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/callback")
async def callback(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
    body: Optional[OAuthCallbackRequest] = None,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """
    Handle OAuth callback with authorization code.
    
    This endpoint exchanges the authorization code for tokens and stores them.
    Supports both automatic callback and manual code entry.
    Accepts both JSON body and query parameters.
    """
    # Get code and state from either body or query params
    if body:
        code = body.code
        state = body.state
    
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required parameters: code and state"
        )
    if not oauth_flow or not oauth_handler:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth not initialized"
        )
    
    # Get user ID
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias or "default_user"
    
    try:
        # Check if this is a manual code entry
        is_manual = state == "manual_entry"
        
        if is_manual:
            # For manual entry, we need to handle the code directly
            # without state verification
            verbose_proxy_logger.info(f"Processing manual OAuth code entry for user {user_id}")
            
            # Exchange code for tokens directly
            token_data = await oauth_flow.exchange_code(code)
        else:
            # Normal OAuth flow with state verification
            token_data = await oauth_flow.complete_flow(code, state)
        
        # Store tokens using handler
        success = await oauth_handler.store_tokens(
            user_id=user_id,
            token_data=token_data
        )
        
        if success:
            return JSONResponse({
                "success": True,
                "message": "OAuth authentication successful",
                "expires_in": token_data.get("expiresIn", 3600),
                "manual": is_manual
            })
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store tokens"
            )
        
    except Exception as e:
        verbose_proxy_logger.error(f"OAuth callback error: {e}")
        # Provide more specific error message for manual entry
        if state == "manual_entry":
            error_msg = "Invalid or expired authentication code. Please get a new code from Claude."
        else:
            error_msg = f"Failed to complete OAuth flow: {str(e)}"
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


@router.get("/status")
async def get_status(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Check OAuth authentication status for the current user.
    """
    if not oauth_handler:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth not initialized"
        )
    
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias or "default_user"
    
    try:
        # Check if user has valid tokens
        token = await oauth_handler.get_valid_token(user_id=user_id, auto_refresh=False)
        
        if token:
            # Get token expiration info
            expires_in = oauth_handler.get_token_expiry(user_id)
            
            return JSONResponse({
                "authenticated": True,
                "user_id": user_id,
                "expires_in": expires_in,
                "needs_refresh": expires_in < 300 if expires_in else False
            })
        else:
            return JSONResponse({
                "authenticated": False,
                "user_id": user_id,
                "message": "No valid OAuth tokens found"
            })
    
    except Exception as e:
        verbose_proxy_logger.error(f"Failed to get OAuth status: {e}")
        return JSONResponse({
            "authenticated": False,
            "error": str(e)
        })


@router.post("/refresh")
async def refresh_token(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth)
):
    """
    Manually refresh the OAuth token for the authenticated user.
    """
    if not oauth_handler:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth not initialized"
        )
    
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias or "default_user"
    
    try:
        # Refresh token
        new_token = await oauth_handler.refresh_access_token(user_id=user_id)
        
        if new_token:
            return JSONResponse({
                "success": True,
                "message": "Token refreshed successfully"
            })
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No refresh token available or refresh failed"
            )
            
    except Exception as e:
        verbose_proxy_logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/status")
async def oauth_status(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth)
):
    """
    Check OAuth status for the authenticated user.
    
    Returns information about the user's OAuth connection status,
    token validity, and expiration time.
    """
    manager = get_token_manager()
    
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias
    
    if not user_id:
        return JSONResponse(
            content={
                "authenticated": False,
                "message": "User ID not found"
            }
        )
    
    # Check for valid token
    token = await manager.get_token(user_id, auto_refresh=False)
    
    if not token:
        return JSONResponse(
            content={
                "authenticated": False,
                "user_id": user_id,
                "message": "No OAuth token found"
            }
        )
    
    # Get token info
    token_info = manager.active_tokens.get(user_id)
    
    if token_info:
        from datetime import datetime, timezone
        
        current_time = datetime.now(timezone.utc)
        time_until_expiry = (token_info.expires_at - current_time).total_seconds()
        
        return JSONResponse(
            content={
                "authenticated": True,
                "user_id": user_id,
                "expires_in": int(time_until_expiry),
                "expires_at": token_info.expires_at.isoformat(),
                "scopes": token_info.scopes,
                "refresh_count": token_info.refresh_count,
                "last_used": token_info.last_used.isoformat() if token_info.last_used else None,
                "auto_refresh_enabled": manager.auto_refresh
            }
        )
    
    return JSONResponse(
        content={
            "authenticated": False,
            "user_id": user_id,
            "message": "Token info not available"
        }
    )


@router.delete("/revoke")
async def revoke_token(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth)
):
    """
    Revoke the OAuth token for the authenticated user.
    
    This endpoint allows users to disconnect their Claude OAuth connection
    and revoke their stored tokens.
    """
    manager = get_token_manager()
    
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required"
        )
    
    # Revoke token
    success = await manager.revoke_token(user_id)
    
    if success:
        return JSONResponse(
            content={
                "success": True,
                "message": "OAuth token revoked successfully"
            }
        )
    else:
        return JSONResponse(
            content={
                "success": False,
                "message": "No token found to revoke"
            }
        )


@router.get("/health")
async def health_check():
    """
    Health check endpoint for Claude OAuth service.
    
    Returns the health status of the OAuth system including
    token manager statistics.
    """
    if not oauth_handler or not token_manager:
        return JSONResponse(
            content={
                "status": "unhealthy",
                "message": "OAuth not configured"
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    try:
        stats = await token_manager.get_token_stats()
        
        return JSONResponse(
            content={
                "status": "healthy",
                "oauth_configured": True,
                "token_stats": stats
            }
        )
    except Exception as e:
        verbose_proxy_logger.error(f"Health check error: {e}")
        return JSONResponse(
            content={
                "status": "unhealthy",
                "message": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )