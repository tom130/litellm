# Source Generated with Decompyle++
# File: main.cpython-312.pyc (Python 3.12)

'''
Claude OAuth CLI - Secure OAuth authentication for Claude AI API.
'''
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional
from auth import ClaudeOAuth, TokenManager
from storage import SecureTokenStore
from litellm import LiteLLMProxy
from  import __version__
logger = logging.getLogger(__name__)

def setup_logging(verbose = None):
    '''Setup logging configuration'''
    level = logging.DEBUG if verbose else logging.INFO
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s' if verbose else '%(message)s'
    logging.basicConfig(level = level, format = format, handlers = [
        logging.StreamHandler(sys.stdout)])


def cmd_auth(args):
    '''Perform OAuth authentication'''
    OAuthConfig = OAuthConfig
    import auth.oauth
    import urllib.parse as urllib
    import webbrowser
    config = OAuthConfig(client_id = '9d1c250a-e61b-44d9-88ed-5944d1962f5e', auth_url = 'https://claude.ai/oauth/authorize', token_url = 'https://claude.ai/oauth/token', redirect_uri = 'https://console.anthropic.com/oauth/code/callback', scope = 'org:create_api_key user:profile user:inference', callback_port = 8765)
    oauth = ClaudeOAuth(config)
    print('🔐 Claude OAuth Authentication')
    print('============================================================')
    (code_verifier, code_challenge) = oauth.generate_pkce()
    state = oauth.generate_state()
    params = {
        'code': 'true',
        'client_id': config.client_id,
        'response_type': 'code',
        'redirect_uri': config.redirect_uri,
        'scope': config.scope,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'state': state }
    auth_url = f'''{config.auth_url}?{urllib.parse.urlencode(params)}'''
    print('\nOpening browser for authentication...')
    if not args.no_browser:
        webbrowser.open(auth_url)
        print('Browser opened. Please login and authorize the application.')
    else:
        print(f'''\nPlease visit this URL to authenticate:\n{auth_url}''')
    print('\n============================================================')
    print("After authorization, you'll be redirected to the Console.")
    print('Copy the code shown on the page (format: CODE#STATE)')
    print('============================================================\n')
    paste_code = input('📋 Paste the authorization code here: ').strip()
    if not paste_code:
        raise Exception('No code provided')
    if None in paste_code:
        (auth_code, returned_state) = paste_code.split('#', 1)
    else:
        auth_code = paste_code
        returned_state = state
# WARNING: Decompyle incomplete


def cmd_token(args):
    '''Get or display token information'''
    manager = TokenManager()
    if args.refresh:
        print('🔄 Refreshing token...')
        token = manager.get_access_token()
        print('✅ Token refreshed successfully')
    info = manager.get_token_info()
    if not info:
        print("❌ No tokens found. Run 'claude-oauth auth' first.", file = sys.stderr)
        return 1
    if args.json:
        print(json.dumps(info, indent = 2))
    else:
        print('📊 Token Information:')
        print(f'''  Has access token: {info['has_access_token']}''')
        print(f'''  Has refresh token: {info['has_refresh_token']}''')
        print(f'''  Expires in: {info['expires_in']:.0f} seconds''')
        print(f'''  Is expired: {info['is_expired']}''')
        print(f'''  Needs refresh: {info['needs_refresh']}''')
    if args.get:
        token = manager.get_access_token()
        print(f'''\n{token}''')
    return 0
# WARNING: Decompyle incomplete


def cmd_validate(args):
    '''Validate current token'''
    manager = TokenManager()
    if manager.validate_token():
        print('✅ Token is valid')
        return 0
    print('❌ Token is invalid or expired', file = sys.stderr)
    return 1
# WARNING: Decompyle incomplete


def cmd_revoke(args):
    '''Revoke tokens'''
    manager = TokenManager()
    if not args.force:
        response = input('Are you sure you want to revoke all tokens? (y/N): ')
        if response.lower() != 'y':
            print('Cancelled')
            return 0
    manager.revoke_tokens()
    print('✅ Tokens revoked successfully')
    return 0
# WARNING: Decompyle incomplete


def cmd_proxy(args):
    '''Start LiteLLM proxy server'''
    proxy = LiteLLMProxy(port = args.port, host = args.host)
    print(f'''🚀 Starting LiteLLM proxy on {args.host}:{args.port}...''')
    print('Press Ctrl+C to stop\n')
    if args.auto_refresh:
        asyncio.run(proxy.run_with_token_refresh(refresh_interval = args.refresh_interval))
        return 0
    proxy.start(detached = False)
    return 0
# WARNING: Decompyle incomplete


