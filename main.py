import urllib.request
import urllib.parse
import argparse
import json
import os
from find_instance import find_instances
from create_instance import create_instance
from list_instances import list_instances
from delete_instance import delete_instance, find_and_delete_instance
from aws_instances import list_instances_aws, create_instance_aws, delete_instance_aws, start_instance_aws, stop_instance_aws
from aws_instances import find_instance_types_aws
from aws_instances import find_instances_aws
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import secrets
import string
from google.cloud import compute_v1
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
from swarm_coordinator import get_swarm_info_via_ssh, prepare_worker_script, prepare_manager_script

load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Tailscale Configuration
TAILSCALE_AUTH_KEY = os.environ.get('TAILSCALE_AUTH_KEY')

# Cache for instance types (TTL: 5 minutes)
_instance_types_cache = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

def _get_cache_key(provider: str, zone_or_region: str, cpus: int, ram: int) -> str:
    """Generate cache key for instance types"""
    return f"{provider}:{zone_or_region}:{cpus}:{ram}"

def _get_from_cache(cache_key: str):
    """Get cached result if not expired"""
    if cache_key in _instance_types_cache:
        cached_data, timestamp = _instance_types_cache[cache_key]
        if datetime.now() - timestamp < timedelta(seconds=CACHE_TTL_SECONDS):
            return cached_data
        else:
            # Expired, remove from cache
            del _instance_types_cache[cache_key]
    return None

def _set_cache(cache_key: str, data):
    """Store data in cache with timestamp"""
    _instance_types_cache[cache_key] = (data, datetime.now())

def log_to_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"Telegram logger not configured. Message: {message}")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": message}).encode()
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Failed to send Telegram log: {e}")

app = FastAPI()

# Default AWS region used when none provided
DEFAULT_REGION = 'us-west-2'

# Permitir CORS para llamadas desde Astro
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Startup Scripts ---
STARTUP_SCRIPTS = {
    "kubernetes": """
apt-get update
apt-get install -y curl
curl -sfL https://get.k3s.io | sh -
""",
    "docker-swarm": """
apt-get update
apt-get install -y docker.io docker-compose
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu
# Wait for docker to be ready
timeout 60s bash -c 'until docker info; do sleep 2; done'
docker swarm init || true
# Install Portainer for Swarm management UI
docker run -d -p 8000:8000 -p 9443:9443 --name portainer --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:latest
""",
    "docker-swarm-manager": """

set -x
export DEBIAN_FRONTEND=noninteractive

# Telegram logging function
log_telegram() {
    MSG="$1"
    curl -s -X POST https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage \
        -d chat_id={TELEGRAM_CHAT_ID} \
        -d text="🔹 [GCP-Manager] $MSG" >/dev/null || true
}

log_telegram "Starting initialization..."

# Flush firewall and allow all
iptables -F
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT
ufw disable || true

# Explicitly allow Swarm and Portainer ports
iptables -A INPUT -p tcp --dport 2377 -j ACCEPT
iptables -A INPUT -p tcp --dport 7946 -j ACCEPT
iptables -A INPUT -p udp --dport 7946 -j ACCEPT
iptables -A INPUT -p udp --dport 4789 -j ACCEPT
iptables -A INPUT -p tcp --dport 9443 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j ACCEPT

# Wait for apt lock
while fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do sleep 1 ; done
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 ; do sleep 1 ; done

log_telegram "Installing Docker and dependencies..."
apt-get update
apt-get install -y docker.io docker-compose curl jq

systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Get Public IP from metadata
PUBLIC_IP=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
log_telegram "Public IP detected: ${PUBLIC_IP}"

# Initialize Swarm with Public IP
log_telegram "Initializing Swarm on ${PUBLIC_IP}..."
docker swarm init --advertise-addr ${PUBLIC_IP} || true

# Wait for docker to be ready
timeout 60s bash -c 'until docker info; do sleep 2; done'



# Get tokens
WORKER_TOKEN=$(docker swarm join-token -q worker)
MANAGER_TOKEN=$(docker swarm join-token -q manager)

# Save tokens and Public IP to file
cat > /tmp/swarm_info.json <<EOF
{
  "vpn_ip": "${PUBLIC_IP}",
  "worker_token": "${WORKER_TOKEN}",
  "manager_token": "${MANAGER_TOKEN}"
}
EOF

# Install Portainer
docker run -d -p 8000:8000 -p 9443:9443 --name portainer --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data \
  portainer/portainer-ce:latest

# Wait for Portainer to be ready
log_telegram "Waiting for Portainer to start..."
timeout 60s bash -c 'until curl -k -s https://localhost:9443 >/dev/null; do sleep 2; done'

log_telegram "✅ EVERYTHING READY! Access Portainer at: https://${PUBLIC_IP}:9443"
echo "Swarm manager initialized. Public IP: ${PUBLIC_IP}"
""",
    "docker-swarm-worker": """
set -x
export DEBIAN_FRONTEND=noninteractive

# Telegram logging function
log_telegram() {
    MSG="$1"
    curl -s -X POST https://api.telegram.org/botTELEGRAM_BOT_TOKEN_PLACEHOLDER/sendMessage \
        -d chat_id=TELEGRAM_CHAT_ID_PLACEHOLDER \
        -d text="🔸 [AWS-Worker] $MSG" >/dev/null || true
}

log_telegram "Starting initialization..."

# Flush firewall
iptables -F
ufw disable || true

# Wait for apt lock
while fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do sleep 1 ; done
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 ; do sleep 1 ; done

log_telegram "Installing Docker and dependencies..."
apt-get update
apt-get install -y docker.io docker-compose curl

systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu



# Wait for docker to be ready
timeout 60s bash -c 'until docker info; do sleep 2; done'

log_telegram "Joining Swarm..."
# Join swarm (manager IP and token will be replaced)
docker swarm join --token WORKER_TOKEN_PLACEHOLDER MANAGER_IP_PLACEHOLDER:2377

log_telegram "Joined swarm successfully!"

echo "Joined swarm as worker"
""",
    "redis": """
apt-get update
apt-get install -y redis-server
systemctl enable redis-server
systemctl start redis-server
sed -i 's/bind 127.0.0.1 ::1/bind 0.0.0.0/' /etc/redis/redis.conf
systemctl restart redis-server
""",
    "portainer": """
apt-get update
apt-get install -y docker.io docker-compose
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu
# Wait for docker to be ready
timeout 60s bash -c 'until docker info; do sleep 2; done'
docker run -d -p 8000:8000 -p 9443:9443 --name portainer --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:latest
"""
}

