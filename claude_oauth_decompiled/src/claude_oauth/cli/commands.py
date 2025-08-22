# Source Generated with Decompyle++
# File: commands.cpython-312.pyc (Python 3.12)

'''
CLI Commands Implementation
==========================

Command handlers for the Claude OAuth CLI interface.
'''
import json
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time
from auth import OAuthClient, TokenManager
from storage import SecureTokenStorage
logger = logging.getLogger(__name__)

class CallbackHandler(BaseHTTPRequestHandler):
    '''HTTP handler for OAuth callback.'''
    
    def do_GET(self):
        '''Handle GET request to callback endpoint.'''
        if self.path.startswith('/callback'):
            self.server.callback_url = f'''http://localhost:{self.server.server_port}{self.path}'''
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html_response = '\n            <!DOCTYPE html>\n            <html>\n            <head>\n                <title>Claude OAuth - Success</title>\n                <style>\n                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }\n                    .success { color: green; font-size: 24px; margin-bottom: 20px; }\n                    .message { color: #666; }\n                </style>\n            </head>\n            <body>\n                <div class="success">✓ Authentication Successful!</div>\n                <div class="message">\n                    <p>You have successfully authenticated with Claude OAuth.</p>\n                    <p>You can close this window and return to your terminal.</p>\n                </div>\n            </body>\n            </html>\n            '
            self.wfile.write(html_response.encode())
            return None
        self.send_response(404)
        self.end_headers()

    
    def log_message(self, format, *args):
        '''Suppress default HTTP server logging.'''
        pass



class AuthCommands:
    '''Authentication command handlers.'''
    
    def __init__(self = None, oauth_client = None, storage = None):
        '''Initialize auth commands.'''
        self.oauth_client = oauth_client
        self.storage = storage

    
    def execute(self = None, args = None):
        '''Execute auth command based on arguments.'''
        if args.auth_command == 'login':
            return self.login(args)
        if None.auth_command == 'logout':
            return self.logout(args)
        if None.auth_command == 'status':
            return self.status(args)
        None('Unknown auth command. Use --help for available commands.')
        return 1

    
    def login(self = None, args = None):
        '''Handle login command.'''
        print(f'''Starting OAuth login for user: {args.user_id}''')
        auth_url = self.oauth_client.generate_authorization_url()
        print('Opening authorization URL in browser...')
        print(f'''If browser doesn\'t open automatically, visit: {auth_url}''')
        webbrowser.open(auth_url)
        callback_url = self._wait_for_callback(args.port)
        if not callback_url:
            print('✗ Login failed: No authorization code received')
            return 1
        print('Exchanging authorization code for access token...')
        token_data = self.oauth_client.exchange_code_for_token(callback_url)
        token_manager = TokenManager(self.oauth_client, self.storage, args.user_id)
        token_manager.store_token(token_data)
        print(f'''✓ Login successful for user: {args.user_id}''')
        token_info = token_manager.get_token_info()
        if token_info['expires_in_seconds']:
            minutes = token_info['expires_in_seconds'] // 60
            print(f'''Token expires in: {minutes} minutes''')
        return 0
    # WARNING: Decompyle incomplete

    
    def logout(self = None, args = None):
        '''Handle logout command.'''
        print(f'''Logging out user: {args.user_id}''')
        token_manager = TokenManager(self.oauth_client, self.storage, args.user_id)
        if args.revoke:
            print('Revoking tokens on server...')
            if token_manager.revoke_token():
                print('✓ Tokens revoked successfully')
                return 0
            print('⚠ Token revocation may have failed')
            return 0
        self.storage.delete_token(args.user_id)
        print('✓ Local tokens cleared')
        return 0
    # WARNING: Decompyle incomplete

    
    def status(self = None, args = None):
        '''Handle status command.'''
        if args.user_id:
            return self._show_user_status(args.user_id)
        users = None.storage.list_users()
        if not users:
            print('No authenticated users found.')
            return 0
        print(f'''Authentication status for {len(users)} user(s):''')
    # WARNING: Decompyle incomplete

    
    def _wait_for_callback(self = None, port = None, timeout = None):
        '''Wait for OAuth callback.'''
        server = HTTPServer(('localhost', port), CallbackHandler)
        server.timeout = 1
        server.callback_url = None
        print(f'''Waiting for authorization callback on port {port}...''')
        print('Please complete the authorization in your browser.')
        start_time = time.time()
    # WARNING: Decompyle incomplete

    
    def _show_user_status(self = None, user_id = None, indent = None):
        '''Show status for a specific user.'''
        token_manager = TokenManager(self.oauth_client, self.storage, user_id)
        token_info = token_manager.get_token_info()
        if token_info['valid']:
            print(f'''{indent}✓ Authenticated''')
            if token_info['expires_in_seconds']:
                minutes = token_info['expires_in_seconds'] // 60
                print(f'''{indent}  Token expires in: {minutes} minutes''')
            if token_info['scopes']:
                print(f'''{indent}  Scopes: {', '.join(token_info['scopes'])}''')
            if token_info['needs_refresh']:
                print(f'''{indent}  ⚠ Token needs refresh soon''')
            return 0
        print(f'''{indent}✗ Not authenticated or token expired''')
        print(f'''{indent}  Reason: {token_info.get('message', 'Unknown')}''')
        return 0
    # WARNING: Decompyle incomplete



