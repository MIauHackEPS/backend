import paramiko
import time
import json
from typing import Dict, Optional

def get_swarm_info_via_ssh(host: str, username: str = 'ubuntu', password: Optional[str] = None, max_retries: int = 10) -> Dict:
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
    for attempt in range(max_retries):
        try:
            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect
            ssh.connect(host, username=username, password=password, timeout=10)
            
            # Check if swarm_info.json exists
            stdin, stdout, stderr = ssh.exec_command('cat /tmp/swarm_info.json')
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if error or not output:
                print(f"Attempt {attempt + 1}/{max_retries}: Swarm info not ready yet...")
                ssh.close()
                time.sleep(10)  # Wait 10 seconds before retry
                continue
            
            # Parse JSON
            swarm_info = json.loads(output)
            ssh.close()
            
            return swarm_info
            
        except Exception as e:
            print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            time.sleep(10)
    
    raise Exception(f"Failed to retrieve swarm info after {max_retries} attempts")


def prepare_worker_script(base_script: str, tailscale_key: str, worker_token: str, manager_ip: str) -> str:
    """
    Prepare worker startup script with actual values
    
    Args:
        base_script: Base worker script template
        tailscale_key: Tailscale auth key
        worker_token: Docker Swarm worker token
        manager_ip: Manager VPN IP address
    
    Returns:
        Complete worker startup script
    """
    script = base_script.replace('TS_AUTHKEY_PLACEHOLDER', tailscale_key)
    script = script.replace('WORKER_TOKEN_PLACEHOLDER', worker_token)
    script = script.replace('MANAGER_IP_PLACEHOLDER', manager_ip)
    return script


def prepare_manager_script(base_script: str, tailscale_key: str) -> str:
    """
    Prepare manager startup script with Tailscale key
    
    Args:
        base_script: Base manager script template
        tailscale_key: Tailscale auth key
    
    Returns:
        Complete manager startup script
    """
    return base_script.replace('TS_AUTHKEY_PLACEHOLDER', tailscale_key)
