# Claude OAuth Token Management

Use pre-existing OAuth tokens from Claude.ai to authenticate with Claude Max models through the LiteLLM Proxy. This provides secure, token-based access to Claude Sonnet and Claude Opus models.

> **Important**: This implementation manages existing OAuth tokens obtained from Claude.ai. It does NOT implement an OAuth flow - you must obtain tokens directly from Claude.ai first.

## Features

- 🔑 **Token Management**: Secure storage and management of existing OAuth tokens
- 🔄 **Automatic Token Refresh**: Tokens are refreshed automatically before expiration
- 🔐 **Encrypted Storage**: AES-256 encryption for stored tokens
- 👥 **Multi-User Support**: Isolated token management per user
- 📊 **Token Lifecycle Management**: Track token usage, expiration, and refresh counts
- 🚀 **Zero-Downtime Auth**: Transparent token refresh without request interruption

## Quick Start

### 1. Obtain Tokens from Claude.ai

First, you need to obtain OAuth tokens from Claude.ai. These tokens include:
- `access_token`: The bearer token for API authentication
- `refresh_token`: Token used to refresh the access token
- `expires_at`: Unix timestamp when the token expires

### 2. Set Environment Variables

```bash
# Required - Your OAuth tokens from Claude.ai
export CLAUDE_ACCESS_TOKEN="your-access-token"
export CLAUDE_REFRESH_TOKEN="your-refresh-token"
export CLAUDE_EXPIRES_AT="1234567890"  # Unix timestamp

# Optional but recommended
export CLAUDE_TOKEN_ENCRYPTION_KEY="your-encryption-key"  # Generate with: openssl rand -base64 32
export DATABASE_URL="postgresql://user:pass@localhost/litellm"  # For persistent token storage
```

### 3. Configure LiteLLM Proxy

Add to your `config.yaml`:

```yaml
model_list:
  - model_name: claude-3-sonnet
    litellm_params:
      model: anthropic/claude-3-sonnet-20240229
      
  - model_name: claude-3-opus
    litellm_params:
      model: anthropic/claude-3-opus-20240229

general_settings:
  master_key: sk-1234
  
  claude_oauth:
    enabled: true
    access_token: "${CLAUDE_ACCESS_TOKEN}"
    refresh_token: "${CLAUDE_REFRESH_TOKEN}"
    expires_at: "${CLAUDE_EXPIRES_AT}"
    
    # Token management
    auto_refresh: true
    refresh_threshold: 300  # Refresh 5 minutes before expiry
    
    # Security settings
    token_encryption: true
```

### 4. Start the Proxy

```bash
litellm --config config.yaml
```

## Using Claude Models

Once configured, use Claude models like any other LiteLLM model:

```python
from litellm import completion

# OAuth token is automatically used
response = completion(
    model="claude-3-sonnet",
    messages=[{"role": "user", "content": "Hello!"}],
    api_key="YOUR_LITELLM_KEY"  # Your LiteLLM proxy key
)
```

### With OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_LITELLM_KEY",
    base_url="http://localhost:4000"
)