def cmd_encrypt(args):
    '''Manage encryption keys'''
    store = SecureTokenStore(encryption_key = args.key, namespace = args.namespace)
    if args.action == 'rotate':
        if not args.new_key:
            print('❌ --new-key is required for rotation', file = sys.stderr)
            return 1
        print('🔄 Rotating encryption key...')
        store.rotate_encryption_key(args.new_key)
        print('✅ Encryption key rotated successfully')
        return 0
    if args.action == 'backup':
        if not args.output:
            args.output = f'''backup_{int(time.time())}.tar.gz'''
        print(f'''💾 Creating backup to {args.output}...''')
        store.backup(args.output)
        print('✅ Backup created successfully')
        return 0
    if args.action == 'restore':
        if not args.input:
            print('❌ --input is required for restore', file = sys.stderr)
            return 1
        print(f'''📥 Restoring from {args.input}...''')
        store.restore(args.input)
        print('✅ Backup restored successfully')
        return 0
    if args.action == 'cleanup':
        print(f'''🧹 Cleaning up tokens older than {args.max_age} days...''')
        count = store.cleanup_expired(args.max_age)
        print(f'''✅ Cleaned up {count} expired token files''')
    return 0
# WARNING: Decompyle incomplete


def create_parser():
    '''Create argument parser'''
    parser = argparse.ArgumentParser(prog = 'claude-oauth', description = 'Claude OAuth CLI - Secure OAuth authentication for Claude AI API', formatter_class = argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action = 'version', version = f'''%(prog)s {__version__}''')
    parser.add_argument('-v', '--verbose', action = 'store_true', help = 'Enable verbose output')
    parser.add_argument('-c', '--config', type = str, help = 'Configuration file path')
    subparsers = parser.add_subparsers(dest = 'command', help = 'Available commands')
    auth_parser = subparsers.add_parser('auth', help = 'Perform OAuth authentication')
    auth_parser.add_argument('--no-browser', action = 'store_true', help = "Don't open browser automatically")
    auth_parser.add_argument('--show-token', action = 'store_true', help = 'Display access token after authentication')
    auth_parser.set_defaults(func = cmd_auth)
    token_parser = subparsers.add_parser('token', help = 'Manage tokens')
    token_parser.add_argument('--get', action = 'store_true', help = 'Get current access token')
    token_parser.add_argument('--refresh', action = 'store_true', help = 'Force token refresh')
    token_parser.add_argument('--json', action = 'store_true', help = 'Output in JSON format')
    token_parser.set_defaults(func = cmd_token)
    validate_parser = subparsers.add_parser('validate', help = 'Validate current token')
    validate_parser.set_defaults(func = cmd_validate)
    revoke_parser = subparsers.add_parser('revoke', help = 'Revoke all tokens')
    revoke_parser.add_argument('-f', '--force', action = 'store_true', help = 'Skip confirmation')
    revoke_parser.set_defaults(func = cmd_revoke)
    proxy_parser = subparsers.add_parser('proxy', help = 'Start LiteLLM proxy server')
    proxy_parser.add_argument('-p', '--port', type = int, default = 4000, help = 'Proxy port (default: 4000)')
    proxy_parser.add_argument('-H', '--host', type = str, default = '0.0.0.0', help = 'Proxy host (default: 0.0.0.0)')
    proxy_parser.add_argument('--auto-refresh', action = 'store_true', help = 'Enable automatic token refresh')
    proxy_parser.add_argument('--refresh-interval', type = int, default = 1800, help = 'Token refresh interval in seconds (default: 1800)')
    proxy_parser.set_defaults(func = cmd_proxy)
    encrypt_parser = subparsers.add_parser('encrypt', help = 'Manage encryption')
    encrypt_parser.add_argument('action', choices = [
        'rotate',
        'backup',
        'restore',
        'cleanup'], help = 'Action to perform')
    encrypt_parser.add_argument('-k', '--key', type = str, help = 'Encryption key')
    encrypt_parser.add_argument('--new-key', type = str, help = 'New encryption key for rotation')
    encrypt_parser.add_argument('-n', '--namespace', type = str, default = 'default', help = 'Token namespace')
    encrypt_parser.add_argument('-o', '--output', type = str, help = 'Output file for backup')
    encrypt_parser.add_argument('-i', '--input', type = str, help = 'Input file for restore')
    encrypt_parser.add_argument('--max-age', type = int, default = 30, help = 'Max age in days for cleanup (default: 30)')
    encrypt_parser.set_defaults(func = cmd_encrypt)
    return parser


def cli():
    '''CLI entry point'''
    parser = create_parser()
    args = parser.parse_args()
    setup_logging(args.verbose if hasattr(args, 'verbose') else False)
    if hasattr(args, 'config') and args.config:
        pass
    if hasattr(args, 'func'):
        return args.func(args)
    None.print_help()
    return 0


def main():
    '''Main entry point'''
    sys.exit(cli())

if __name__ == '__main__':
    main()
    return None
