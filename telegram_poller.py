import os
import time
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BACKEND_URL = "http://localhost:8001"

if not TELEGRAM_BOT_TOKEN:
    print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env")
    exit(1)

print(f"🤖 Telegram Bot Poller started for bot: {TELEGRAM_BOT_TOKEN[:10]}...")
print(f"📡 Backend URL: {BACKEND_URL}")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {'timeout': 30, 'offset': offset}
    try:
        response = requests.get(url, params=params)
        return response.json()
    except Exception as e:
        print(f"Error getting updates: {e}")
        return None

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Error sending message: {e}")

def handle_list_command(chat_id):
    send_message(chat_id, "🔍 Buscando instancias activas...")
    
    try:
        # Get GCP instances
        gcp_res = requests.get(f"{BACKEND_URL}/list")
        gcp_data = gcp_res.json()
        
        # Get AWS instances
        aws_res = requests.get(f"{BACKEND_URL}/aws/list")
        aws_data = aws_res.json()
        
        message = "📊 **Estado del Cluster**\n\n"
        
        # GCP Section
        message += "☁️ **Google Cloud (GCP)**\n"
        if gcp_data.get('success') and gcp_data.get('instances'):
            for inst in gcp_data['instances']:
                name = inst.get('name', 'N/A')
                status = inst.get('status', 'N/A')
                ip = inst.get('external_ips', ['N/A'])[0] if inst.get('external_ips') else 'N/A'
                cpu = inst.get('cpu', '?')
                ram = inst.get('ram', '?')
                
                icon = "🟢" if status == "RUNNING" else "🔴"
                message += f"{icon} *{name}*\n"
                message += f"   IP: `{ip}`\n"
                message += f"   Specs: {cpu} vCPU | {ram} GB RAM\n\n"
        else:
            message += "_No hay instancias activas_\n\n"
            
        # AWS Section
        message += "☁️ **Amazon AWS**\n"
        if aws_data.get('success') and aws_data.get('instances'):
            for inst in aws_data['instances']:
                name = inst.get('Name', 'N/A')
                status = inst.get('State', 'N/A')
                ip = inst.get('PublicIpAddress', 'N/A')
                cpu = inst.get('cpu', '?')
                ram = inst.get('ram', '?')
                
                icon = "🟢" if status == "running" else "🔴"
                message += f"{icon} *{name}*\n"
                message += f"   IP: `{ip}`\n"
                message += f"   Specs: {cpu} vCPU | {ram} GB RAM\n\n"
        else:
            message += "_No hay instancias activas_\n"
            
        send_message(chat_id, message)
        
    except Exception as e:
        send_message(chat_id, f"❌ Error al conectar con el backend: {str(e)}")

def main():
    offset = None
    while True:
        updates = get_updates(offset)
        if updates and updates.get('ok'):
            for update in updates['result']:
                offset = update['update_id'] + 1
                
                if 'message' in update and 'text' in update['message']:
                    text = update['message']['text']
                    chat_id = update['message']['chat']['id']
                    
                    print(f"📩 Received: {text} from {chat_id}")
                    
                    if text == '/start':
                        send_message(chat_id, "👋 Hola! Soy tu Cloud Manager Bot.\n\nComandos:\n/list - Ver instancias activas")
                    elif text == '/list':
                        handle_list_command(chat_id)
                    elif text == '/credentials':
                        send_message(chat_id, "🔐 Para ver credenciales, usa el dashboard web o espera a recibir notificaciones automáticas.")
        
        time.sleep(1)

if __name__ == "__main__":
    try:
        # Check if requests is installed
        import requests
        main()
    except ImportError:
        print("❌ Error: 'requests' library is missing.")
        print("Run: pip install requests")