class TokenCommands:
    '''Token management command handlers.'''
    
    def __init__(self = None, storage = None):
        '''Initialize token commands.'''
        self.storage = storage

    
    def execute(self = None, args = None):
        '''Execute token command based on arguments.'''
        if args.token_command == 'info':
            return self.info(args)
        if None.token_command == 'refresh':
            return self.refresh(args)
        if None.token_command == 'revoke':
            return self.revoke(args)
        if None.token_command == 'cleanup':
            return self.cleanup(args)
        None('Unknown token command. Use --help for available commands.')
        return 1

    
    def info(self = None, args = None):
        '''Show token information.'''
        token_data = self.storage.get_token(args.user_id)
        if not token_data:
            print(f'''No token found for user: {args.user_id}''')
            return 1
        print(f'''Token information for user: {args.user_id}''')
        print(f'''  Has access token: {'Yes' if 'access_token' in token_data else 'No'}''')
        print(f'''  Has refresh token: {'Yes' if 'refresh_token' in token_data else 'No'}''')
        if 'expires_at' in token_data:
            print(f'''  Expires at: {token_data['expires_at']}''')
        if 'scope' in token_data:
            scopes = token_data['scope'].split() if isinstance(token_data['scope'], str) else token_data['scope']
            print(f'''  Scopes: {', '.join(scopes)}''')
        return 0
    # WARNING: Decompyle incomplete

    
    def refresh(self = None, args = None):
        '''Refresh access token.'''
        OAuthConfig = OAuthConfig
        OAuthClient = OAuthClient
        import auth
        config = OAuthConfig(client_id = 'refresh')
        oauth_client = OAuthClient(config)
        token_manager = TokenManager(oauth_client, self.storage, args.user_id)
        print(f'''Refreshing token for user: {args.user_id}''')
        access_token = token_manager.get_access_token()
        print('✓ Token refreshed successfully')
        token_info = token_manager.get_token_info()
        if token_info['expires_in_seconds']:
            minutes = token_info['expires_in_seconds'] // 60
            print(f'''New token expires in: {minutes} minutes''')
        return 0
    # WARNING: Decompyle incomplete

    
    def revoke(self = None, args = None):
        '''Revoke token.'''
        OAuthConfig = OAuthConfig
        OAuthClient = OAuthClient
        import auth
        config = OAuthConfig(client_id = 'revoke')
        oauth_client = OAuthClient(config)
        token_manager = TokenManager(oauth_client, self.storage, args.user_id)
        print(f'''Revoking token for user: {args.user_id}''')
        if token_manager.revoke_token():
            print('✓ Token revoked successfully')
            return 0
        print('⚠ Token revocation may have failed')
        return 1
    # WARNING: Decompyle incomplete

    
    def cleanup(self = None, args = None):
        '''Clean up expired tokens.'''
        print('Cleaning up expired tokens...')
        cleaned_count = self.storage.cleanup_expired_tokens()
        if cleaned_count > 0:
            print(f'''✓ Cleaned up {cleaned_count} expired token(s)''')
            return 0
        print('No expired tokens found')
        return 0
    # WARNING: Decompyle incomplete



class ConfigCommands:
    '''Configuration command handlers.'''
    
    def __init__(self = None, config_file = None):
        '''Initialize config commands.'''
        pass
    # WARNING: Decompyle incomplete

    
    def execute(self = None, args = None):
        '''Execute config command based on arguments.'''
        if args.config_command == 'show':
            return self.show(args)
        if None.config_command == 'set':
            return self.set(args)
        if None.config_command == 'init':
            return self.init(args)
        None('Unknown config command. Use --help for available commands.')
        return 1

    
    def show(self = None, args = None):
        '''Show current configuration.'''
        if not self.config_file.exists():
            print("No configuration file found. Run 'claude-oauth config init' to create one.")
            return 0
    # WARNING: Decompyle incomplete

    
    def set(self = None, args = None):
        '''Set configuration value.'''
        config = { }
    # WARNING: Decompyle incomplete

    
    def init(self = None, args = None):
        '''Initialize configuration.'''
        default_config = {
            'client_id': '',
            'client_secret': '',
            'api_base': 'https://api.anthropic.com/v1',
            'storage_backend': 'file',
            'default_model': 'claude-3-sonnet-20240229' }
    # WARNING: Decompyle incomplete


