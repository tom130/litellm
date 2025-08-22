"""
Tests for Claude OAuth Token Management

Tests token storage, refresh, and bearer authentication.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler
from litellm.proxy.auth.claude_token_manager import ClaudeTokenInfo, ClaudeTokenManager


class TestClaudeOAuthHandler:
    """Test suite for ClaudeOAuthHandler token management."""
    
    @pytest.fixture
    def oauth_handler(self):
        """Create OAuth handler instance with test tokens."""
        return ClaudeOAuthHandler(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_at=int(time.time()) + 3600,  # 1 hour from now
            encryption_key=Fernet.generate_key()
        )
    
    def test_init_from_environment(self):
        """Test initialization from environment variables."""
        # Set environment variables
        os.environ["CLAUDE_ACCESS_TOKEN"] = "env-access-token"
        os.environ["CLAUDE_REFRESH_TOKEN"] = "env-refresh-token"
        os.environ["CLAUDE_EXPIRES_AT"] = str(int(time.time()) + 7200)
        
        try:
            handler = ClaudeOAuthHandler()
            
            assert handler.access_token == "env-access-token"
            assert handler.refresh_token == "env-refresh-token"
            assert handler.expires_at == int(os.environ["CLAUDE_EXPIRES_AT"])
        finally:
            # Clean up
            del os.environ["CLAUDE_ACCESS_TOKEN"]
            del os.environ["CLAUDE_REFRESH_TOKEN"]
            del os.environ["CLAUDE_EXPIRES_AT"]
    
    def test_get_token_data(self, oauth_handler):
        """Test getting token data in correct format."""
        token_data = oauth_handler.get_token_data()
        
        assert token_data["accessToken"] == "test-access-token"
        assert token_data["refreshToken"] == "test-refresh-token"
        assert "expiresAt" in token_data
        assert token_data["scopes"] == ["org:create_api_key", "user:profile", "user:inference"]
        assert token_data["isMax"] == True
    
    def test_is_token_expired(self, oauth_handler):
        """Test token expiration checking."""
        # Token expires in 1 hour, should not be expired
        assert oauth_handler.is_token_expired(buffer_seconds=0) == False
        
        # With 2 hour buffer, should be considered expired
        assert oauth_handler.is_token_expired(buffer_seconds=7200) == True
        
        # Set expired token
        oauth_handler.expires_at = int(time.time()) - 100
        assert oauth_handler.is_token_expired() == True
    
    def test_get_auth_headers(self, oauth_handler):
        """Test authentication header generation."""
        headers = oauth_handler.get_auth_headers()
        
        assert headers["Authorization"] == "Bearer test-access-token"
        assert headers["anthropic-beta"] == "oauth-2025-04-20"
    
    def test_get_auth_headers_no_token(self):
        """Test that auth headers raise error without token."""
        handler = ClaudeOAuthHandler(
            access_token=None,
            refresh_token="test-refresh"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            handler.get_auth_headers()
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_refresh_access_token(self, oauth_handler):
        """Test token refresh."""
        with patch('litellm.llms.custom_httpx.http_handler.get_async_httpx_client') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600
            }
            mock_response.raise_for_status = MagicMock()
            
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http
            
            # Refresh token
            token_data = await oauth_handler.refresh_access_token()
            
            # Verify response format
            assert token_data["accessToken"] == "new-access-token"
            assert token_data["refreshToken"] == "new-refresh-token"
            assert "expiresAt" in token_data
            assert token_data["isMax"] == True
            
            # Verify handler state updated
            assert oauth_handler.access_token == "new-access-token"
            assert oauth_handler.refresh_token == "new-refresh-token"
            
            # Verify API call
            mock_http.post.assert_called_once()
            call_args = mock_http.post.call_args
            assert call_args[0][0] == "https://api.anthropic.com/v1/oauth/refresh"
            assert call_args[1]["json"]["refresh_token"] == "test-refresh-token"
            assert call_args[1]["headers"]["anthropic-beta"] == "oauth-2025-04-20"
    
    @pytest.mark.asyncio
    async def test_refresh_without_refresh_token(self):
        """Test that refresh fails without refresh token."""
        handler = ClaudeOAuthHandler(
            access_token="test-access",
            refresh_token=None
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await handler.refresh_access_token()
        assert exc_info.value.status_code == 401
    
    def test_encrypt_decrypt_token(self, oauth_handler):
        """Test token encryption and decryption."""
        original_token = "test-token-12345"
        
        # Encrypt
        encrypted = oauth_handler.encrypt_token(original_token)
        assert encrypted != original_token
        assert isinstance(encrypted, str)
        
        # Decrypt
        decrypted = oauth_handler.decrypt_token(encrypted)
        assert decrypted == original_token
    
    @pytest.mark.asyncio
    async def test_get_valid_token_with_refresh(self, oauth_handler):
        """Test getting valid token with auto-refresh."""
        # Set token to expire soon
        oauth_handler.expires_at = int(time.time()) + 100  # Expires in 100 seconds
        
        with patch.object(oauth_handler, 'refresh_access_token') as mock_refresh:
            mock_refresh.return_value = {
                "accessToken": "refreshed-token",
                "refreshToken": "new-refresh",
                "expiresAt": int(time.time()) + 3600,
                "scopes": ["org:create_api_key", "user:profile", "user:inference"],
                "isMax": True
            }
            
            # Get token with auto-refresh
            token = await oauth_handler.get_valid_token(auto_refresh=True)
            
            assert token == "refreshed-token"
            mock_refresh.assert_called_once()


class TestClaudeTokenManager:
    """Test suite for ClaudeTokenManager."""
    
    @pytest.fixture
    def token_manager(self):
        """Create token manager instance for testing."""
        oauth_handler = MagicMock()
        return ClaudeTokenManager(
            oauth_handler=oauth_handler,
            auto_refresh=False  # Disable auto refresh for testing
        )
    
    @pytest.fixture
    def sample_token_info(self):
        """Create sample token info for testing."""
        return ClaudeTokenInfo(
            user_id="test-user",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_at=int(time.time()) + 3600,
            scopes=["org:create_api_key", "user:profile", "user:inference"],
            is_max=True
        )
    
    @pytest.mark.asyncio
    async def test_store_and_get_token(self, token_manager, sample_token_info):
        """Test storing and retrieving tokens."""
        user_id = sample_token_info.user_id
        
        # Store token
        await token_manager.store_token(user_id, sample_token_info)
        
        # Retrieve token
        token = await token_manager.get_token(user_id, auto_refresh=False)
        
        assert token == sample_token_info.access_token
        assert user_id in token_manager.active_tokens
        assert token_manager.active_tokens[user_id] == sample_token_info
    
    @pytest.mark.asyncio
    async def test_get_token_expired(self, token_manager, sample_token_info):
        """Test that expired tokens are not returned."""
        # Set token as expired
        sample_token_info.expires_at = int(time.time()) - 100
        user_id = sample_token_info.user_id
        
        await token_manager.store_token(user_id, sample_token_info)
        
        # Should return None for expired token
        token = await token_manager.get_token(user_id, auto_refresh=False)
        assert token is None
    
    @pytest.mark.asyncio
    async def test_refresh_token_with_retry(self, token_manager, sample_token_info):
        """Test token refresh with retry logic."""
        user_id = sample_token_info.user_id
        
        # Mock OAuth handler refresh to return new format
        token_manager.oauth_handler.refresh_access_token = AsyncMock(
            return_value={
                "accessToken": "new-access-token",
                "refreshToken": "new-refresh-token",
                "expiresAt": int(time.time()) + 3600,
                "scopes": ["org:create_api_key", "user:profile", "user:inference"],
                "isMax": True
            }
        )
        
        # Perform refresh
        success = await token_manager._refresh_token_with_retry(
            user_id, sample_token_info
        )
        
        assert success is True
        assert user_id in token_manager.active_tokens
        
        # Check new token info
        new_token_info = token_manager.active_tokens[user_id]
        assert new_token_info.access_token == "new-access-token"
        assert new_token_info.refresh_count == 1
        assert new_token_info.is_max == True
    
    @pytest.mark.asyncio
    async def test_validate_token(self, token_manager, sample_token_info):
        """Test token validation."""
        user_id = sample_token_info.user_id
        
        # Store token
        await token_manager.store_token(user_id, sample_token_info)
        
        # Validate correct token
        auth = await token_manager.validate_token(sample_token_info.access_token)
        assert auth is not None
        assert auth.user_id == user_id
        assert auth.user_role == "claude_oauth_user"
        assert "claude-3-opus" in auth.models  # Max user should have opus access
        
        # Validate incorrect token
        auth = await token_manager.validate_token("wrong-token")
        assert auth is None
    
    @pytest.mark.asyncio
    async def test_validate_token_non_max_user(self, token_manager):
        """Test token validation for non-Max user."""
        token_info = ClaudeTokenInfo(
            user_id="basic-user",
            access_token="basic-token",
            refresh_token=None,
            expires_at=int(time.time()) + 3600,
            scopes=["user:profile"],
            is_max=False  # Not a Max user
        )
        
        await token_manager.store_token("basic-user", token_info)
        
        auth = await token_manager.validate_token("basic-token")
        assert auth is not None
        assert "claude-3-sonnet" in auth.models
        assert "claude-3-opus" not in auth.models  # No opus for non-Max
    
    @pytest.mark.asyncio
    async def test_revoke_token(self, token_manager, sample_token_info):
        """Test token revocation."""
        user_id = sample_token_info.user_id
        
        # Store token
        await token_manager.store_token(user_id, sample_token_info)
        assert user_id in token_manager.active_tokens
        
        # Revoke token
        success = await token_manager.revoke_token(user_id)
        assert success is True
        assert user_id not in token_manager.active_tokens
        
        # Token should not be retrievable
        token = await token_manager.get_token(user_id)
        assert token is None
    
    @pytest.mark.asyncio
    async def test_get_token_stats(self, token_manager):
        """Test token statistics."""
        # Add some tokens with different states
        for i in range(3):
            token_info = ClaudeTokenInfo(
                user_id=f"user-{i}",
                access_token=f"token-{i}",
                refresh_token=f"refresh-{i}" if i > 0 else None,
                expires_at=int(time.time()) + (i - 1) * 3600,  # Varying expiry
                scopes=["org:create_api_key", "user:profile", "user:inference"],
                is_max=(i % 2 == 0),  # Alternate Max status
                refresh_count=i
            )
            await token_manager.store_token(f"user-{i}", token_info)
        
        stats = await token_manager.get_token_stats()
        
        assert stats["active_tokens"] == 3
        assert stats["expired"] == 1  # user-0 is expired
        assert stats["total_refreshes"] == 3  # 0 + 1 + 2
        assert stats["max_users"] == 2  # user-0 and user-2
        assert stats["auto_refresh_enabled"] is False
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens(self, token_manager):
        """Test cleanup of expired tokens."""
        # Add expired token without refresh capability
        expired_token = ClaudeTokenInfo(
            user_id="expired-user",
            access_token="expired-token",
            refresh_token=None,  # No refresh token
            expires_at=int(time.time()) - 100,
            scopes=["user:profile"],
            is_max=False
        )
        
        # Add valid token
        valid_token = ClaudeTokenInfo(
            user_id="valid-user",
            access_token="valid-token",
            refresh_token="refresh",
            expires_at=int(time.time()) + 3600,
            scopes=["org:create_api_key", "user:profile", "user:inference"],
            is_max=True
        )
        
        await token_manager.store_token("expired-user", expired_token)
        await token_manager.store_token("valid-user", valid_token)
        
        # Cleanup
        cleaned = await token_manager.cleanup_expired_tokens()
        
        assert cleaned == 1
        assert "expired-user" not in token_manager.active_tokens
        assert "valid-user" in token_manager.active_tokens


class TestClaudeOAuthBearer:
    """Test suite for Claude OAuth Bearer authentication."""
    
    def test_is_oauth_request_with_metadata(self):
        """Test OAuth request detection via metadata."""
        from litellm.llms.anthropic.oauth.bearer_auth import ClaudeOAuthBearer
        
        # Check with metadata flag
        assert ClaudeOAuthBearer.is_oauth_request(
            api_key=None,
            metadata={"using_claude_oauth": True}
        ) == True
        
        # Check with token in metadata
        assert ClaudeOAuthBearer.is_oauth_request(
            api_key=None,
            metadata={"claude_oauth_token": "test-token"}
        ) == True
    
    def test_is_oauth_request_with_bearer_token(self):
        """Test OAuth request detection via Bearer token."""
        from litellm.llms.anthropic.oauth.bearer_auth import ClaudeOAuthBearer
        
        # Bearer token (not API key)
        assert ClaudeOAuthBearer.is_oauth_request(
            api_key="Bearer oauth-token-123",
            metadata=None
        ) == True
        
        # Regular API key
        assert ClaudeOAuthBearer.is_oauth_request(
            api_key="sk-ant-api-key-123",
            metadata=None
        ) == False
    
    def test_prepare_oauth_headers(self):
        """Test OAuth header preparation."""
        from litellm.llms.anthropic.oauth.bearer_auth import ClaudeOAuthBearer
        
        headers = {}
        metadata = {"claude_oauth_token": "test-oauth-token"}
        
        headers = ClaudeOAuthBearer.prepare_oauth_headers(
            headers, None, metadata
        )
        
        assert headers["Authorization"] == "Bearer test-oauth-token"
        assert headers["anthropic-beta"] == "oauth-2025-04-20"
        assert "x-api-key" not in headers
    
    def test_should_refresh_token(self):
        """Test token refresh detection."""
        from litellm.llms.anthropic.oauth.bearer_auth import ClaudeOAuthBearer
        
        # 401 error should trigger refresh
        assert ClaudeOAuthBearer.should_refresh_token({
            "status_code": 401,
            "error": {"message": "Unauthorized"}
        }) == True
        
        # Token expired error
        assert ClaudeOAuthBearer.should_refresh_token({
            "error": {"type": "token_expired"}
        }) == True
        
        # Other errors should not trigger refresh
        assert ClaudeOAuthBearer.should_refresh_token({
            "status_code": 500,
            "error": {"message": "Server error"}
        }) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])