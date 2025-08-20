"""
Claude OAuth API Endpoints

FastAPI endpoints for Claude OAuth authentication flow.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler
from litellm.proxy.auth.claude_token_manager import ClaudeTokenManager


router = APIRouter(prefix="/auth/claude", tags=["Claude OAuth"])


# Global instances (will be initialized by proxy server)
oauth_handler: Optional[ClaudeOAuthHandler] = None
token_manager: Optional[ClaudeTokenManager] = None


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


@router.get("/authorize")
async def authorize(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
    scopes: Optional[str] = Query(None, description="Space-separated OAuth scopes"),
    redirect_uri: Optional[str] = Query(None, description="Custom redirect URI")
):
    """
    Initiate Claude OAuth authorization flow.
    
    This endpoint generates an authorization URL with PKCE parameters
    and redirects the user to Claude's OAuth authorization page.
    """
    handler = get_oauth_handler()
    
    # Get user ID from authenticated session
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required for OAuth flow"
        )
    
    # Parse scopes if provided
    scope_list = scopes.split() if scopes else None
    
    # Additional parameters for OAuth flow
    additional_params = {}
    if redirect_uri:
        additional_params["redirect_uri"] = redirect_uri
    
    try:
        # Generate authorization URL with PKCE
        auth_url, state, code_verifier = handler.get_authorization_url(
            user_id=user_id,
            scopes=scope_list,
            additional_params=additional_params
        )
        
        # Store code_verifier in session or return to client
        # For browser-based flow, redirect directly
        return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        verbose_proxy_logger.error(f"Failed to generate authorization URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Claude"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    error: Optional[str] = Query(None, description="Error from OAuth provider"),
    error_description: Optional[str] = Query(None, description="Error description")
):
    """
    Handle OAuth callback from Claude.
    
    This endpoint receives the authorization code from Claude's OAuth server
    and exchanges it for access and refresh tokens.
    """
    # Check for OAuth errors
    if error:
        verbose_proxy_logger.error(f"OAuth error: {error} - {error_description}")
        return HTMLResponse(
            content=f"""
            <html>
                <body>
                    <h2>Authentication Failed</h2>
                    <p>Error: {error}</p>
                    <p>{error_description or 'No additional details'}</p>
                    <p><a href="/">Return to home</a></p>
                </body>
            </html>
            """,
            status_code=400
        )
    
    handler = get_oauth_handler()
    manager = get_token_manager()
    
    try:
        # Exchange code for tokens
        token_response = await handler.exchange_code_for_token(code, state)
        
        # Create token info for storage
        from datetime import datetime, timedelta, timezone
        from litellm.proxy.auth.claude_token_manager import ClaudeTokenInfo
        
        token_info = ClaudeTokenInfo(
            user_id=token_response["user_id"],
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token"),
            expires_at=datetime.now(timezone.utc) + timedelta(
                seconds=token_response.get("expires_in", 3600)
            ),
            scopes=token_response.get("scope", "").split(),
            created_at=datetime.now(timezone.utc)
        )
        
        # Store token
        await manager.store_token(token_response["user_id"], token_info)
        
        # Return success page
        return HTMLResponse(
            content=f"""
            <html>
                <head>
                    <title>Authentication Successful</title>
                    <style>
                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            max-width: 600px;
                            margin: 50px auto;
                            padding: 20px;
                        }}
                        .success {{
                            background: #d4edda;
                            border: 1px solid #c3e6cb;
                            border-radius: 4px;
                            padding: 15px;
                            margin-bottom: 20px;
                        }}
                        code {{
                            background: #f8f9fa;
                            padding: 2px 5px;
                            border-radius: 3px;
                        }}
                    </style>
                </head>
                <body>
                    <div class="success">
                        <h2>✅ Authentication Successful!</h2>
                        <p>Your Claude OAuth connection has been established.</p>
                    </div>
                    
                    <h3>Next Steps:</h3>
                    <p>You can now use Claude models through the LiteLLM proxy.</p>
                    
                    <p>Example request:</p>
                    <pre><code>curl -X POST http://localhost:4000/chat/completions \\
  -H "Authorization: Bearer YOUR_LITELLM_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "model": "claude-3-sonnet",
    "messages": [{{"role": "user", "content": "Hello!"}}]
  }}'</code></pre>
                    
                    <p>Token expires in: {token_response.get('expires_in', 3600)} seconds</p>
                    
                    <script>
                        // Auto-close window after 5 seconds if opened as popup
                        setTimeout(() => {{
                            if (window.opener) {{
                                window.close();
                            }}
                        }}, 5000);
                    </script>
                </body>
            </html>
            """,
            status_code=200
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        verbose_proxy_logger.error(f"OAuth callback error: {e}")
        return HTMLResponse(
            content=f"""
            <html>
                <body>
                    <h2>Authentication Failed</h2>
                    <p>Failed to complete OAuth flow: {str(e)}</p>
                    <p><a href="/auth/claude/authorize">Try again</a></p>
                </body>
            </html>
            """,
            status_code=500
        )


@router.post("/refresh")
async def refresh_token(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth)
):
    """
    Manually refresh the OAuth token for the authenticated user.
    
    This endpoint allows users to manually trigger a token refresh
    before the automatic refresh occurs.
    """
    handler = get_oauth_handler()
    manager = get_token_manager()
    
    user_id = user_api_key_dict.user_id or user_api_key_dict.key_alias
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required"
        )
    
    # Get current token
    token = await manager.get_token(user_id, auto_refresh=False)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OAuth token found for user"
        )
    
    # Get token info
    token_info = manager.active_tokens.get(user_id)
    
    if not token_info or not token_info.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refresh token available"
        )
    
    try:
        # Perform refresh
        success = await manager._refresh_token_with_retry(user_id, token_info)
        
        if success:
            new_token = await manager.get_token(user_id, auto_refresh=False)
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Token refreshed successfully",
                    "expires_in": 3600  # This would come from actual token response
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh token"
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