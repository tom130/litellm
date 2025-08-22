"""
Claude OAuth CLI Commands

Provides command-line interface for Claude OAuth authentication flow.
"""

import asyncio
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional

import click

from litellm._logging import verbose_proxy_logger
from litellm.proxy.auth.claude_oauth_flow import ClaudeOAuthFlow
from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler
from litellm.proxy.auth.claude_token_manager import ClaudeTokenInfo, ClaudeTokenManager


# Configuration file paths
CONFIG_DIR = Path.home() / ".litellm"
TOKEN_FILE = CONFIG_DIR / "claude_tokens.json"
CONFIG_DIR.mkdir(exist_ok=True)


@click.group()
def claude():
    """Claude OAuth authentication management."""
    pass


@claude.command()
@click.option(
    "--no-browser",
    is_flag=True,
    help="Don't automatically open browser"
)
@click.option(
    "--state-dir",
    type=click.Path(),
    help="Directory for storing OAuth state (default: /tmp)"
)
def login(no_browser: bool, state_dir: Optional[str]):
    """
    Start Claude OAuth login flow.
    
    This command will:
    1. Generate an authorization URL
    2. Open it in your browser (unless --no-browser)
    3. Wait for you to complete authentication
    4. Provide instructions for completing the flow
    """
    async def _login():
        click.echo("🔐 Starting Claude OAuth authentication...")
        click.echo("=" * 60)
        
        # Initialize OAuth flow
        flow = ClaudeOAuthFlow(state_dir=state_dir)
        
        # Clean up any expired states first
        flow.cleanup_expired_states()
        
        # Start OAuth flow
        auth_url, state = await flow.start_flow()
        
        click.echo("\n📋 Authorization URL generated!")
        
        # Open browser unless disabled
        if not no_browser:
            click.echo("🌐 Opening browser...")
            webbrowser.open(auth_url)
            click.echo("   Browser opened. Please complete authentication.")
        else:
            click.echo(f"\n🔗 Please visit this URL to authenticate:")
            click.echo(f"   {auth_url}")
        
        click.echo("\n" + "=" * 60)
        click.echo("📝 After authorization, you'll be redirected to:")
        click.echo("   https://console.anthropic.com/oauth/code/callback")
        click.echo("\n⚠️  Copy the CODE parameter from the redirect URL")
        click.echo("\n💡 Then run:")
        click.echo(f"   litellm claude callback <CODE>")
        click.echo("=" * 60)
        
        # Save state for reference
        state_file = CONFIG_DIR / "oauth_state.txt"
        state_file.write_text(state)
        click.echo(f"\n✅ State saved. This session expires in 10 minutes.")
    
    # Run async function
    asyncio.run(_login())


@claude.command()
@click.argument("code")
@click.option(
    "--state-dir",
    type=click.Path(),
    help="Directory for storing OAuth state (default: /tmp)"
)
def callback(code: str, state_dir: Optional[str]):
    """
    Complete OAuth flow with authorization code.
    
    CODE: The authorization code from the callback URL
    """
    async def _callback():
        click.echo("🔄 Completing OAuth authentication...")
        
        # Load saved state
        state_file = CONFIG_DIR / "oauth_state.txt"
        if not state_file.exists():
            click.echo("❌ No saved state found. Please run 'litellm claude login' first.")
            sys.exit(1)
        
        state = state_file.read_text().strip()
        
        # Initialize OAuth flow
        flow = ClaudeOAuthFlow(state_dir=state_dir)
        
        try:
            # Exchange code for tokens
            click.echo("🔄 Exchanging authorization code for tokens...")
            token_data = await flow.complete_flow(code, state)
            
            # Save tokens
            TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
            TOKEN_FILE.chmod(0o600)  # Restrict permissions
            
            # Clean up state file
            state_file.unlink(missing_ok=True)
            
            # Display success
            click.echo("\n" + "=" * 60)
            click.echo("✅ Authentication successful!")
            click.echo("=" * 60)
            
            # Show token info
            expires_at = token_data.get("expiresAt", 0)
            expires_in = expires_at - int(time.time())
            expires_hours = expires_in / 3600
            
            click.echo(f"\n📊 Token Information:")
            click.echo(f"   • Scopes: {', '.join(token_data.get('scopes', []))}")
            click.echo(f"   • Claude Max: {'Yes' if token_data.get('isMax') else 'No'}")
            click.echo(f"   • Expires in: {expires_hours:.1f} hours")
            click.echo(f"\n📁 Tokens saved to: {TOKEN_FILE}")
            
            # Set environment variables hint
            click.echo("\n💡 To use these tokens, set environment variables:")
            click.echo(f"   export CLAUDE_ACCESS_TOKEN={token_data['accessToken'][:20]}...")
            click.echo(f"   export CLAUDE_REFRESH_TOKEN={token_data['refreshToken'][:20]}...")
            click.echo(f"   export CLAUDE_EXPIRES_AT={token_data['expiresAt']}")
            
        except ValueError as e:
            click.echo(f"❌ Authentication failed: {e}")
            click.echo("   Your session may have expired. Please run 'litellm claude login' again.")
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            sys.exit(1)
    
    # Run async function
    asyncio.run(_callback())


