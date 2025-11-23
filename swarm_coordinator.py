import paramiko
import time
import json
from typing import Dict, Optional

def get_swarm_info_via_ssh(host: str, username: str = 'ubuntu', password: Optional[str] = None, max_retries: int = 20) -> Dict:
    """
    SSH into manager node and retrieve swarm info from /tmp/swarm_info.json
    
    Args:
        host: IP address of the manager node
        username: SSH username (default: ubuntu)
        password: SSH password
        max_retries: Maximum number of retry attempts
    
    Returns:
        Dict with vpn_ip, worker_token, and manager_token
    """
    print(f"Attempting to connect to {host} with user {username}")
    
    for attempt in range(max_retries):
        try:
            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect with increased timeout
            print(f"Attempt {attempt + 1}/{max_retries}: Connecting to {host}...")
            ssh.connect(host, username=username, password=password, timeout=30, banner_timeout=30)
            
            # Check if swarm_info.json exists
            stdin, stdout, stderr = ssh.exec_command('cat /tmp/swarm_info.json')
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if error or not output:
                print(f"Attempt {attempt + 1}/{max_retries}: Swarm info not ready yet (file not found or empty)")
                ssh.close()
                time.sleep(15)  # Wait 15 seconds before retry
                continue
            
            # Parse JSON
            swarm_info = json.loads(output)
            ssh.close()
            
            print(f"✅ Successfully retrieved swarm info from {host}")
            return swarm_info
            
        except paramiko.AuthenticationException as e:
            print(f"Attempt {attempt + 1}/{max_retries}: Authentication failed - instance may still be initializing")
            time.sleep(15)
        except Exception as e:
            print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            time.sleep(15)
    
    raise Exception(f"Failed to retrieve swarm info after {max_retries} attempts")


def prepare_worker_script(base_script: str, worker_token: str, manager_ip: str, telegram_token: str = None, telegram_chat_id: str = None) -> str:
    """
    Prepare worker startup script with actual values
    
    Args:
        base_script: Base worker script template
        worker_token: Docker Swarm worker token
        manager_ip: Manager Public IP address
        telegram_token: Telegram bot token for logging
        telegram_chat_id: Telegram chat ID for logging
    
    Returns:
        Complete worker startup script
    """
    script = base_script.replace('WORKER_TOKEN_PLACEHOLDER', worker_token)
    script = script.replace('MANAGER_IP_PLACEHOLDER', manager_ip)
    
    if telegram_token and telegram_chat_id:
        script = script.replace('TELEGRAM_BOT_TOKEN_PLACEHOLDER', telegram_token)
        script = script.replace('TELEGRAM_CHAT_ID_PLACEHOLDER', telegram_chat_id)
        
    return script


def prepare_manager_script(base_script: str, telegram_token: str = None, telegram_chat_id: str = None) -> str:
    """
    Prepare manager startup script
    
    Args:
        base_script: Base manager script template
        telegram_token: Telegram bot token for logging
        telegram_chat_id: Telegram chat ID for logging
    
    Returns:
        Complete manager startup script
    """
    script = base_script
    
    if telegram_token and telegram_chat_id:
        script = script.replace('TELEGRAM_BOT_TOKEN_PLACEHOLDER', telegram_token)
        script = script.replace('TELEGRAM_CHAT_ID_PLACEHOLDER', telegram_chat_id)
        
    return script
