#!/usr/bin/env python3
"""
Simple test runner for Claude OAuth tests without pytest
"""

import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta, timezone

# Add the project root to path
sys.path.insert(0, '/home/tom130/_PROJECTS/git/litellm')

from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler
from litellm.proxy.auth.claude_token_manager import ClaudeTokenInfo, ClaudeTokenManager
from cryptography.fernet import Fernet

def test_pkce_generation():
    """Test PKCE code generation"""
    print("Testing PKCE generation...")
    handler = ClaudeOAuthHandler(
        client_id="test-client",
        redirect_uri="http://localhost:4000/callback",
        encryption_key=Fernet.generate_key()
    )
    
    verifier, challenge = handler.generate_pkce_pair()
    
    assert len(verifier) >= 43, f"Verifier too short: {len(verifier)}"
    assert len(challenge) >= 43, f"Challenge too short: {len(challenge)}"
    
    # Test uniqueness
    verifier2, challenge2 = handler.generate_pkce_pair()
    assert verifier != verifier2, "PKCE pairs should be unique"
    
    print("✓ PKCE generation test passed")

def test_state_generation():
    """Test OAuth state generation and verification"""
    print("Testing state generation...")
    handler = ClaudeOAuthHandler(
        client_id="test-client",
        redirect_uri="http://localhost:4000/callback",
        encryption_key=Fernet.generate_key()
    )
    
    user_id = "test-user-123"
    state = handler.generate_state(user_id)
    
    assert len(state) > 0, "State should not be empty"
    
    # Verify state
    state_data = handler.verify_state(state)
    assert state_data["user_id"] == user_id, "User ID mismatch"
    assert "nonce" in state_data, "Missing nonce"
    assert "timestamp" in state_data, "Missing timestamp"
    
    print("✓ State generation test passed")

def test_authorization_url():
    """Test authorization URL generation"""
    print("Testing authorization URL...")
    handler = ClaudeOAuthHandler(
        client_id="test-client",
        redirect_uri="http://localhost:4000/callback"
    )
    
    auth_url, state, verifier = handler.get_authorization_url(
        user_id="test-user",
        scopes=["claude:chat", "claude:models"]
    )
    
    assert "https://claude.ai/oauth/authorize" in auth_url
    assert "client_id=test-client" in auth_url
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url
    
    print("✓ Authorization URL test passed")

def test_token_encryption():
    """Test token encryption/decryption"""
    print("Testing token encryption...")
    handler = ClaudeOAuthHandler(
        encryption_key=Fernet.generate_key()
    )
    
    original = "test-token-12345"
    encrypted = handler.encrypt_token(original)
    decrypted = handler.decrypt_token(encrypted)
    
    assert encrypted != original, "Token should be encrypted"
    assert decrypted == original, "Decryption failed"
    
    print("✓ Token encryption test passed")

async def test_token_manager():
    """Test token manager basic operations"""
    print("Testing token manager...")
    
    oauth_handler = MagicMock()
    manager = ClaudeTokenManager(
        oauth_handler=oauth_handler,
        auto_refresh=False
    )
    
    # Create test token
    token_info = ClaudeTokenInfo(
        user_id="test-user",
        access_token="test-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["claude:chat"],
        created_at=datetime.now(timezone.utc)
    )
    
    # Store and retrieve
    await manager.store_token("test-user", token_info)
    retrieved = await manager.get_token("test-user", auto_refresh=False)
    
    assert retrieved == "test-token", "Token retrieval failed"
    
    # Test revocation
    await manager.revoke_token("test-user")
    retrieved = await manager.get_token("test-user", auto_refresh=False)
    assert retrieved is None, "Token should be revoked"
    
    print("✓ Token manager test passed")

async def test_token_validation():
    """Test token validation"""
    print("Testing token validation...")
    
    oauth_handler = MagicMock()
    manager = ClaudeTokenManager(
        oauth_handler=oauth_handler,
        auto_refresh=False
    )
    
    # Create and store token
    token_info = ClaudeTokenInfo(
        user_id="test-user",
        access_token="valid-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["claude:chat"],
        created_at=datetime.now(timezone.utc)
    )
    
    await manager.store_token("test-user", token_info)
    
    # Validate correct token
    auth = await manager.validate_token("valid-token")
    assert auth is not None, "Valid token should authenticate"
    assert auth.user_id == "test-user", "User ID mismatch"
    
    # Validate wrong token
    auth = await manager.validate_token("invalid-token")
    assert auth is None, "Invalid token should not authenticate"
    
    print("✓ Token validation test passed")

async def run_async_tests():
    """Run all async tests"""
    await test_token_manager()
    await test_token_validation()

def main():
    """Run all tests"""
    print("\n" + "="*50)
    print("Running Claude OAuth Tests")
    print("="*50 + "\n")
    
    try:
        # Run sync tests
        test_pkce_generation()
        test_state_generation()
        test_authorization_url()
        test_token_encryption()
        
        # Run async tests
        asyncio.run(run_async_tests())
        
        print("\n" + "="*50)
        print("✅ All tests passed!")
        print("="*50 + "\n")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())