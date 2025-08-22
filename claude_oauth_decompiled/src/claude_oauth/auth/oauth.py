# Source Generated with Decompyle++
# File: oauth.cpython-312.pyc (Python 3.12)

__doc__ = '\nPKCE OAuth implementation for Claude Max authentication.\nHandles the complete OAuth flow with security best practices.\n'
import base64
import hashlib
import json
import logging
import os
import secrets
import socket
import threading
import time
import urllib.parse as urllib
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Tuple, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
logger = logging.getLogger(__name__)
OAuthConfig = <NODE:12>()

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    '''HTTP request handler for OAuth callback'''
    
    def do_GET(self):
        '''Handle GET request with authorization code'''
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.server.state = params.get('state', [
                None])[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            success_html = '\n            <!DOCTYPE html>\n            <html>\n            <head>\n                <title>Authentication Successful</title>\n                <style>\n                    body {\n                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;\n                        display: flex;\n                        justify-content: center;\n                        align-items: center;\n                        height: 100vh;\n                        margin: 0;\n                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);\n                    }\n                    .container {\n                        background: white;\n                        padding: 2rem;\n                        border-radius: 10px;\n                        box-shadow: 0 10px 25px rgba(0,0,0,0.1);\n                        text-align: center;\n                    }\n                    .success-icon {\n                        font-size: 48px;\n                        color: #48bb78;\n                        margin-bottom: 1rem;\n                    }\n                    h1 {\n                        color: #2d3748;\n                        margin-bottom: 0.5rem;\n                    }\n                    p {\n                        color: #718096;\n                    }\n                </style>\n            </head>\n            <body>\n                <div class="container">\n                    <div class="success-icon">✓</div>\n                    <h1>Authentication Successful!</h1>\n                    <p>You can now close this window and return to the terminal.</p>\n                </div>\n            </body>\n            </html>\n            '
            self.wfile.write(success_html.encode())
            return None
        if 'error' in params:
            self.server.error = params['error'][0]
            self.server.error_description = params.get('error_description', [
                'Unknown error'])[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            error_html = f'''\n            <!DOCTYPE html>\n            <html>\n            <head>\n                <title>Authentication Failed</title>\n                <style>\n                    body {{\n                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;\n                        display: flex;\n                        justify-content: center;\n                        align-items: center;\n                        height: 100vh;\n                        margin: 0;\n                        background: linear-gradient(135deg, #f56565 0%, #c53030 100%);\n                    }}\n                    .container {{\n                        background: white;\n                        padding: 2rem;\n                        border-radius: 10px;\n                        box-shadow: 0 10px 25px rgba(0,0,0,0.1);\n                        text-align: center;\n                        max-width: 400px;\n                    }}\n                    .error-icon {{\n                        font-size: 48px;\n                        color: #f56565;\n                        margin-bottom: 1rem;\n                    }}\n                    h1 {{\n                        color: #2d3748;\n                        margin-bottom: 0.5rem;\n                    }}\n                    p {{\n                        color: #718096;\n                    }}\n                    .error-details {{\n                        background: #fed7d7;\n                        color: #742a2a;\n                        padding: 0.5rem;\n                        border-radius: 5px;\n                        margin-top: 1rem;\n                        font-size: 0.875rem;\n                    }}\n                </style>\n            </head>\n            <body>\n                <div class="container">\n                    <div class="error-icon">✗</div>\n                    <h1>Authentication Failed</h1>\n                    <p>There was an error during authentication.</p>\n                    <div class="error-details">\n                        {params.get('error_description', [
                'Unknown error'])[0]}\n                    </div>\n                </div>\n            </body>\n            </html>\n            '''
            self.wfile.write(error_html.encode())
            return None
        self.send_response(400)
        self.end_headers()
        self.wfile.write(b'Missing authorization code or error parameter')

    
    def log_message(self, *args):
        '''Suppress default HTTP server logging'''
        pass



class ClaudeOAuth:
    '''Main OAuth client for Claude Max authentication'''
    
    def __init__(self = None, config = None):
        '''Initialize OAuth client with configuration'''
        pass
    # WARNING: Decompyle incomplete

    
    def _setup_session(self):
        '''Setup requests session with retry logic'''
        self.session = requests.Session()
        retry_strategy = Retry(total = 3, backoff_factor = 1, status_forcelist = [
            429,
            500,
            502,
            503,
            504])
        adapter = HTTPAdapter(max_retries = retry_strategy)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

    
    def generate_pkce(self = None):
        '''
        Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (verifier, challenge)
        '''
        pass
    # WARNING: Decompyle incomplete

    
    def generate_state(self = None):
        '''Generate random state parameter for CSRF protection'''
        return secrets.token_urlsafe(32)

    
    def get_authorization_url(self = None, code_challenge = None, state = None):
        '''
        Build the authorization URL for the OAuth flow.
        
        Args:
            code_challenge: PKCE code challenge
            state: State parameter for CSRF protection
            
        Returns:
            Complete authorization URL
        '''
        params = {
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'scope': self.config.scope,
            'state': state }
        return f'''{self.config.auth_url}?{urllib.parse.urlencode(params)}'''

    
    def start_callback_server(self = None):
        '''
        Start local HTTP server to receive OAuth callback.
        
        Returns:
            Tuple of (auth_code, state, error)
        '''
        server = HTTPServer(('localhost', self.config.callback_port), OAuthCallbackHandler)
        server.auth_code = None
        server.state = None
        server.error = None
        server.error_description = None
        server.timeout = self.config.callback_timeout
        logger.info(f'''Starting callback server on port {self.config.callback_port}''')
        server.handle_request()
        if server.error:
            error_msg = f'''{server.error}: {server.error_description}'''
            logger.error(f'''OAuth error: {error_msg}''')
            return (None, None, error_msg)
        return (None.auth_code, server.state, None)

    
    def exchange_code(self = None, code = None, code_verifier = None):
        '''
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from callback
            code_verifier: PKCE code verifier
            
        Returns:
            Token response dictionary
            
        Raises:
            requests.HTTPError: If token exchange fails
        '''
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'code_verifier': code_verifier,
            'redirect_uri': self.config.redirect_uri,
            'client_id': self.config.client_id }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json' }
        logger.info('Exchanging authorization code for tokens')
        logger.debug(f'''Token URL: {self.config.token_url}''')
        logger.debug(f'''Request data: {data}''')
        response = self.session.post(self.config.token_url, data = data, headers = headers)
        logger.debug(f'''Response status: {response.status_code}''')
        logger.debug(f'''Response headers: {response.headers}''')
        if response.status_code == 403:
            logger.error('403 Forbidden - Client may not be authorized for token exchange')
            logger.error(f'''Response body: {response.text}''')
        response.raise_for_status()
        tokens = response.json()
        if 'expires_in' in tokens:
            tokens['expires_at'] = time.time() + tokens['expires_in']
        logger.info('Successfully obtained access token')
        return tokens

    
    def refresh_token(self = None, refresh_token = None):
        '''
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New token response dictionary
            
        Raises:
            requests.HTTPError: If token refresh fails
        '''
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config.client_id }
        logger.info('Refreshing access token')
        response = self.session.post(self.config.token_url, data = data)
        response.raise_for_status()
        tokens = response.json()
        if 'expires_in' in tokens:
            tokens['expires_at'] = time.time() + tokens['expires_in']
        logger.info('Successfully refreshed access token')
        return tokens

    
    def authenticate(self = None, open_browser = None):
        '''
        Perform complete OAuth authentication flow.
        
        Args:
            open_browser: Whether to automatically open browser
            
        Returns:
            Token response dictionary
            
        Raises:
            Exception: If authentication fails
        '''
        (code_verifier, code_challenge) = self.generate_pkce()
        state = self.generate_state()
        auth_url = self.get_authorization_url(code_challenge, state)
        if open_browser:
            logger.info(f'''Opening browser for authentication: {auth_url}''')
            webbrowser.open(auth_url)
        else:
            print(f'''Please visit this URL to authenticate:\n{auth_url}''')
        (auth_code, returned_state, error) = self.start_callback_server()
        if error:
            raise Exception(f'''Authentication failed: {error}''')
        if not None:
            raise Exception('No authorization code received')
        if None != state:
            raise Exception('State parameter mismatch - possible CSRF attack')
        tokens = None.exchange_code(auth_code, code_verifier)
        return tokens

    
    def validate_token(self = None, access_token = None):
        '''
        Validate if an access token is still valid.
        
        Args:
            access_token: Token to validate
            
        Returns:
            True if token is valid
        '''
        headers = {
            'Authorization': f'''Bearer {access_token}''',
            'anthropic-beta': 'oauth-2025-04-20' }
        response = self.session.get('https://api.anthropic.com/v1/models', headers = headers, timeout = 5)
        return response.status_code == 200
    # WARNING: Decompyle incomplete


# WARNING: Decompyle incomplete
