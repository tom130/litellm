"""
Tests for Claude Authentication Service
"""

import asyncio
import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import pytest

from litellm.proxy.auth.claude_auth_service import (
    ClaudeAuthService,
    get_auth_service,
    quick_authenticate
)
from litellm.proxy.auth.claude_token_manager import ClaudeTokenInfo


class TestClaudeAuthService:
    """Test suite for ClaudeAuthService."""
    
    @pytest.fixture
    def auth_service(self, tmp_path):
        """Create an auth service instance with temporary storage."""
        token_file = tmp_path / "tokens.json"
        return ClaudeAuthService(token_file=token_file)
    
    @pytest.fixture
    def sample_tokens(self):
        """Sample token data for testing."""
        return {
            "accessToken": "test_access_token",
            "refreshToken": "test_refresh_token",
            "expiresAt": int(time.time()) + 3600,
            "scopes": ["org:create_api_key", "user:profile", "user:inference"],
            "isMax": True
        }
    
    def test_init(self, tmp_path):
        """Test service initialization."""
        token_file = tmp_path / "test_tokens.json"
        service = ClaudeAuthService(token_file=token_file)
        
        assert service.token_file == token_file
        assert service.oauth_flow is not None
        assert service.token_manager is not None
        assert service.oauth_handler is not None
    
    def test_load_tokens_from_file(self, auth_service, sample_tokens):
        """Test loading tokens from file."""
        # Save tokens to file
        auth_service.token_file.write_text(json.dumps(sample_tokens))
        
        # Load tokens
        result = auth_service._load_tokens()
        
        assert result is True
        assert auth_service.oauth_handler.access_token == sample_tokens["accessToken"]
        assert auth_service.oauth_handler.refresh_token == sample_tokens["refreshToken"]
        assert auth_service.oauth_handler.expires_at == sample_tokens["expiresAt"]
    
    def test_load_tokens_from_env(self, auth_service, monkeypatch):
        """Test loading tokens from environment variables."""
        monkeypatch.setenv("CLAUDE_ACCESS_TOKEN", "env_access_token")
        monkeypatch.setenv("CLAUDE_REFRESH_TOKEN", "env_refresh_token")
        monkeypatch.setenv("CLAUDE_EXPIRES_AT", "1234567890")
        
        result = auth_service._load_tokens()
        
        assert result is True
        assert auth_service.oauth_handler.access_token == "env_access_token"
        assert auth_service.oauth_handler.refresh_token == "env_refresh_token"
        assert auth_service.oauth_handler.expires_at == 1234567890
    
    def test_save_tokens(self, auth_service, sample_tokens):
        """Test saving tokens to file."""
        auth_service._save_tokens(sample_tokens)
        
        assert auth_service.token_file.exists()
        
        # Verify file contents
        saved_data = json.loads(auth_service.token_file.read_text())
        assert saved_data == sample_tokens
        
        # Verify handler was updated
        assert auth_service.oauth_handler.access_token == sample_tokens["accessToken"]
        assert auth_service.oauth_handler.refresh_token == sample_tokens["refreshToken"]
    
    @pytest.mark.asyncio
    async def test_get_access_token_valid(self, auth_service, sample_tokens):
        """Test getting access token when valid token exists."""
        # Setup valid tokens
        auth_service._save_tokens(sample_tokens)
        
        with patch.object(auth_service.oauth_handler, 'get_valid_token') as mock_get:
            mock_get.return_value = sample_tokens["accessToken"]
            
            token = await auth_service.get_access_token()
            
            assert token == sample_tokens["accessToken"]
            mock_get.assert_called_once_with(
                user_id=None,
                auto_refresh=True,
                auto_oauth=False
            )
    
    @pytest.mark.asyncio
    async def test_get_access_token_refresh(self, auth_service, sample_tokens):
        """Test automatic token refresh."""
        # Setup expired tokens
        expired_tokens = sample_tokens.copy()
        expired_tokens["expiresAt"] = int(time.time()) - 100
        auth_service._save_tokens(expired_tokens)
        
        # Setup refresh token
        auth_service.oauth_handler.refresh_token = expired_tokens["refreshToken"]
        
        with patch.object(auth_service.oauth_handler, 'get_valid_token') as mock_get:
            mock_get.return_value = None  # Token expired
            
            with patch.object(auth_service.oauth_handler, 'refresh_access_token') as mock_refresh:
                new_tokens = sample_tokens.copy()
                new_tokens["accessToken"] = "new_access_token"
                mock_refresh.return_value = new_tokens
                
                token = await auth_service.get_access_token()
                
                assert token == "new_access_token"
                mock_refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_access_token_no_tokens(self, auth_service):
        """Test behavior when no tokens exist."""
        with patch.object(auth_service.oauth_handler, 'get_valid_token') as mock_get:
            mock_get.return_value = None
            
            token = await auth_service.get_access_token(require_oauth=False)
            
            assert token is None
    
    @pytest.mark.asyncio
    async def test_start_oauth_flow(self, auth_service):
        """Test starting OAuth flow."""
        with patch.object(auth_service.oauth_flow, 'start_flow') as mock_start:
            mock_start.return_value = ("https://auth.url", "state123")
            
            with patch.object(auth_service.oauth_flow, 'get_manual_instructions') as mock_instr:
                mock_instr.return_value = "Instructions"
                
                result = await auth_service.start_oauth_flow()
                
                assert result["authorization_url"] == "https://auth.url"
                assert result["state"] == "state123"
                assert result["instructions"] == "Instructions"
    
    @pytest.mark.asyncio
    async def test_complete_oauth_flow(self, auth_service, sample_tokens):
        """Test completing OAuth flow."""
        with patch.object(auth_service.oauth_flow, 'complete_flow') as mock_complete:
            mock_complete.return_value = sample_tokens
            
            result = await auth_service.complete_oauth_flow("code123", "state123")
            
            assert result == sample_tokens
            assert auth_service.token_file.exists()
            
            # Verify tokens were saved
            saved_data = json.loads(auth_service.token_file.read_text())
            assert saved_data == sample_tokens
    
    @pytest.mark.asyncio
    async def test_refresh_tokens(self, auth_service, sample_tokens):
        """Test manual token refresh."""
        auth_service.oauth_handler.refresh_token = "refresh_token"
        
        with patch.object(auth_service.oauth_handler, 'refresh_access_token') as mock_refresh:
            new_tokens = sample_tokens.copy()
            new_tokens["accessToken"] = "refreshed_token"
            mock_refresh.return_value = new_tokens
            
            result = await auth_service.refresh_tokens()
            
            assert result == new_tokens
            assert auth_service.token_file.exists()
    
    def test_get_token_info(self, auth_service, sample_tokens):
        """Test getting token information."""
        auth_service._save_tokens(sample_tokens)
        
        with patch.object(auth_service.token_manager, 'get_token_info') as mock_info:
            mock_info.return_value = ClaudeTokenInfo(
                has_access_token=True,
                has_refresh_token=True,
                expires_at=sample_tokens["expiresAt"],
                expires_in=3600,
                is_expired=False,
                needs_refresh=False
            )
            
            info = auth_service.get_token_info()
            
            assert info.has_access_token is True
            assert info.has_refresh_token is True
            assert info.is_expired is False
    
    def test_clear_tokens(self, auth_service, sample_tokens):
        """Test clearing all tokens."""
        # Save tokens first
        auth_service._save_tokens(sample_tokens)
        assert auth_service.token_file.exists()
        
        # Clear tokens
        auth_service.clear_tokens()
        
        assert not auth_service.token_file.exists()
        assert auth_service.oauth_handler.access_token is None
        assert auth_service.oauth_handler.refresh_token is None
        assert auth_service.oauth_handler.expires_at is None
    
    @pytest.mark.asyncio
    async def test_ensure_authenticated_success(self, auth_service, sample_tokens):
        """Test ensure_authenticated with valid tokens."""
        with patch.object(auth_service, 'get_access_token') as mock_get:
            mock_get.return_value = sample_tokens["accessToken"]
            
            result = await auth_service.ensure_authenticated()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_ensure_authenticated_failure(self, auth_service):
        """Test ensure_authenticated without valid tokens."""
        with patch.object(auth_service, 'get_access_token') as mock_get:
            mock_get.return_value = None
            
            result = await auth_service.ensure_authenticated()
            
            assert result is False
    
    def test_get_headers(self, auth_service, sample_tokens):
        """Test getting authentication headers."""
        auth_service._save_tokens(sample_tokens)
        
        with patch.object(auth_service.oauth_handler, 'get_auth_headers') as mock_headers:
            mock_headers.return_value = {
                "Authorization": f"Bearer {sample_tokens['accessToken']}",
                "anthropic-beta": "oauth-2025-04-20"
            }
            
            headers = auth_service.get_headers()
            
            assert "Authorization" in headers
            assert "anthropic-beta" in headers
    
    def test_get_headers_no_token(self, auth_service):
        """Test getting headers without token raises error."""
        auth_service.oauth_handler.access_token = None
        
        with pytest.raises(ValueError, match="No access token available"):
            auth_service.get_headers()


class TestAuthServiceHelpers:
    """Test helper functions for auth service."""
    
    def test_get_auth_service_singleton(self, tmp_path):
        """Test that get_auth_service returns singleton."""
        token_file = tmp_path / "tokens.json"
        
        service1 = get_auth_service(token_file=token_file)
        service2 = get_auth_service(token_file=token_file)
        
        assert service1 is service2
    
    @pytest.mark.asyncio
    async def test_quick_authenticate(self, tmp_path):
        """Test quick_authenticate helper."""
        token_file = tmp_path / "tokens.json"
        
        with patch('litellm.proxy.auth.claude_auth_service.get_auth_service') as mock_get:
            mock_service = AsyncMock()
            mock_service.get_access_token.return_value = "quick_token"
            mock_get.return_value = mock_service
            
            token = await quick_authenticate()
            
            assert token == "quick_token"
            mock_service.get_access_token.assert_called_once_with(
                auto_refresh=True,
                require_oauth=False
            )