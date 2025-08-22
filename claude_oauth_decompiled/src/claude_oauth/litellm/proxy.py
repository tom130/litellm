# Source Generated with Decompyle++
# File: proxy.cpython-312.pyc (Python 3.12)

'''
LiteLLM proxy server with Claude OAuth integration.
'''
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Any
from auth.token_manager import TokenManager
from config import LiteLLMConfig
logger = logging.getLogger(__name__)

class LiteLLMProxy:
    '''Manage LiteLLM proxy server with Claude OAuth'''
    
    def __init__(self = None, token_manager = None, config_path = None, port = (None, None, 4000, '0.0.0.0'), host = ('token_manager', Optional[TokenManager], 'config_path', Optional[str], 'port', int, 'host', str)):
        '''
        Initialize LiteLLM proxy.
        
        Args:
            token_manager: Token manager instance
            config_path: Path to LiteLLM config file
            port: Proxy server port
            host: Proxy server host
        '''
        pass
    # WARNING: Decompyle incomplete

    
    def generate_config(self = None):
        '''Generate LiteLLM configuration'''
        config_gen = LiteLLMConfig()
        return config_gen.generate_config(master_key = os.getenv('LITELLM_MASTER_KEY', 'sk-1234'), database_url = os.getenv('DATABASE_URL'), redis_url = os.getenv('REDIS_URL'))

    
    def update_token(self = None):
        '''Update access token and return it'''
        token = self.token_manager.get_access_token()
        os.environ['CLAUDE_ACCESS_TOKEN'] = token
        logger.info('Updated CLAUDE_ACCESS_TOKEN environment variable')
        return token

    
    def save_config(self = None, config = None):
        '''Save LiteLLM configuration to file'''
        import yaml
    # WARNING: Decompyle incomplete

    
    def start(self = None, detached = None):
        '''
        Start LiteLLM proxy server.
        
        Args:
            detached: Run in background
            
        Returns:
            Process object if detached, None otherwise
        '''
        self.update_token()
        self.save_config()
        cmd = [
            sys.executable,
            '-m',
            'litellm',
            '--config',
            str(self.config_path),
            '--host',
            self.host,
            '--port',
            str(self.port),
            '--detailed_debug']
        logger.info(f'''Starting LiteLLM proxy: {' '.join(cmd)}''')
    # WARNING: Decompyle incomplete

    
    def stop(self = None):
        '''Stop the proxy server'''
        if self.process:
            logger.info('Stopping LiteLLM proxy')
            self.process.terminate()
            self.process.wait(timeout = 5)
            self.process = None
            return None
        return None
    # WARNING: Decompyle incomplete

    
    async def run_with_token_refresh(self = None, refresh_interval = None):
        '''
        Run proxy with automatic token refresh.
        
        Args:
            refresh_interval: Token refresh interval in seconds
        '''
        pass
    # WARNING: Decompyle incomplete

    
    def health_check(self = None):
        '''Check if proxy is healthy'''
        import requests
        response = requests.get(f'''http://{self.host}:{self.port}/health''', timeout = 5)
        return response.status_code == 200
    # WARNING: Decompyle incomplete

    
    def get_models(self = None):
        '''Get available models from proxy'''
        import requests
        response = requests.get(f'''http://{self.host}:{self.port}/v1/models''', timeout = 5)
        response.raise_for_status()
        return response.json()
    # WARNING: Decompyle incomplete

    
    def test_completion(self = None, model = None):
        '''Test a completion request'''
        import requests
        response = requests.post(f'''http://{self.host}:{self.port}/v1/chat/completions''', json = {
            'model': model,
            'messages': [
                {
                    'role': 'user',
                    'content': "Say 'Hello, Claude OAuth!'" }],
            'max_tokens': 50 }, timeout = 30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    # WARNING: Decompyle incomplete


if __name__ == '__main__':
    logging.basicConfig(level = logging.INFO)
    proxy = LiteLLMProxy()
    print('Starting LiteLLM proxy...')
    process = proxy.start(detached = True)
    if process:
        print(f'''Proxy started with PID {process.pid}''')
        time.sleep(5)
        if proxy.health_check():
            print('Proxy is healthy')
            result = proxy.test_completion()
        proxy.stop()
        print('Proxy stopped')
        return None
    return None