SERVICE_INFO = {
    "kubernetes": {
        "ports": [6443],
        "protocol": "tcp",
        "instructions": "K3s is installing. Access via port 6443. Config at /etc/rancher/k3s/k3s.yaml"
    },
    "docker-swarm": {
        "ports": [2377, 7946, 4789, 9443, 8000],
        "protocol": "tcp/udp",
        "instructions": "Docker Swarm initialized. Portainer UI available at https://<IP>:9443"
    },
    "docker-swarm-manager": {
        "ports": [2377, 7946, 4789, 8000, 9443],
        "protocol": "tcp",
        "instructions": "Docker Swarm Manager (Public IP). Portainer at https://<IP>:9443"
    },
    "docker-swarm-worker": {
        "ports": [2377, 7946, 4789],
        "protocol": "tcp",
        "instructions": "Docker Swarm Worker. Connected to manager via Public IP."
    },
    "redis": {
        "ports": [6379],
        "protocol": "tcp",
        "instructions": "Redis server running on port 6379."
    },
    "portainer": {
        "ports": [9443, 8000],
        "protocol": "tcp",
        "instructions": "Portainer UI available at https://<IP>:9443"
    }
}

def load_credentials(credentials_file):
    with open(credentials_file, 'r') as f:
        return json.load(f)

def _set_credentials_and_load(credentials_path: str):
    if not credentials_path:
        raise ValueError("credentials path is required")
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
    with open(credentials_path, 'r') as f:
        return json.load(f)

def _load_aws_credentials_file(path: Optional[str] = None):
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'credentials_aws.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            return data or {}
    except Exception:
        return {}

# --- GCP Start/Stop Helpers ---
def start_instance_gcp(project_id, zone, instance_name):
    client = compute_v1.InstancesClient()
    op = client.start(project=project_id, zone=zone, instance=instance_name)
    return op

def stop_instance_gcp(project_id, zone, instance_name):
    client = compute_v1.InstancesClient()
    op = client.stop(project=project_id, zone=zone, instance=instance_name)
    return op

def _serialize_instances(instances, zone=None):
    out = []
    for inst in instances:
        item = {
            'name': getattr(inst, 'name', None),
            'status': getattr(inst, 'status', None),
            'machine_type': getattr(inst, 'machine_type', None).split('/')[-1] if getattr(inst, 'machine_type', None) else None,
            'creation_timestamp': getattr(inst, 'creation_timestamp', None),
            'zone': zone,
            'internal_ips': [],
            'external_ips': []
        }
        if getattr(inst, 'network_interfaces', None):
            for iface in inst.network_interfaces:
                if getattr(iface, 'network_i_p', None):
                    item['internal_ips'].append(iface.network_i_p)
                if getattr(iface, 'access_configs', None):
                    for ac in iface.access_configs:
                        ip = getattr(ac, 'nat_i_p', None) or getattr(ac, 'nat_ip', None)
                        if ip:
                            item['external_ips'].append(ip)
        out.append(item)
    return out

# --- Request Models ---
class FindRequest(BaseModel):
    credentials: str
    zone: str
    region: str
    cpus: int
    ram: int

class CreateRequest(BaseModel):
    credentials: Optional[str] = None
    zone: str
    name: str
    machine_type: str
    ssh_key: Optional[str] = None
    password: Optional[str] = None
    count: Optional[int] = 1
    image_project: Optional[str] = None
    image_family: Optional[str] = None
    image: Optional[str] = None
    cluster_type: Optional[str] = None

class ListRequest(BaseModel):
    credentials: Optional[str] = None
    zone: Optional[str] = None
    state: Optional[str] = None

class DeleteRequest(BaseModel):
    credentials: str
    name: str
    zone: Optional[str] = None

class AwsCreateRequest(BaseModel):
    region: str = "us-west-2"
    name: Optional[str] = None
    image_id: str = "ami-03c1f788292172a4e"
    instance_type: str
    password: Optional[str] = None
    key_name: Optional[str] = None
    security_group_ids: Optional[List[str]] = None
    subnet_id: Optional[str] = None
    min_count: Optional[int] = 1
    max_count: Optional[int] = 1
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    cluster_type: Optional[str] = None

class AwsDeleteRequest(BaseModel):
    region: Optional[str] = None
    instance_id: Optional[str] = None
    name: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None

class AwsFindRequest(BaseModel):
    region: Optional[str] = "us-west-2"
    name: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None

class AwsDebugListRequest(BaseModel):
    region: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None

class ActionRequest(BaseModel):
    provider: str # gcp or aws
    id: str # instance id or name
    zone: Optional[str] = None # for GCP
    region: Optional[str] = None # for AWS
    credentials: Optional[str] = None # path for GCP
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None

class AllCreateRequest(BaseModel):
    gcp: Optional[CreateRequest] = None
    aws: Optional[AwsCreateRequest] = None
    cluster_type: Optional[str] = None
    total_nodes: Optional[int] = None  # Total nodes to create, split evenly between GCP and AWS


class AllListRequest(BaseModel):
    gcp_credentials: Optional[str] = None
    gcp_zone: Optional[str] = None
    aws_region: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    state: Optional[str] = None

class AllDeleteRequest(BaseModel):
    gcp_credentials: Optional[str] = None
    gcp_name: Optional[str] = None
    gcp_zone: Optional[str] = None
    aws_region: Optional[str] = None
    aws_instance_id: Optional[str] = None
    aws_name: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None

class AllFindRequest(BaseModel):
    gcp_credentials: Optional[str] = None
    gcp_zone: Optional[str] = None
    gcp_region: Optional[str] = None
    gcp_cpus: Optional[int] = None
    gcp_ram: Optional[int] = None
    aws_region: Optional[str] = None
    aws_min_vcpus: Optional[int] = None
    aws_min_memory_gb: Optional[int] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_session_token: Optional[str] = None

# --- Endpoints ---