response = client.chat.completions.create(
    model="claude-3-opus",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### With cURL

```bash
curl -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer YOUR_LITELLM_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-sonnet",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Direct Bearer Token Usage

You can also pass the OAuth token directly:

```bash
curl -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer YOUR_OAUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-sonnet",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## API Endpoints

### Token Management

#### `GET /auth/claude/status`
Check OAuth token status.

```bash
curl http://localhost:4000/auth/claude/status \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

**Response:**
```json
{
  "authenticated": true,
  "expires_in": 3542,
  "expires_at": 1234567890,
  "scopes": ["org:create_api_key", "user:profile", "user:inference"],
  "is_max": true,
  "refresh_count": 2,
  "auto_refresh_enabled": true
}
```

#### `POST /auth/claude/refresh`
Manually refresh the OAuth token.

```bash
curl -X POST http://localhost:4000/auth/claude/refresh \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

#### `DELETE /auth/claude/revoke`
Revoke OAuth tokens.

```bash
curl -X DELETE http://localhost:4000/auth/claude/revoke \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

#### `GET /auth/claude/health`
Health check for OAuth service.

```bash
curl http://localhost:4000/auth/claude/health
```

## Advanced Configuration

### Database Setup

For production, use PostgreSQL for persistent token storage:

1. Run the migration:
```sql
CREATE TABLE IF NOT EXISTS claude_oauth_tokens (
  user_id VARCHAR(256) PRIMARY KEY,
  access_token_encrypted TEXT NOT NULL,
  refresh_token_encrypted TEXT,
  expires_at BIGINT NOT NULL,
  scopes TEXT[],
  is_max BOOLEAN DEFAULT true,
  refresh_count INTEGER DEFAULT 0,
  last_used BIGINT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

2. Configure database in environment:
```bash
export DATABASE_URL="postgresql://user:pass@localhost/litellm"
```

### Security Best Practices

1. **Generate Strong Encryption Key**:
```bash
export CLAUDE_TOKEN_ENCRYPTION_KEY=$(openssl rand -base64 32)
```

2. **Use HTTPS in Production**:
Ensure all API calls use HTTPS to protect token transmission.

3. **Secure Token Storage**:
Never log or expose tokens. Always use encryption for storage.

4. **Regular Token Rotation**:
Tokens are automatically refreshed before expiration.

### Multi-User Configuration

Enable team-based token management:

```yaml
claude_oauth:
  multi_user:
    enabled: true
    isolation: strict  # Each user has separate tokens
```

### Token Refresh Strategy

Configure automatic refresh behavior:

```yaml
claude_oauth:
  auto_refresh:
    enabled: true
    threshold: 300  # Seconds before expiry
    max_retries: 3
    retry_backoff: exponential
```

## Monitoring

### Token Statistics

Get OAuth token statistics:

```bash
curl http://localhost:4000/auth/claude/stats
```

Response includes:
- Active tokens count
- Tokens expiring soon
- Refresh statistics
- Failed refresh attempts

### Prometheus Metrics

Available metrics:
- `litellm_claude_oauth_tokens_active`
- `litellm_claude_oauth_tokens_refreshed`
- `litellm_claude_oauth_auth_failures`
- `litellm_claude_oauth_token_expiry_seconds`

## Troubleshooting

### Common Issues

**"OAuth token expired"**
- Tokens are auto-refreshed 5 minutes before expiry
- Manually refresh: `POST /auth/claude/refresh`
- Check if refresh token is valid

**"No OAuth token found"**
- Ensure `CLAUDE_ACCESS_TOKEN` is set
- Check token configuration in `config.yaml`

**"Failed to refresh token"**
- Verify refresh token is valid
- Check network connectivity to Anthropic API
- May need to obtain new tokens from Claude.ai

**"anthropic-beta header required"**
- This header is automatically added
- Ensure you're using the latest version

### Debug Mode

Enable detailed logging:

```yaml
claude_oauth:
  debug: true
  log_tokens: false  # Never log actual tokens
```

```bash
litellm --config config.yaml --detailed_debug
```

## Migration from API Keys

Gradual migration path:

1. **Set Both Auth Methods**:
```yaml
model_list:
  - model_name: claude-3-sonnet
    litellm_params:
      model: anthropic/claude-3-sonnet-20240229
      api_key: "${ANTHROPIC_API_KEY}"  # Fallback to API key
```

2. **Configure OAuth**:
```yaml
claude_oauth:
  enabled: true
  access_token: "${CLAUDE_ACCESS_TOKEN}"
  refresh_token: "${CLAUDE_REFRESH_TOKEN}"
  expires_at: "${CLAUDE_EXPIRES_AT}"
```

3. **OAuth Takes Precedence**:
When both are configured, OAuth tokens are used first.

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `CLAUDE_ACCESS_TOKEN` | OAuth access token from Claude.ai | Yes | - |
| `CLAUDE_REFRESH_TOKEN` | OAuth refresh token from Claude.ai | Yes | - |
| `CLAUDE_EXPIRES_AT` | Token expiration Unix timestamp | Yes | - |
| `CLAUDE_TOKEN_ENCRYPTION_KEY` | AES-256 encryption key | No | Auto-generated |
| `CLAUDE_OAUTH_AUTO_REFRESH` | Enable auto-refresh | No | `true` |
| `CLAUDE_OAUTH_REFRESH_THRESHOLD` | Seconds before expiry to refresh | No | `300` |

## Important Notes

1. **No OAuth Flow**: This implementation does NOT include an OAuth authorization flow. You must obtain tokens from Claude.ai directly.

2. **Token Format**: Tokens use the format from Claude.ai:
   - `accessToken` (not `access_token`)
   - `refreshToken` (not `refresh_token`)
   - `expiresAt` as Unix timestamp (not datetime)

3. **Required Headers**: The `anthropic-beta: oauth-2025-04-20` header is automatically added to all OAuth requests.

4. **Scopes**: Default scopes are:
   - `org:create_api_key`
   - `user:profile`
   - `user:inference`

## Support

- [GitHub Issues](https://github.com/BerriAI/litellm/issues)
- [Discord Community](https://discord.gg/wuPM9dRgDw)
- [Enterprise Support](https://calendly.com/d/4mp-gd3-k5k/litellm-1-1-onboarding-chat)