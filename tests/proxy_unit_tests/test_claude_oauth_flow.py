"""
Tests for Claude OAuth Flow Implementation
"""

import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import pytest
import httpx

from litellm.proxy.auth.claude_oauth_flow import ClaudeOAuthFlow, OAuthState


class TestClaudeOAuthFlow:
    """Test suite for ClaudeOAuthFlow class."""
    
    @pytest.fixture
    def oauth_flow(self, tmp_path):
        """Create an OAuth flow instance with temporary state directory."""
        return ClaudeOAuthFlow(state_dir=str(tmp_path))
    
    def test_generate_pkce_pair(self, oauth_flow):
        """Test PKCE pair generation."""
        verifier, challenge = oauth_flow.generate_pkce_pair()
        
        # Verify format
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert len(verifier) > 40  # Base64 encoded 32 bytes
        assert len(challenge) > 40  # Base64 encoded SHA256
        
        # Verify challenge is correct SHA256 of verifier
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode('utf-8').rstrip('=')
        assert challenge == expected_challenge
    
    def test_generate_state(self, oauth_flow):
        """Test state generation for CSRF protection."""
        state1 = oauth_flow.generate_state()
        state2 = oauth_flow.generate_state()
        
        # States should be unique
        assert state1 != state2
        
        # States should be 64 characters (32 bytes hex)
        assert len(state1) == 64
        assert len(state2) == 64
        
        # Should be valid hex
        int(state1, 16)
        int(state2, 16)
    
    def test_build_authorization_url(self, oauth_flow):
        """Test authorization URL construction."""
        state = "test_state_123"
        challenge = "test_challenge_456"
        
        url = oauth_flow.build_authorization_url(state, challenge)
        
        # Check base URL
        assert url.startswith("https://claude.ai/oauth/authorize?")
        
        # Check required parameters
        assert f"state={state}" in url
        assert f"code_challenge={challenge}" in url
        assert "code_challenge_method=S256" in url
        assert f"client_id={oauth_flow.CLIENT_ID}" in url
        assert f"redirect_uri={oauth_flow.REDIRECT_URI}" in url
        assert "response_type=code" in url
        assert "code=true" in url  # Claude-specific parameter
        
        # Check scopes
        for scope in oauth_flow.SCOPES:
            assert scope.replace(":", "%3A") in url
    
    @pytest.mark.asyncio
    async def test_save_and_load_state(self, oauth_flow):
        """Test saving and loading OAuth state."""
        state = "test_state_789"
        verifier = "test_verifier_abc"
        
        # Save state
        state_file = await oauth_flow.save_state(state, verifier)
        assert Path(state_file).exists()
        
        # Load state
        loaded_state = await oauth_flow.load_state(state)
        assert loaded_state is not None
        assert loaded_state.state == state
        assert loaded_state.code_verifier == verifier
        assert loaded_state.timestamp > 0
        assert loaded_state.expires_at > loaded_state.timestamp
    
    @pytest.mark.asyncio
    async def test_expired_state_cleanup(self, oauth_flow):
        """Test that expired states are cleaned up."""
        state = "expired_state"
        verifier = "test_verifier"
        
        # Save state with past expiration
        state_data = {
            "state": state,
            "code_verifier": verifier,
            "timestamp": int(time.time()) - 1000,
            "expires_at": int(time.time()) - 500  # Expired
        }
        
        state_file = oauth_flow.state_dir / f"{oauth_flow.STATE_FILE_PREFIX}_{state}.json"
        state_file.write_text(json.dumps(state_data))
        
        # Try to load expired state
        loaded_state = await oauth_flow.load_state(state)
        assert loaded_state is None
        assert not state_file.exists()  # Should be deleted
    
    @pytest.mark.asyncio
    async def test_exchange_code_success(self, oauth_flow):
        """Test successful authorization code exchange."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Mock successful response
            mock_response = AsyncMock()
            mock_response.is_success = True
            mock_response.json.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scope": "org:create_api_key user:profile user:inference"
            }
            mock_client.post.return_value = mock_response
            
            # Save state first
            state = "test_state"
            verifier = "test_verifier"
            await oauth_flow.save_state(state, verifier)
            
            # Exchange code
            result = await oauth_flow.exchange_code("test_code", state)
            
            assert result["accessToken"] == "test_access_token"
            assert result["refreshToken"] == "test_refresh_token"
            assert result["expiresAt"] > int(time.time())
            assert "org:create_api_key" in result["scopes"]
            assert result["isMax"] is True
    
    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state(self, oauth_flow):
        """Test code exchange with invalid state."""
        with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
            await oauth_flow.exchange_code("test_code", "nonexistent_state")
    
    @pytest.mark.asyncio
    async def test_exchange_code_http_error(self, oauth_flow):
        """Test code exchange with HTTP error."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Mock error response
            mock_response = AsyncMock()
            mock_response.is_success = False
            mock_response.status_code = 400
            mock_response.text = "Invalid authorization code"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=Mock(),
                response=Mock(status_code=400)
            )
            mock_client.post.return_value = mock_response
            
            # Save state first
            state = "test_state"
            verifier = "test_verifier"
            await oauth_flow.save_state(state, verifier)
            
            # Exchange should fail
            with pytest.raises(httpx.HTTPStatusError):
                await oauth_flow.exchange_code("invalid_code", state)
    
    @pytest.mark.asyncio
    async def test_start_flow(self, oauth_flow):
        """Test starting the OAuth flow."""
        auth_url, state = await oauth_flow.start_flow()
        
        # Verify URL format
        assert auth_url.startswith("https://claude.ai/oauth/authorize?")
        assert f"state={state}" in auth_url
        
        # Verify state was saved
        loaded_state = await oauth_flow.load_state(state)
        assert loaded_state is not None
        assert loaded_state.state == state
    
    @pytest.mark.asyncio
    async def test_complete_flow(self, oauth_flow):
        """Test completing the OAuth flow."""
        with patch.object(oauth_flow, 'exchange_code') as mock_exchange:
            mock_exchange.return_value = {
                "accessToken": "token",
                "refreshToken": "refresh",
                "expiresAt": int(time.time()) + 3600
            }
            
            result = await oauth_flow.complete_flow("code", "state")
            
            assert result["accessToken"] == "token"
            mock_exchange.assert_called_once_with("code", "state")
    
    def test_cleanup_expired_states(self, oauth_flow):
        """Test cleanup of expired state files."""
        # Create expired and valid state files
        current_time = int(time.time())
        
        # Expired state
        expired_state = {
            "state": "expired",
            "code_verifier": "verifier",
            "timestamp": current_time - 1000,
            "expires_at": current_time - 500
        }
        expired_file = oauth_flow.state_dir / f"{oauth_flow.STATE_FILE_PREFIX}_expired.json"
        expired_file.write_text(json.dumps(expired_state))
        
        # Valid state
        valid_state = {
            "state": "valid",
            "code_verifier": "verifier",
            "timestamp": current_time,
            "expires_at": current_time + 500
        }
        valid_file = oauth_flow.state_dir / f"{oauth_flow.STATE_FILE_PREFIX}_valid.json"
        valid_file.write_text(json.dumps(valid_state))
        
        # Run cleanup
        cleaned = oauth_flow.cleanup_expired_states()
        
        assert cleaned == 1
        assert not expired_file.exists()
        assert valid_file.exists()
    
    def test_get_manual_instructions(self, oauth_flow):
        """Test generation of manual instructions."""
        auth_url = "https://claude.ai/oauth/authorize?test=1"
        instructions = oauth_flow.get_manual_instructions(auth_url)
        
        assert auth_url in instructions
        assert "Claude OAuth Authentication Required" in instructions
        assert "CODE" in instructions
        assert "callback" in instructions