@claude.command()
def status():
    """Check Claude OAuth token status."""
    
    # Check environment variables first
    has_env_tokens = all([
        os.getenv("CLAUDE_ACCESS_TOKEN"),
        os.getenv("CLAUDE_REFRESH_TOKEN"),
        os.getenv("CLAUDE_EXPIRES_AT")
    ])
    
    # Check saved token file
    has_file_tokens = TOKEN_FILE.exists()
    
    click.echo("🔍 Claude OAuth Status")
    click.echo("=" * 60)
    
    if not has_env_tokens and not has_file_tokens:
        click.echo("❌ No tokens found")
        click.echo("\n   Run 'litellm claude login' to authenticate")
        return
    
    # Load tokens
    if has_env_tokens:
        click.echo("✅ Using tokens from environment variables")
        expires_at = int(os.getenv("CLAUDE_EXPIRES_AT", 0))
    else:
        click.echo(f"✅ Using tokens from: {TOKEN_FILE}")
        token_data = json.loads(TOKEN_FILE.read_text())
        expires_at = token_data.get("expiresAt", 0)
    
    # Check expiration
    current_time = int(time.time())
    if expires_at > current_time:
        expires_in = expires_at - current_time
        hours = expires_in / 3600
        days = expires_in / 86400
        
        if days > 1:
            expiry_text = f"{days:.1f} days"
        else:
            expiry_text = f"{hours:.1f} hours"
        
        click.echo(f"\n📊 Token Status:")
        click.echo(f"   • Status: ✅ Valid")
        click.echo(f"   • Expires in: {expiry_text}")
        
        # Warning if expiring soon
        if hours < 24:
            click.echo(f"\n⚠️  Token expires soon! Consider refreshing.")
    else:
        click.echo(f"\n📊 Token Status:")
        click.echo(f"   • Status: ❌ Expired")
        click.echo(f"\n   Run 'litellm claude login' to re-authenticate")


@claude.command()
def refresh():
    """Manually refresh Claude OAuth tokens."""
    
    async def _refresh():
        click.echo("🔄 Refreshing Claude OAuth tokens...")
        
        # Load current tokens
        if not TOKEN_FILE.exists():
            # Try environment variables
            access_token = os.getenv("CLAUDE_ACCESS_TOKEN")
            refresh_token = os.getenv("CLAUDE_REFRESH_TOKEN")
            expires_at = os.getenv("CLAUDE_EXPIRES_AT")
            
            if not all([access_token, refresh_token, expires_at]):
                click.echo("❌ No tokens found to refresh")
                click.echo("   Run 'litellm claude login' to authenticate")
                sys.exit(1)
        else:
            token_data = json.loads(TOKEN_FILE.read_text())
            access_token = token_data.get("accessToken")
            refresh_token = token_data.get("refreshToken")
            expires_at = token_data.get("expiresAt")
        
        # Initialize handler with current tokens
        handler = ClaudeOAuthHandler(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at
        )
        
        try:
            # Refresh tokens
            new_token_data = await handler.refresh_access_token()
            
            # Save refreshed tokens
            TOKEN_FILE.write_text(json.dumps(new_token_data, indent=2))
            TOKEN_FILE.chmod(0o600)
            
            click.echo("✅ Tokens refreshed successfully!")
            
            # Show new expiration
            expires_at = new_token_data.get("expiresAt", 0)
            expires_in = expires_at - int(time.time())
            hours = expires_in / 3600
            
            click.echo(f"\n📊 New token expires in: {hours:.1f} hours")
            
        except Exception as e:
            click.echo(f"❌ Refresh failed: {e}")
            click.echo("\n   Your refresh token may have expired.")
            click.echo("   Run 'litellm claude login' to re-authenticate")
            sys.exit(1)
    
    # Run async function
    asyncio.run(_refresh())


@claude.command()
@click.confirmation_option(prompt="Are you sure you want to clear tokens?")
def logout():
    """Clear stored Claude OAuth tokens."""
    
    click.echo("🗑️  Clearing Claude OAuth tokens...")
    
    # Remove token file
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        click.echo(f"   ✅ Removed: {TOKEN_FILE}")
    
    # Clear OAuth state if exists
    state_file = CONFIG_DIR / "oauth_state.txt"
    if state_file.exists():
        state_file.unlink()
        click.echo(f"   ✅ Removed: OAuth state")
    
    # Clean up any OAuth state files in temp
    flow = ClaudeOAuthFlow()
    cleaned = flow.cleanup_expired_states()
    if cleaned > 0:
        click.echo(f"   ✅ Cleaned up {cleaned} temporary state files")
    
    click.echo("\n✅ Logout complete")
    click.echo("   Run 'litellm claude login' to authenticate again")


@claude.command()
def export():
    """Export tokens as environment variables."""
    
    if not TOKEN_FILE.exists():
        click.echo("❌ No tokens found")
        click.echo("   Run 'litellm claude login' to authenticate")
        return
    
    token_data = json.loads(TOKEN_FILE.read_text())
    
    click.echo("# Claude OAuth Token Environment Variables")
    click.echo("# Add these to your shell profile or .env file")
    click.echo()
    click.echo(f"export CLAUDE_ACCESS_TOKEN='{token_data['accessToken']}'")
    click.echo(f"export CLAUDE_REFRESH_TOKEN='{token_data['refreshToken']}'")
    click.echo(f"export CLAUDE_EXPIRES_AT='{token_data['expiresAt']}'")


def register_claude_commands(cli_group):
    """
    Register Claude OAuth commands with the main CLI.
    
    Args:
        cli_group: The main Click CLI group to add commands to
    """
    cli_group.add_command(claude)


if __name__ == "__main__":
    # For standalone testing
    claude()