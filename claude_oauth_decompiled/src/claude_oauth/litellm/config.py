# Source Generated with Decompyle++
# File: config.cpython-312.pyc (Python 3.12)

'''
LiteLLM configuration generator for Claude models.
'''
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any

class LiteLLMConfig:
    '''Generate LiteLLM configuration for Claude models'''
    CLAUDE_MODELS = {
        'claude-sonnet-4': {
            'model_id': 'claude-sonnet-4-20250514',
            'supports_vision': True,
            'supports_function_calling': True,
            'max_tokens': 8192,
            'input_cost': 3e-06,
            'output_cost': 1.5e-05 },
        'claude-opus-4-1': {
            'model_id': 'claude-opus-4-1-20250805',
            'supports_vision': True,
            'supports_function_calling': True,
            'max_tokens': 8192,
            'input_cost': 1.5e-05,
            'output_cost': 7.5e-05 },
        'claude-3-5-sonnet': {
            'model_id': 'claude-3-5-sonnet-20241022',
            'supports_vision': True,
            'supports_function_calling': True,
            'max_tokens': 8192,
            'input_cost': 3e-06,
            'output_cost': 1.5e-05 },
        'claude-3-5-haiku': {
            'model_id': 'claude-3-5-haiku-20241022',
            'supports_vision': False,
            'supports_function_calling': True,
            'max_tokens': 8192,
            'input_cost': 1e-06,
            'output_cost': 5e-06 } }
    
    def __init__(self = None, models = None):
        '''
        Initialize config generator.
        
        Args:
            models: List of model names to include (default: all)
        '''
        pass
    # WARNING: Decompyle incomplete

    
    def generate_model_config(self = None, model_name = None):
        '''Generate configuration for a single model'''
        if model_name not in self.CLAUDE_MODELS:
            raise ValueError(f'''Unknown model: {model_name}''')
        model_info = None.CLAUDE_MODELS[model_name]
        return {
            'model_name': model_name,
            'litellm_params': {
                'model': model_info['model_id'],
                'api_base': 'https://api.anthropic.com',
                'custom_llm_provider': 'anthropic' },
            'model_info': {
                'supports_vision': model_info['supports_vision'],
                'supports_function_calling': model_info['supports_function_calling'],
                'max_tokens': model_info['max_tokens'],
                'input_cost_per_token': model_info['input_cost'],
                'output_cost_per_token': model_info['output_cost'] },
            'custom_auth_header': {
                'Authorization': 'Bearer {{env:CLAUDE_ACCESS_TOKEN}}',
                'anthropic-beta': 'oauth-2025-04-20' } }

    
    def generate_config(self = None, master_key = None, database_url = None, redis_url = (None, None, None, None), additional_settings = ('master_key', Optional[str], 'database_url', Optional[str], 'redis_url', Optional[str], 'additional_settings', Optional[Dict[(str, Any)]], 'return', Dict[(str, Any)])):
        '''
        Generate complete LiteLLM configuration.
        
        Args:
            master_key: Master API key for LiteLLM
            database_url: PostgreSQL URL for analytics
            redis_url: Redis URL for caching
            additional_settings: Extra settings to merge
            
        Returns:
            Complete configuration dictionary
        '''
        pass
    # WARNING: Decompyle incomplete

    
    def save_config(self = None, config = None, output_path = None, format = ('yaml',)):
        """
        Save configuration to file.
        
        Args:
            config: Configuration dictionary
            output_path: Output file path
            format: Output format ('yaml' or 'json')
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents = True, exist_ok = True)
    # WARNING: Decompyle incomplete

    
    def generate_docker_compose_env(self = None):
        '''Generate environment variables for Docker Compose'''
        return {
            'CLAUDE_ACCESS_TOKEN': '${CLAUDE_ACCESS_TOKEN}',
            'LITELLM_MASTER_KEY': '${LITELLM_MASTER_KEY:-sk-1234}',
            'DATABASE_URL': '${DATABASE_URL:-postgresql://litellm:password@postgres:5432/litellm}',
            'REDIS_URL': '${REDIS_URL:-redis://redis:6379}' }

    
    def generate_systemd_env(self = None):
        '''Generate environment file for systemd'''
        env_lines = [
            '# LiteLLM Environment Configuration',
            "CLAUDE_ACCESS_TOKEN_COMMAND='python /opt/claude-oauth/get_token.py'",
            'LITELLM_CONFIG_PATH=/etc/litellm/config.yaml',
            'LITELLM_PORT=4000',
            'LITELLM_LOG_LEVEL=INFO']
        return '\n'.join(env_lines)


if __name__ == '__main__':
    config_gen = LiteLLMConfig()
    config = config_gen.generate_config(master_key = 'sk-test-key', redis_url = 'redis://localhost:6379')
    config_gen.save_config(config, 'litellm_config.yaml', format = 'yaml')
    print('Configuration saved to litellm_config.yaml')
    print('\nSample configuration:')
    print(yaml.dump(config, default_flow_style = False, sort_keys = False))
    return None