@app.post('/find')
def api_find(req: FindRequest):
    creds = _set_credentials_and_load(req.credentials)
    try:
        results = find_instances(
            project_id=creds['project_id'],
            zone=req.zone,
            region=req.region,
            num_cpus=req.cpus,
            num_ram_gb=req.ram
        )
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/create')
def api_create(req: CreateRequest):
    if not req.credentials:
        raise HTTPException(status_code=400, detail="credentials is required for /create endpoint")
    creds = _set_credentials_and_load(req.credentials)
    log_to_telegram(f"🚀 Creating GCP instance: {req.name} ({req.cluster_type or 'base'})")
    try:
        result = create_instance(
            project_id=creds['project_id'],
            zone=req.zone,
            instance_name=req.name,
            machine_type=req.machine_type,
            ssh_key=req.ssh_key,
            password=getattr(req, 'password', None),
            count=getattr(req, 'count', 1),
            image_project=getattr(req, 'image_project', None),
            image_family=getattr(req, 'image_family', None),
            image=getattr(req, 'image', None),
            startup_script=STARTUP_SCRIPTS.get(req.cluster_type) if req.cluster_type else None
        )
        if req.cluster_type and req.cluster_type in SERVICE_INFO:
            if isinstance(result, dict) and "created" in result:
                 # Multiple instances
                 for item in result["created"]:
                     item["service_info"] = SERVICE_INFO[req.cluster_type]
            elif isinstance(result, dict):
                 # Single instance
                 result["service_info"] = SERVICE_INFO[req.cluster_type]
        
        # Debug: print result structure
        print(f"DEBUG GCP Result: {result}")
        
        # Enhanced Telegram logging
        ports = SERVICE_INFO.get(req.cluster_type, {}).get('ports', []) if req.cluster_type else []
        ports_str = ', '.join(map(str, ports)) if ports else 'N/A'
        
        if isinstance(result, dict):
            # Check if it's a multiple instances response
            if "created" in result and isinstance(result["created"], list):
                # Multiple instances
                for item in result["created"]:
                    ip = item.get('public_ip', 'N/A')
                    password = item.get('password', 'N/A')
                    username = item.get('username', 'ubuntu')
                    name = item.get('name', req.name)
                    
                    msg = f"✅ GCP Instance Created!\n"
                    msg += f"Name: {name}\n"
                    msg += f"IP: {ip}\n"
                    msg += f"User: {username}\n"
                    msg += f"Password: {password}\n"
                    msg += f"Cluster: {req.cluster_type or 'base'}\n"
                    msg += f"Ports: {ports_str}"
                    log_to_telegram(msg)
            else:
                # Single instance
                ip = result.get('public_ip', 'N/A')
                password = result.get('password', 'N/A')
                username = result.get('username', 'ubuntu')
                
                msg = f"✅ GCP Instance Created!\n"
                msg += f"Name: {req.name}\n"
                msg += f"IP: {ip}\n"
                msg += f"User: {username}\n"
                msg += f"Password: {password}\n"
                msg += f"Cluster: {req.cluster_type or 'base'}\n"
                msg += f"Ports: {ports_str}"
                log_to_telegram(msg)
        
        return result
    except Exception as e:
        log_to_telegram(f"❌ Error creating GCP instance {req.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/list')
def api_list(req: ListRequest):
    credentials_path = req.credentials or os.path.join(os.path.dirname(__file__), 'credentials.json')
    creds = _set_credentials_and_load(credentials_path)
    try:
        instances = list_instances(
            project_id=creds['project_id'],
            zone=req.zone,
            state=req.state
        )
        serialized = _serialize_instances(instances, zone=req.zone)
        if not serialized:
            return {"success": True, "count": 0, "instances": [], "message": "No se encontraron instancias"}
        return {"success": True, "count": len(serialized), "instances": serialized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/list')
def api_list_get(zone: Optional[str] = None, credentials_path: Optional[str] = None, state: Optional[str] = None):
    credentials_path = credentials_path or os.path.join(os.path.dirname(__file__), 'credentials.json')
    creds = _set_credentials_and_load(credentials_path)
    try:
        instances = list_instances(
            project_id=creds['project_id'],
            zone=zone,
            state=state
        )
        serialized = _serialize_instances(instances, zone=zone)
        if not serialized:
            return {"success": True, "count": 0, "instances": [], "message": "No se encontraron instancias"}
        return {"success": True, "count": len(serialized), "instances": serialized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/delete')
def api_delete(req: DeleteRequest):
    creds = _set_credentials_and_load(req.credentials)
    log_to_telegram(f"Deleting GCP instance: {req.name}")
    try:
        if req.zone:
            success = delete_instance(
                project_id=creds['project_id'],
                zone=req.zone,
                instance_name=req.name
            )
        else:
            success = find_and_delete_instance(
                project_id=creds['project_id'],
                instance_name=req.name
            )
        log_to_telegram(f"GCP instance deleted: {req.name} (Success: {success})")
        return {"success": bool(success)}
    except Exception as e:
        log_to_telegram(f"Error deleting GCP instance {req.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/aws/list')
def api_aws_list_get(region: Optional[str] = None, credentials_path: Optional[str] = None, state: Optional[str] = None):
    credentials_path = credentials_path or os.path.join(os.path.dirname(__file__), 'credentials_aws.json')
    creds = _load_aws_credentials_file(credentials_path)
    if not (creds.get('aws_access_key_id') or creds.get('aws_access_key') or creds.get('aws_secret_access_key') or creds.get('aws_secret_key')):
        raise HTTPException(status_code=400, detail="No AWS credentials found.")
    try:
        instances = list_instances_aws(region_name=region or DEFAULT_REGION,
                                       aws_access_key=creds.get('aws_access_key_id'),
                                       aws_secret_key=creds.get('aws_secret_access_key'),
                                       aws_session_token=creds.get('aws_session_token'),
                                       state=state)
        if not instances:
            return {"success": True, "count": 0, "instances": [], "message": "No se encontraron instancias con el prefijo t3- activas"}
        return {"success": True, "count": len(instances), "instances": instances}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/aws/list_debug')
def api_aws_list_debug(req: AwsDebugListRequest):
    try:
        aws_creds = {}
        if req.aws_access_key or req.aws_secret_key or req.aws_session_token:
            aws_creds = {
                'aws_access_key': req.aws_access_key,
                'aws_secret_key': req.aws_secret_key,
                'aws_session_token': req.aws_session_token,
                'region': req.region
            }
        else:
            aws_creds = _load_aws_credentials_file()
        from aws_instances import list_instances_aws_all
        instances = list_instances_aws_all(
            region_name=req.region or aws_creds.get('region'),
            aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
            aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
            aws_session_token=aws_creds.get('aws_session_token')
        )
        if not instances:
            return {"success": True, "count": 0, "instances": [], "message": "No se encontraron instancias (debug)"}
        return {"success": True, "count": len(instances), "instances": instances}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/aws/find')
def api_aws_find(req: AwsFindRequest):
    try:
        aws_creds = {}
        if req.aws_access_key or req.aws_secret_key or req.aws_session_token:
            aws_creds = {
                'aws_access_key': req.aws_access_key,
                'aws_secret_key': req.aws_secret_key,
                'aws_session_token': req.aws_session_token,
                'region': req.region
            }
        else:
            aws_creds = _load_aws_credentials_file()
        instances = find_instances_aws(
            name=req.name,
            region_name=req.region or aws_creds.get('region') or 'us-west-2',
            aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
            aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
            aws_session_token=aws_creds.get('aws_session_token')
        )
        if not instances:
            return {"success": True, "count": 0, "instances": [], "message": "No se encontraron instancias t3-"}
        return {"success": True, "count": len(instances), "instances": instances}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/instance-types/gcp')
def api_gcp_instance_types(zone: Optional[str] = None, credentials: Optional[str] = None, cpus: Optional[int] = None, ram_gb: Optional[int] = None, region: Optional[str] = None):
    if not zone:
        raise HTTPException(status_code=400, detail="zone is required")
    
    # Check cache first
    cache_key = _get_cache_key('gcp', zone, int(cpus or 1), int(ram_gb or 1))
    cached_result = _get_from_cache(cache_key)
    if cached_result is not None:
        return cached_result
    
    credentials_path = credentials or os.path.join(os.path.dirname(__file__), 'credentials.json')
    creds = _set_credentials_and_load(credentials_path)
    try:
        results = find_instances(project_id=creds['project_id'], zone=zone, region=region or '', num_cpus=int(cpus or 1), num_ram_gb=int(ram_gb or 1))
        response = {"success": True, "count": len(results), "instance_types": results}
        
        # Cache the result
        _set_cache(cache_key, response)
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/instance-types/aws')
def api_aws_instance_types(region: Optional[str] = None, min_vcpus: Optional[int] = None, min_memory_gb: Optional[float] = None, aws_access_key: Optional[str] = None, aws_secret_key: Optional[str] = None, aws_session_token: Optional[str] = None):
    # Check cache first
    region_name = region or 'us-west-2'
    cache_key = _get_cache_key('aws', region_name, int(min_vcpus or 1), int(min_memory_gb or 1))
    cached_result = _get_from_cache(cache_key)
    if cached_result is not None:
        return cached_result
    
    try:
        aws_creds = _load_aws_credentials_file()
        aws_access = aws_access_key or aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key')
        aws_secret = aws_secret_key or aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key')
        aws_token = aws_session_token or aws_creds.get('aws_session_token')
        results = find_instance_types_aws(region_name=region_name, min_vcpus=int(min_vcpus or 1), min_memory_gb=float(min_memory_gb or 1.0), aws_access_key=aws_access, aws_secret_key=aws_secret, aws_session_token=aws_token)
        response = {"success": True, "count": len(results), "instance_types": results}
        
        # Cache the result
        _set_cache(cache_key, response)
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/aws/create')
def api_aws_create(req: AwsCreateRequest):
    log_to_telegram(f"🚀 Creating AWS instance: {req.name} ({req.cluster_type or 'base'})")
    try:
        aws_creds = {}
        if req.aws_access_key or req.aws_secret_key or req.aws_session_token:
            aws_creds = {
                'aws_access_key': req.aws_access_key,
                'aws_secret_key': req.aws_secret_key,
                'aws_session_token': req.aws_session_token,
                'region': req.region
            }
        else:
            aws_creds = _load_aws_credentials_file()
        
        script = STARTUP_SCRIPTS.get(req.cluster_type) if req.cluster_type else None

        created = create_instance_aws(
            region_name=req.region or aws_creds.get('region') or 'us-west-2',
            image_id=req.image_id,
            instance_type=req.instance_type,
            password=getattr(req, 'password', None),
            name=req.name,
            key_name=req.key_name,
            security_group_ids=req.security_group_ids,
            subnet_id=req.subnet_id,
            min_count=req.min_count,
            max_count=req.max_count,
            aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
            aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
            aws_session_token=aws_creds.get('aws_session_token'),
            user_data_script=script
        )

        response = {"success": True, "created": created}
        if req.cluster_type and req.cluster_type in SERVICE_INFO:
            for item in created:
                item["service_info"] = SERVICE_INFO[req.cluster_type]
        
        # Enhanced Telegram logging
        ports = SERVICE_INFO.get(req.cluster_type, {}).get('ports', []) if req.cluster_type else []
        ports_str = ', '.join(map(str, ports)) if ports else 'N/A'
        
        for instance in created:
            ip = instance.get('PublicIpAddress', 'N/A')
            password = instance.get('Password', 'N/A')
            username = instance.get('username', 'ubuntu')
            instance_id = instance.get('InstanceId', 'N/A')
            
            msg = f"✅ AWS Instance Created!\n"
            msg += f"ID: {instance_id}\n"
            msg += f"IP: {ip}\n"
            msg += f"User: {username}\n"
            msg += f"Password: {password}\n"
            msg += f"Cluster: {req.cluster_type or 'base'}\n"
            msg += f"Ports: {ports_str}"
            log_to_telegram(msg)
        
        return response
    except Exception as e:
        log_to_telegram(f"❌ Error creating AWS instance {req.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/aws/delete')
def api_aws_delete(req: AwsDeleteRequest):
    log_to_telegram(f"Deleting AWS instance: {req.instance_id or req.name}")
    try:
        aws_creds = {}
        if req.aws_access_key or req.aws_secret_key or req.aws_session_token:
            aws_creds = {
                'aws_access_key': req.aws_access_key,
                'aws_secret_key': req.aws_secret_key,
                'aws_session_token': req.aws_session_token,
                'region': req.region
            }
        else:
            aws_creds = _load_aws_credentials_file()
        result = delete_instance_aws(
            instance_id=req.instance_id,
            name=req.name,
            region_name=req.region or aws_creds.get('region') or 'us-west-2',
            aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
            aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
            aws_session_token=aws_creds.get('aws_session_token')
        )
        log_to_telegram(f"AWS instance deleted: {req.instance_id or req.name} (Result: {result})")
        return {"success": True, "result": result}
    except Exception as e:
        log_to_telegram(f"Error deleting AWS instance {req.instance_id or req.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/all/create')
def api_all_create(req: AllCreateRequest):
    log_to_telegram(f"🚀 Starting hybrid creation. Cluster: {req.cluster_type or 'base'}")
    results = {'gcp': None, 'aws': None}
    errors = {'gcp': None, 'aws': None}
    
    # Calculate node distribution if total_nodes is specified
    if req.total_nodes and req.total_nodes > 0:
        gcp_count = req.total_nodes // 2
        aws_count = req.total_nodes - gcp_count
        
        # Override count in gcp and aws configs
        if req.gcp:
            req.gcp.count = gcp_count
        if req.aws:
            req.aws.min_count = aws_count
            req.aws.max_count = aws_count
        
        log_to_telegram(f"📊 Node distribution: {gcp_count} GCP + {aws_count} AWS = {req.total_nodes} total")
    
    # Special handling for docker-swarm-manager (Public IP cluster)
    if req.cluster_type in ["docker-swarm-manager", "docker-swarm"]:
        log_to_telegram(f"🔧 Creating Public IP-based Docker Swarm cluster")
        
        # Step 1: Create manager (first GCP node)
        if req.gcp:
            try:
                credentials_path = req.gcp.credentials or os.path.join(os.path.dirname(__file__), 'credentials.json')
                creds = _set_credentials_and_load(credentials_path)
                
                # Prepare manager script with Telegram logging
                manager_script = prepare_manager_script(
                    STARTUP_SCRIPTS["docker-swarm-manager"],
                    telegram_token=TELEGRAM_BOT_TOKEN,
                    telegram_chat_id=TELEGRAM_CHAT_ID
                )
                
                log_to_telegram(f"📍 Creating Swarm manager on GCP: {req.gcp.name}")
                
                manager_result = create_instance(
                    project_id=creds['project_id'],
                    zone=req.gcp.zone,
                    instance_name=req.gcp.name,
                    machine_type=req.gcp.machine_type,
                    ssh_key=req.gcp.ssh_key,
                    password=getattr(req.gcp, 'password', None),
                    count=1,  # Only 1 manager
                    startup_script=manager_script
                )
                
                results['gcp'] = manager_result
                manager_ip = manager_result.get('public_ip')
                manager_password = manager_result.get('password')
                
                log_to_telegram(f"⏳ Waiting for manager to initialize Swarm (this may take 2-3 minutes)...")
                
                # Step 2: Wait and retrieve swarm info via SSH
                try:
                    swarm_info = get_swarm_info_via_ssh(manager_ip, password=manager_password, max_retries=15)
                    # Use Public IP for workers to join
                    manager_public_ip = manager_ip
                    worker_token = swarm_info['worker_token']
                    
                    log_to_telegram(f"✅ Manager ready! Public IP: {manager_public_ip}")
                    
                    # Step 2.5: Create remaining GCP workers if count > 1
                    if req.gcp and req.gcp.count > 1:
                        remaining_gcp = req.gcp.count - 1
                        log_to_telegram(f"📍 Creating {remaining_gcp} additional Swarm workers on GCP")
                        
                        # Prepare worker script
                        worker_script = prepare_worker_script(
                            STARTUP_SCRIPTS["docker-swarm-worker"],
                            worker_token,
                            manager_public_ip,
                            telegram_token=TELEGRAM_BOT_TOKEN,
                            telegram_chat_id=TELEGRAM_CHAT_ID
                        )
                        
                        gcp_workers = create_instance(
                            project_id=creds['project_id'],
                            zone=req.gcp.zone,
                            instance_name=f"{req.gcp.name}-worker",
                            machine_type=req.gcp.machine_type,
                            ssh_key=req.gcp.ssh_key,
                            password=getattr(req.gcp, 'password', None),
                            count=remaining_gcp,
                            startup_script=worker_script
                        )
                        
                        # Merge results
                        if isinstance(results['gcp'], dict) and 'created' in results['gcp']:
                            if isinstance(gcp_workers, dict) and 'created' in gcp_workers:
                                results['gcp']['created'].extend(gcp_workers['created'])
                        
                    # Step 3: Create workers on AWS
                    if req.aws and req.aws.min_count > 0:
                        aws_creds = {}
                        if getattr(req.aws, 'aws_access_key', None) or getattr(req.aws, 'aws_secret_key', None):
                            aws_creds = {
                                'aws_access_key': getattr(req.aws, 'aws_access_key', None),
                                'aws_secret_key': getattr(req.aws, 'aws_secret_key', None),
                                'aws_session_token': getattr(req.aws, 'aws_session_token', None),
                                'region': req.aws.region
                            }
                        else:
                            aws_creds = _load_aws_credentials_file()
                        
                        # Prepare worker script
                        worker_script = prepare_worker_script(
                            STARTUP_SCRIPTS["docker-swarm-worker"],
                            worker_token,
                            manager_public_ip,
                            telegram_token=TELEGRAM_BOT_TOKEN,
                            telegram_chat_id=TELEGRAM_CHAT_ID
                        )
                        
                        log_to_telegram(f"📍 Creating {req.aws.min_count} Swarm workers on AWS")
                        
                        workers = create_instance_aws(
                            region_name=req.aws.region or aws_creds.get('region') or 'us-west-2',
                            image_id=getattr(req.aws, 'image_id', None) or 'ami-03c1f788292172a4e',
                            instance_type=getattr(req.aws, 'instance_type', None) or 't3.micro',
                            password=getattr(req.aws, 'password', None),
                            name=getattr(req.aws, 'name', None),
                            key_name=req.aws.key_name,
                            security_group_ids=req.aws.security_group_ids,
                            subnet_id=req.aws.subnet_id,
                            min_count=req.aws.min_count,
                            max_count=req.aws.max_count,
                            aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
                            aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
                            aws_session_token=aws_creds.get('aws_session_token'),
                            user_data_script=worker_script
                        )
                        
                        results['aws'] = {'success': True, 'created': workers}
                        log_to_telegram(f"✅ Swarm cluster created! Manager: {manager_public_ip}, Workers: {len(workers)}")
                    
                except Exception as e:
                    errors['gcp'] = f"Failed to retrieve swarm info: {e}"
                    log_to_telegram(f"❌ Failed to get swarm info: {e}")
                    
            except Exception as e:
                errors['gcp'] = str(e)
                results['gcp'] = {'success': False}
                log_to_telegram(f"❌ GCP manager creation failed: {e}")
        
        return {"results": results, "errors": errors}
    
    # Normal hybrid creation (non-Swarm)
    # GCP
    if req.gcp:
        try:
            credentials_path = req.gcp.credentials or os.path.join(os.path.dirname(__file__), 'credentials.json')
            creds = _set_credentials_and_load(credentials_path)
            gcp_result = create_instance(
                project_id=creds['project_id'],
                zone=req.gcp.zone,
                instance_name=req.gcp.name,
                machine_type=req.gcp.machine_type,
                ssh_key=req.gcp.ssh_key,
                password=getattr(req.gcp, 'password', None),
                count=getattr(req.gcp, 'count', 1),
                startup_script=STARTUP_SCRIPTS.get(req.cluster_type) if req.cluster_type else None
            )
            results['gcp'] = gcp_result
            if req.cluster_type and req.cluster_type in SERVICE_INFO:
                if isinstance(gcp_result, dict) and "created" in gcp_result:
                    for item in gcp_result["created"]:
                        item["service_info"] = SERVICE_INFO[req.cluster_type]
                elif isinstance(gcp_result, dict):
                    gcp_result["service_info"] = SERVICE_INFO[req.cluster_type]
            
            # Enhanced Telegram logging for GCP
            ports = SERVICE_INFO.get(req.cluster_type, {}).get('ports', []) if req.cluster_type else []
            ports_str = ', '.join(map(str, ports)) if ports else 'N/A'
            
            if isinstance(gcp_result, dict):
                # Check if it's a multiple instances response
                if "created" in gcp_result and isinstance(gcp_result["created"], list):
                    # Multiple instances
                    for item in gcp_result["created"]:
                        ip = item.get('public_ip', 'N/A')
                        password = item.get('password', 'N/A')
                        username = item.get('username', 'ubuntu')
                        name = item.get('name', req.gcp.name)
                        
                        msg = f"✅ GCP Instance Created!\n"
                        msg += f"Name: {name}\n"
                        msg += f"IP: {ip}\n"
                        msg += f"User: {username}\n"
                        msg += f"Password: {password}\n"
                        msg += f"Cluster: {req.cluster_type or 'base'}\n"
                        msg += f"Ports: {ports_str}"
                        log_to_telegram(msg)
                else:
                    # Single instance
                    ip = gcp_result.get('public_ip', 'N/A')
                    password = gcp_result.get('password', 'N/A')
                    username = gcp_result.get('username', 'ubuntu')
                    
                    msg = f"✅ GCP Instance Created!\n"
                    msg += f"Name: {req.gcp.name}\n"
                    msg += f"IP: {ip}\n"
                    msg += f"User: {username}\n"
                    msg += f"Password: {password}\n"
                    msg += f"Cluster: {req.cluster_type or 'base'}\n"
                    msg += f"Ports: {ports_str}"
                    log_to_telegram(msg)
        except Exception as e:
            errors['gcp'] = str(e)
            results['gcp'] = {'success': False}
            log_to_telegram(f"❌ GCP creation failed: {e}")

    # AWS
    if req.aws:
        try:
            aws_creds = {}
            if getattr(req.aws, 'aws_access_key', None) or getattr(req.aws, 'aws_secret_key', None):
                aws_creds = {
                    'aws_access_key': getattr(req.aws, 'aws_access_key', None),
                    'aws_secret_key': getattr(req.aws, 'aws_secret_key', None),
                    'aws_session_token': getattr(req.aws, 'aws_session_token', None),
                    'region': req.aws.region
                }
            else:
                aws_creds = _load_aws_credentials_file()

            script = STARTUP_SCRIPTS.get(req.cluster_type) if req.cluster_type else None

            ids = create_instance_aws(
                region_name=req.aws.region or aws_creds.get('region') or 'us-west-2',
                image_id=getattr(req.aws, 'image_id', None) or 'ami-03c1f788292172a4e',
                instance_type=getattr(req.aws, 'instance_type', None) or 't3.micro',
                password=getattr(req.aws, 'password', None),
                name=getattr(req.aws, 'name', None),
                key_name=req.aws.key_name,
                security_group_ids=req.aws.security_group_ids,
                subnet_id=req.aws.subnet_id,
                min_count=req.aws.min_count,
                max_count=req.aws.max_count,
                aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
                aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
                aws_session_token=aws_creds.get('aws_session_token'),
                user_data_script=script
            )
            results['aws'] = {'success': True, 'created': ids}
            if req.cluster_type and req.cluster_type in SERVICE_INFO:
                for item in ids:
                    item["service_info"] = SERVICE_INFO[req.cluster_type]
            
            # Enhanced Telegram logging for AWS
            ports = SERVICE_INFO.get(req.cluster_type, {}).get('ports', []) if req.cluster_type else []
            ports_str = ', '.join(map(str, ports)) if ports else 'N/A'
            
            for instance in ids:
                ip = instance.get('PublicIpAddress', 'N/A')
                password = instance.get('Password', 'N/A')
                username = instance.get('username', 'ubuntu')
                instance_id = instance.get('InstanceId', 'N/A')
                
                msg = f"✅ AWS Instance Created!\n"
                msg += f"ID: {instance_id}\n"
                msg += f"IP: {ip}\n"
                msg += f"User: {username}\n"
                msg += f"Password: {password}\n"
                msg += f"Cluster: {req.cluster_type or 'base'}\n"
                msg += f"Ports: {ports_str}"
                log_to_telegram(msg)
        except Exception as e:
            errors['aws'] = str(e)
            results['aws'] = {'success': False}
            log_to_telegram(f"❌ AWS creation failed: {e}")

    return {"results": results, "errors": errors}

@app.post('/all/list')
def api_all_list(req: AllListRequest):
    out = {'gcp': None, 'aws': None, 'errors': {}}
    # GCP list
    try:
        credentials_path = req.gcp_credentials or os.path.join(os.path.dirname(__file__), 'credentials.json')
        creds = _set_credentials_and_load(credentials_path)
        insts = list_instances(project_id=creds['project_id'], zone=req.gcp_zone, state=req.state)
        out['gcp'] = _serialize_instances(insts, zone=req.gcp_zone)
    except Exception as e:
        out['errors']['gcp'] = str(e)
    # AWS list
    try:
        if req.aws_access_key or req.aws_secret_key or req.aws_session_token:
            aws_access_key = req.aws_access_key
            aws_secret_key = req.aws_secret_key
            aws_session_token = req.aws_session_token
            aws_region = req.aws_region or 'us-west-2'
        else:
            aws_creds = _load_aws_credentials_file()
            aws_access_key = aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key')
            aws_secret_key = aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key')
            aws_session_token = aws_creds.get('aws_session_token')
            aws_region = req.aws_region or aws_creds.get('region') or 'us-west-2'
        aws_insts = list_instances_aws(region_name=aws_region,
                                       aws_access_key=aws_access_key,
                                       aws_secret_key=aws_secret_key,
                                       aws_session_token=aws_session_token)
        out['aws'] = aws_insts
    except Exception as e:
        out['errors']['aws'] = str(e)
    
    if not out.get('gcp'):
        out['gcp'] = []
        out['errors'].setdefault('gcp', None)
        out.setdefault('message_gcp', 'No se encontraron instancias en GCP')
    if not out.get('aws'):
        out['aws'] = []
        out['errors'].setdefault('aws', None)
        out.setdefault('message_aws', 'No se encontraron instancias en AWS')
    return out

@app.post('/all/delete')
def api_all_delete(req: AllDeleteRequest):
    log_to_telegram("Starting hybrid deletion")
    results = {'gcp': None, 'aws': None}
    errors = {'gcp': None, 'aws': None}
    # GCP delete
    try:
        if req.gcp_name:
            credentials_path = req.gcp_credentials or os.path.join(os.path.dirname(__file__), 'credentials.json')
            creds = _set_credentials_and_load(credentials_path)
            if req.gcp_zone:
                ok = delete_instance(project_id=creds['project_id'], zone=req.gcp_zone, instance_name=req.gcp_name)
            else:
                ok = find_and_delete_instance(project_id=creds['project_id'], instance_name=req.gcp_name)
            results['gcp'] = {'success': bool(ok)}
            log_to_telegram(f"Hybrid GCP delete: {req.gcp_name} (Success: {ok})")
    except Exception as e:
        errors['gcp'] = str(e)
        results['gcp'] = {'success': False}
        log_to_telegram(f"Hybrid GCP delete error: {e}")
    # AWS delete
    try:
        if req.aws_access_key or req.aws_secret_key or req.aws_session_token:
            aws_access_key = req.aws_access_key
            aws_secret_key = req.aws_secret_key
            aws_session_token = req.aws_session_token
            aws_region = req.aws_region or 'us-west-2'
        else:
            aws_creds = _load_aws_credentials_file()
            aws_access_key = aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key')
            aws_secret_key = aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key')
            aws_session_token = aws_creds.get('aws_session_token')
            aws_region = req.aws_region or aws_creds.get('region') or 'us-west-2'
        res = delete_instance_aws(instance_id=req.aws_instance_id, name=req.aws_name, region_name=aws_region,
                                  aws_access_key=aws_access_key, aws_secret_key=aws_secret_key, aws_session_token=aws_session_token)
        results['aws'] = res
        log_to_telegram(f"Hybrid AWS delete: {req.aws_instance_id or req.aws_name} (Result: {res})")
    except Exception as e:
        errors['aws'] = str(e)
        results['aws'] = {'success': False}
        log_to_telegram(f"Hybrid AWS delete error: {e}")
    return {"results": results, "errors": errors}

@app.post('/all/find')
def api_all_find(req: AllFindRequest):
    results = {'gcp': None, 'aws': None}
    errors = {'gcp': None, 'aws': None}
    # GCP find
    try:
        if req.gcp_cpus and req.gcp_ram and req.gcp_zone:
            credentials_path = req.gcp_credentials or os.path.join(os.path.dirname(__file__), 'credentials.json')
            creds = _set_credentials_and_load(credentials_path)
            gcp_results = find_instances(project_id=creds['project_id'], zone=req.gcp_zone, region=req.gcp_region or '', num_cpus=req.gcp_cpus, num_ram_gb=req.gcp_ram)
            results['gcp'] = gcp_results
        else:
            results['gcp'] = []
    except Exception as e:
        errors['gcp'] = str(e)
    # AWS find
    try:
        if req.aws_min_vcpus and req.aws_min_memory_gb:
            if req.aws_access_key or req.aws_secret_key or req.aws_session_token:
                aws_access_key = req.aws_access_key
                aws_secret_key = req.aws_secret_key
                aws_session_token = req.aws_session_token
                aws_region = req.aws_region
            else:
                aws_creds = _load_aws_credentials_file()
                aws_access_key = aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key')
                aws_secret_key = aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key')
                aws_session_token = aws_creds.get('aws_session_token')
                aws_region = req.aws_region or aws_creds.get('region')
            aws_results = find_instance_types_aws(region_name=aws_region, min_vcpus=req.aws_min_vcpus, min_memory_gb=req.aws_min_memory_gb,
                                                 aws_access_key=aws_access_key, aws_secret_key=aws_secret_key, aws_session_token=aws_session_token)
            results['aws'] = aws_results
        else:
            results['aws'] = []
    except Exception as e:
        errors['aws'] = str(e)
    return {"results": results, "errors": errors}

@app.post('/action/start')
def api_action_start(req: ActionRequest):
    log_to_telegram(f"Starting instance: {req.id} ({req.provider})")
    try:
        if req.provider == 'gcp':
            creds = _set_credentials_and_load(req.credentials or './credentials.json')
            start_instance_gcp(creds['project_id'], req.zone, req.id)
            log_to_telegram(f"GCP instance started: {req.id}")
            return {"success": True}
        elif req.provider == 'aws':
            aws_creds = {}
            if req.aws_access_key:
                aws_creds = {'aws_access_key': req.aws_access_key, 'aws_secret_key': req.aws_secret_key, 'aws_session_token': req.aws_session_token}
            else:
                aws_creds = _load_aws_credentials_file()
            
            start_instance_aws(req.id, region_name=req.region, 
                               aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
                               aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
                               aws_session_token=aws_creds.get('aws_session_token'))
            log_to_telegram(f"AWS instance started: {req.id}")
            return {"success": True}
    except Exception as e:
        log_to_telegram(f"Error starting instance {req.id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/action/stop')
def api_action_stop(req: ActionRequest):
    log_to_telegram(f"Stopping instance: {req.id} ({req.provider})")
    try:
        if req.provider == 'gcp':
            if not req.zone:
                raise HTTPException(status_code=400, detail="Zone is required for GCP stop action")
            creds = _set_credentials_and_load(req.credentials or './credentials.json')
            stop_instance_gcp(creds['project_id'], req.zone, req.id)
            log_to_telegram(f"GCP instance stopped: {req.id}")
            return {"success": True}
        elif req.provider == 'aws':
            aws_creds = {}
            if req.aws_access_key:
                aws_creds = {'aws_access_key': req.aws_access_key, 'aws_secret_key': req.aws_secret_key, 'aws_session_token': req.aws_session_token}
            else:
                aws_creds = _load_aws_credentials_file()
            
            stop_instance_aws(req.id, region_name=req.region, 
                               aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
                               aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
                               aws_session_token=aws_creds.get('aws_session_token'))
            log_to_telegram(f"AWS instance stopped: {req.id}")
            return {"success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        log_to_telegram(f"Error stopping instance {req.id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/telegram/webhook')
async def telegram_webhook(request: dict):
    """Handle Telegram bot commands"""
    try:
        # Extract message info
        message = request.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        
        if not chat_id or not text:
            return {"ok": True}
        
        # Handle commands
        if text == '/start':
            response_text = "👋 Welcome to Cloud Instance Manager Bot!\n\nCommands:\n/list - Show all running instances"
            _send_telegram_message(chat_id, response_text)
        
        elif text == '/list':
            # Get GCP instances
            gcp_instances = []
            aws_instances = []
            
            try:
                credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
                creds = _set_credentials_and_load(credentials_path)
                gcp_instances = list_instances(project_id=creds['project_id'])
            except Exception as e:
                print(f"Error listing GCP: {e}")
            
            try:
                aws_creds = _load_aws_credentials_file()
                aws_instances = list_instances_aws(
                    region_name=aws_creds.get('region', 'us-west-2'),
                    aws_access_key=aws_creds.get('aws_access_key_id') or aws_creds.get('aws_access_key'),
                    aws_secret_key=aws_creds.get('aws_secret_access_key') or aws_creds.get('aws_secret_key'),
                    aws_session_token=aws_creds.get('aws_session_token')
                )
            except Exception as e:
                print(f"Error listing AWS: {e}")
            
            # Format response
            response_text = "📊 **Active Instances**\n\n"
            
            if gcp_instances:
                response_text += "**GCP:**\n"
                for inst in gcp_instances[:10]:  # Limit to 10
                    name = inst.get('name', 'N/A')
                    status = inst.get('status', 'N/A')
                    ip = inst.get('public_ip', 'N/A')
                    response_text += f"• {name} - {status}\n  IP: {ip}\n"
                response_text += "\n"
            
            if aws_instances:
                response_text += "**AWS:**\n"
                for inst in aws_instances[:10]:  # Limit to 10
                    name = inst.get('Name', 'N/A')
                    status = inst.get('State', 'N/A')
                    ip = inst.get('PublicIpAddress', 'N/A')
                    response_text += f"• {name} - {status}\n  IP: {ip}\n"
            
            if not gcp_instances and not aws_instances:
                response_text += "No active instances found."
            
            _send_telegram_message(chat_id, response_text)
        
        return {"ok": True}
    except Exception as e:
        print(f"Error in telegram webhook: {e}")
        return {"ok": False, "error": str(e)}

def _send_telegram_message(chat_id: int, text: str):
    """Send a message to a specific Telegram chat"""
    if not TELEGRAM_BOT_TOKEN:
        print(f"Cannot send message, bot token not configured: {text}")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='Gestionar instancias de GCP'
    )
    
    # Acciones
    parser.add_argument(
        '--find-instance',
        action='store_true',
        help='Buscar instancias compatibles'
    )
    
    parser.add_argument(
        '--create-instance',
        action='store_true',
        help='Crear una nueva instancia'
    )
    
    parser.add_argument(
        '--list-instances',
        action='store_true',
        help='Listar todas las instancias del proyecto'
    )
    
    parser.add_argument(
        '--delete-instance',
        action='store_true',
        help='Borrar una instancia del proyecto'
    )
    
    # Parámetros comunes
    parser.add_argument(
        '--credentials',
        required=True,
        help='Ruta al archivo de credenciales de GCP (JSON)'
    )
    
    parser.add_argument(
        '--zone',
        help='Zona de GCP (ej: us-central1-a) - requerido para --find-instance y --create-instance'
    )
    
    # Parámetros para find-instance
    parser.add_argument(
        '--region',
        help='Región de GCP (ej: us-central1) - requerido para --find-instance'
    )
    
    parser.add_argument(
        '--cpus',
        type=int,
        help='Número mínimo de CPUs - requerido para --find-instance'
    )
    
    parser.add_argument(
        '--ram',
        type=int,
        help='Cantidad mínima de RAM en GB - requerido para --find-instance'
    )
    
    
    parser.add_argument(
        '--machine-type',
        help='Tipo de máquina (ej: e2-medium, n1-standard-1) - requerido para --create-instance'
    )
    
    parser.add_argument(
        '--ssh-key',
        help='Clave SSH pública para acceso a la instancia (formato: usuario:ssh-rsa AAAA...)'
    )
    
    parser.add_argument(
        '--name',
        help='Nombre de la instancia (ej: node1, node2, node3, etc.)'
    )
    
    args = parser.parse_args()
    
    # Validar que se haya seleccionado una acción
    if not args.find_instance and not args.create_instance and not args.list_instances and not args.delete_instance:
        parser.print_help()
        return
    
    # Cargar credenciales
    print(f"Cargando credenciales desde: {args.credentials}")
    credentials = load_credentials(args.credentials)
    
    # Configurar variable de entorno para autenticación
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = args.credentials
    
    if args.find_instance:
        # Validar parámetros requeridos para find-instance
        if not all([args.region, args.cpus, args.ram, args.zone]):
            parser.error("--find-instance requiere --region, --cpus y --ram y --zone")
        
        # Buscar instancias
        find_instances(
            project_id=credentials['project_id'],
            zone=args.zone,
            region=args.region,
            num_cpus=args.cpus,
            num_ram_gb=args.ram
        )
    
    elif args.create_instance:
        # Validar parámetros requeridos para create-instance
        if not all([args.name, args.machine_type, args.zone]):
            parser.error("--create-instance requiere --name, --machine-type, --zone")
        
        
        # Crear instancia
        create_instance(
            project_id=credentials['project_id'],
            zone=args.zone,
            instance_name=args.name,
            machine_type=args.machine_type,
            ssh_key=args.ssh_key
        )
    
    elif args.list_instances:
        # Listar instancias
        list_instances(
            project_id=credentials['project_id'],
            zone=args.zone,
        )
    
    elif args.delete_instance:
        # Validar parámetros requeridos para delete-instance
        if not args.name:
            parser.error("--delete-instance requiere --name")
        
        # Borrar instancia
        if args.zone:
            # Borrar en una zona específica
            delete_instance(
                project_id=credentials['project_id'],
                zone=args.zone,
                instance_name=args.name
            )
        else:
            # Buscar en todas las zonas y borrar
            find_and_delete_instance(
                project_id=credentials['project_id'],
                instance_name=args.name
            )

if __name__ == '__main__':
    main()