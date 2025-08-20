"""
Tests for Claude OAuth Implementation

Tests PKCE flow, token management, and OAuth endpoints.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler
from litellm.proxy.auth.claude_token_manager import ClaudeTokenInfo, ClaudeTokenManager


class TestClaudeOAuthHandler:
    """Test suite for ClaudeOAuthHandler."""
    
    @pytest.fixture
    def oauth_handler(self):
        """Create OAuth handler instance for testing."""
        return ClaudeOAuthHandler(
            client_id="test-client-id",
            redirect_uri="http://localhost:4000/auth/claude/callback",
            encryption_key=Fernet.generate_key()
        )
    
    def test_generate_pkce_pair(self, oauth_handler):
        """Test PKCE code verifier and challenge generation."""
        verifier, challenge = oauth_handler.generate_pkce_pair()
        
        # Verify lengths
        assert len(verifier) >= 43
        assert len(verifier) <= 128
        assert len(challenge) >= 43
        assert len(challenge) <= 128
        
        # Verify challenge is SHA256 of verifier
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip('=')
        assert challenge == expected_challenge
        
        # Generate multiple pairs and ensure uniqueness
        pairs = [oauth_handler.generate_pkce_pair() for _ in range(10)]
        verifiers = [v for v, _ in pairs]
        assert len(set(verifiers)) == 10  # All unique
    
    def test_generate_state(self, oauth_handler):
        """Test state parameter generation."""
        user_id = "test-user-123"
        state = oauth_handler.generate_state(user_id)
        
        # State should be a non-empty string
        assert isinstance(state, str)
        assert len(state) > 0
        
        # Should be able to decrypt and verify
        state_data = oauth_handler.verify_state(state)
        assert state_data["user_id"] == user_id
        assert "nonce" in state_data
        assert "timestamp" in state_data
    
    def test_verify_state_expired(self, oauth_handler):
        """Test that expired state is rejected."""
        # Generate state with old timestamp
        state_data = {
            "nonce": secrets.token_urlsafe(32),
            "timestamp": int(time.time()) - 700,  # 11 minutes ago
            "user_id": "test-user"
        }
        state_json = json.dumps(state_data)
        encrypted_state = oauth_handler.cipher_suite.encrypt(state_json.encode())
        state = base64.urlsafe_b64encode(encrypted_state).decode().rstrip('=')
        
        # Should raise exception for expired state
        with pytest.raises(Exception) as exc_info:
            oauth_handler.verify_state(state)
        assert "expired" in str(exc_info.value).lower()
    
    def test_verify_state_invalid(self, oauth_handler):
        """Test that invalid state is rejected."""
        invalid_state = "invalid-state-string"
        
        with pytest.raises(Exception) as exc_info:
            oauth_handler.verify_state(invalid_state)
        assert "invalid" in str(exc_info.value).lower()
    
    def test_get_authorization_url(self, oauth_handler):
        """Test authorization URL generation."""
        user_id = "test-user-123"
        scopes = ["claude:chat", "claude:models"]
        
        auth_url, state, code_verifier = oauth_handler.get_authorization_url(
            user_id=user_id,
            scopes=scopes
        )
        
        # Check URL structure
        assert auth_url.startswith(oauth_handler.AUTHORIZE_URL)
        assert "client_id=test-client-id" in auth_url
        assert "response_type=code" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url
        assert "state=" in auth_url
        assert "scope=claude%3Achat+claude%3Amodels" in auth_url
        
        # Verify state can be decrypted
        state_data = oauth_handler.verify_state(state)
        assert state_data["user_id"] == user_id
        
        # Verify PKCE verifier is stored
        assert state in oauth_handler.pkce_storage
        assert oauth_handler.pkce_storage[state]["code_verifier"] == code_verifier
    
    def test_get_authorization_url_no_client_id(self):
        """Test that authorization URL generation fails without client ID."""
        handler = ClaudeOAuthHandler()
        
        with pytest.raises(Exception) as exc_info:
            handler.get_authorization_url()
        assert "client ID not configured" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token(self, oauth_handler):
        """Test authorization code exchange for tokens."""
        # Setup
        user_id = "test-user-123"
        auth_url, state, code_verifier = oauth_handler.get_authorization_url(user_id=user_id)
        code = "test-auth-code"
        
        # Mock HTTP client
        with patch('litellm.llms.custom_httpx.http_handler.get_async_httpx_client') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "expires_in": 3600,
                "scope": "claude:chat claude:models"
            }
            mock_response.raise_for_status = MagicMock()
            
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http
            
            # Exchange code
            token_response = await oauth_handler.exchange_code_for_token(code, state)
            
            # Verify response
            assert token_response["access_token"] == "test-access-token"
            assert token_response["refresh_token"] == "test-refresh-token"
            assert token_response["user_id"] == user_id
            
            # Verify HTTP call
            mock_http.post.assert_called_once()
            call_args = mock_http.post.call_args
            assert call_args[0][0] == oauth_handler.TOKEN_URL
            assert call_args[1]["data"]["code"] == code
            assert call_args[1]["data"]["code_verifier"] == code_verifier
    
    @pytest.mark.asyncio
    async def test_refresh_access_token(self, oauth_handler):
        """Test token refresh."""
        refresh_token = "test-refresh-token"
        
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
            new_token = await oauth_handler.refresh_access_token(refresh_token)
            
            # Verify response
            assert new_token["access_token"] == "new-access-token"
            assert new_token["refresh_token"] == "new-refresh-token"
            
            # Verify HTTP call
            mock_http.post.assert_called_once()
            call_args = mock_http.post.call_args
            assert call_args[1]["data"]["grant_type"] == "refresh_token"
            assert call_args[1]["data"]["refresh_token"] == refresh_token
    
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
        
        # Ensure different encryptions produce different ciphertexts
        encrypted2 = oauth_handler.encrypt_token(original_token)
        assert encrypted != encrypted2  # Different due to IV/nonce


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
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["claude:chat"],
            created_at=datetime.now(timezone.utc)
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
        sample_token_info.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        user_id = sample_token_info.user_id
        
        await token_manager.store_token(user_id, sample_token_info)
        
        # Should return None for expired token
        token = await token_manager.get_token(user_id, auto_refresh=False)
        assert token is None
    
    @pytest.mark.asyncio
    async def test_refresh_token_with_retry(self, token_manager, sample_token_info):
        """Test token refresh with retry logic."""
        user_id = sample_token_info.user_id
        
        # Mock OAuth handler refresh
        token_manager.oauth_handler.refresh_access_token = AsyncMock(
            return_value={
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600
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
    
    @pytest.mark.asyncio
    async def test_refresh_token_with_retry_failure(self, token_manager, sample_token_info):
        """Test token refresh failure after retries."""
        user_id = sample_token_info.user_id
        
        # Mock OAuth handler to always fail
        token_manager.oauth_handler.refresh_access_token = AsyncMock(
            side_effect=Exception("Refresh failed")
        )
        
        # Store initial token
        await token_manager.store_token(user_id, sample_token_info)
        
        # Perform refresh (should fail)
        success = await token_manager._refresh_token_with_retry(
            user_id, sample_token_info, max_retries=2
        )
        
        assert success is False
        # Token should be revoked after failure
        assert user_id not in token_manager.active_tokens
    
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
        
        # Validate incorrect token
        auth = await token_manager.validate_token("wrong-token")
        assert auth is None
    
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
        # Add some tokens
        for i in range(3):
            token_info = ClaudeTokenInfo(
                user_id=f"user-{i}",
                access_token=f"token-{i}",
                refresh_token=f"refresh-{i}",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=i - 1),
                scopes=["claude:chat"],
                created_at=datetime.now(timezone.utc),
                refresh_count=i
            )
            await token_manager.store_token(f"user-{i}", token_info)
        
        stats = await token_manager.get_token_stats()
        
        assert stats["active_tokens"] == 3
        assert stats["expired"] == 1  # user-0 is expired
        assert stats["total_refreshes"] == 3  # 0 + 1 + 2
        assert stats["auto_refresh_enabled"] is False
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens(self, token_manager):
        """Test cleanup of expired tokens."""
        # Add expired and valid tokens
        expired_token = ClaudeTokenInfo(
            user_id="expired-user",
            access_token="expired-token",
            refresh_token=None,  # No refresh token
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scopes=["claude:chat"],
            created_at=datetime.now(timezone.utc)
        )
        
        valid_token = ClaudeTokenInfo(
            user_id="valid-user",
            access_token="valid-token",
            refresh_token="refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["claude:chat"],
            created_at=datetime.now(timezone.utc)
        )
        
        await token_manager.store_token("expired-user", expired_token)
        await token_manager.store_token("valid-user", valid_token)
        
        # Cleanup
        cleaned = await token_manager.cleanup_expired_tokens()
        
        assert cleaned == 1
        assert "expired-user" not in token_manager.active_tokens
        assert "valid-user" in token_manager.active_tokens


if __name__ == "__main__":
    pytest.main([__file__, "-v"])