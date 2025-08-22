# Source Generated with Decompyle++
# File: token_manager.cpython-312.pyc (Python 3.12)

__doc__ = '\nToken management with automatic refresh and secure storage.\n'
import json
import logging
import os
import time
from pathlib import Path
from threading import Lock
from typing import Dict, Optional, Any
from oauth import ClaudeOAuth, OAuthConfig
logger = logging.getLogger(__name__)

class TokenManager:
    '''Manages OAuth tokens with automatic refresh and persistence'''
    
    def __init__(self = None, oauth_client = None, token_file = None, auto_refresh = (None, None, True, 300), refresh_buffer = ('oauth_client', Optional[ClaudeOAuth], 'token_file', Optional[str], 'auto_refresh', bool, 'refresh_buffer', int)):
        '''
        Initialize token manager.
        
        Args:
            oauth_client: OAuth client instance
            token_file: Path to token storage file
            auto_refresh: Enable automatic token refresh
            refresh_buffer: Seconds before expiry to trigger refresh
        '''
        pass
    # WARNING: Decompyle incomplete

    
    def load_tokens(self = None):
        '''Load tokens from storage file'''
        if not self.token_file.exists():
            logger.debug('No existing token file found')
            return None
    # WARNING: Decompyle incomplete

    
    def save_tokens(self = None, tokens = None):
        '''Save tokens to storage file with secure permissions'''
        pass
    # WARNING: Decompyle incomplete

    
    def get_access_token(self = None):
        '''
        Get valid access token, refreshing if necessary.
        
        Returns:
            Valid access token
            
        Raises:
            Exception: If unable to obtain valid token
        '''
        pass
    # WARNING: Decompyle incomplete

    
    def _should_refresh(self = None):
        '''Check if token should be refreshed'''
        if not self._tokens:
            return True
        expires_at = self._tokens.get('expires_at', 0)
        current_time = time.time()
        return current_time >= expires_at - self.refresh_buffer

    
    def _refresh_token(self = None):
        '''
        Refresh the access token.
        
        Returns:
            New access token
            
        Raises:
            Exception: If refresh fails
        '''
        if self._tokens or 'refresh_token' not in self._tokens:
            logger.warning('No refresh token available, re-authenticating')
            tokens = self.oauth_client.authenticate()
            self.save_tokens(tokens)
            return tokens['access_token']
        new_tokens = self.oauth_client.refresh_token(self._tokens['refresh_token'])
        if 'refresh_token' not in new_tokens and 'refresh_token' in self._tokens:
            new_tokens['refresh_token'] = self._tokens['refresh_token']
        self.save_tokens(new_tokens)
        return new_tokens['access_token']
    # WARNING: Decompyle incomplete

    
    def revoke_tokens(self = None):
        '''Revoke tokens and clear storage'''
        pass
    # WARNING: Decompyle incomplete

    
    def get_token_info(self = None):
        '''Get information about current tokens'''
        if not self._tokens:
            return None
        expires_at = self._tokens.get('expires_at', 0)
        current_time = time.time()
        if self.auto_refresh:
            return {
                'has_access_token': 'access_token' in self._tokens,
                'has_refresh_token': 'refresh_token' in self._tokens,
                'expires_at': expires_at,
                'expires_in': max(0, expires_at - current_time),
                'is_expired': current_time >= expires_at,
                'needs_refresh': self._should_refresh() }
        return {
            'has_access_token': None,
            'has_refresh_token': 'access_token' in self._tokens,
            'expires_at': 'refresh_token' in self._tokens,
            'expires_in': expires_at,
            'is_expired': max(0, expires_at - current_time),
            'needs_refresh': current_time >= expires_at }

    
    def validate_token(self = None):
        '''
        Validate current access token.
        
        Returns:
            True if token is valid
        '''
        if self._tokens or 'access_token' not in self._tokens:
            return False
        return self.oauth_client.validate_token(self._tokens['access_token'])


# WARNING: Decompyle incomplete
