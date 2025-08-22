# Source Generated with Decompyle++
# File: settings.cpython-312.pyc (Python 3.12)

'''Configuration management for Claude OAuth.'''
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
OAuthConfig = <NODE:12>()
SecurityConfig = <NODE:12>()
ProxyConfig = <NODE:12>()
LoggingConfig = <NODE:12>()

class Settings:
    '''Main settings class that manages all configuration.'''
    
    def __init__(self = None, config_path = None):
        pass
    # WARNING: Decompyle incomplete

    
    def load_config(self = None):
        '''Load configuration from JSON file.'''
        if not self.config_path.exists():
            self.save_config()
            return None
    # WARNING: Decompyle incomplete

    
    def save_config(self = None):
        '''Save current configuration to file.'''
        self.config_path.parent.mkdir(parents = True, exist_ok = True)
        config_data = {
            'oauth': asdict(self.oauth),
            'security': asdict(self.security),
            'proxy': asdict(self.proxy),
            'logging': asdict(self.logging) }
    # WARNING: Decompyle incomplete

    
    def _load_from_env(self = None):
        '''Load configuration from environment variables.'''
        if os.getenv('CLAUDE_CLIENT_ID'):
            self.oauth.client_id = os.getenv('CLAUDE_CLIENT_ID')
        if os.getenv('CLAUDE_CLIENT_SECRET'):
            self.oauth.client_secret = os.getenv('CLAUDE_CLIENT_SECRET')
        if os.getenv('CLAUDE_REDIRECT_URI'):
            self.oauth.redirect_uri = os.getenv('CLAUDE_REDIRECT_URI')
        if os.getenv('CLAUDE_ENCRYPTION_KEY_PATH'):
            self.security.encryption_key_path = os.getenv('CLAUDE_ENCRYPTION_KEY_PATH')
        if os.getenv('CLAUDE_TOKEN_STORAGE_PATH'):
            self.security.token_storage_path = os.getenv('CLAUDE_TOKEN_STORAGE_PATH')
        if os.getenv('CLAUDE_PROXY_PORT'):
            self.proxy.default_port = int(os.getenv('CLAUDE_PROXY_PORT'))
        if os.getenv('CLAUDE_PROXY_HOST'):
            self.proxy.default_host = os.getenv('CLAUDE_PROXY_HOST')
        if os.getenv('CLAUDE_DEFAULT_MODEL'):
            self.proxy.default_model = os.getenv('CLAUDE_DEFAULT_MODEL')
        if os.getenv('CLAUDE_LOG_LEVEL'):
            self.logging.level = os.getenv('CLAUDE_LOG_LEVEL')
        if os.getenv('CLAUDE_LOG_FILE'):
            self.logging.file_path = os.getenv('CLAUDE_LOG_FILE')
            return None
        return None
    # WARNING: Decompyle incomplete

    
    def get_expanded_path(self = None, path = None):
        '''Get expanded path (handles ~ and environment variables).'''
        return Path(os.path.expandvars(os.path.expanduser(path)))

    
    def to_dict(self = None):
        '''Convert settings to dictionary.'''
        return {
            'oauth': asdict(self.oauth),
            'security': asdict(self.security),
            'proxy': asdict(self.proxy),
            'logging': asdict(self.logging) }

    
    def validate(self = None):
        '''Validate configuration settings.'''
        errors = []
        if not self.oauth.client_id:
            errors.append('OAuth client_id is required')
        if not self.oauth.client_secret:
            errors.append('OAuth client_secret is required')
        if not self.oauth.redirect_uri:
            errors.append('OAuth redirect_uri is required')
        required_urls = [
            ('auth_url', self.oauth.auth_url),
            ('token_url', self.oauth.token_url)]
    # WARNING: Decompyle incomplete


