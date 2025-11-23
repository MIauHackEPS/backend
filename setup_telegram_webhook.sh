#!/bin/bash

# Telegram Bot Webhook Setup Script
echo "=== Telegram Bot Webhook Setup ==="
echo ""

# Check if .env exists and has token
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Run ./setup_telegram.sh first."
    exit 1
fi

# Load .env
export $(cat .env | xargs)

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ "$TELEGRAM_BOT_TOKEN" = "your_bot_token_here" ]; then
    echo "❌ TELEGRAM_BOT_TOKEN not configured in .env"
    echo "Run ./setup_telegram.sh to configure your bot."
    exit 1
fi

echo "✅ Bot token found"
echo ""

# Ask for webhook URL
echo "Enter your public webhook URL (e.g., https://your-domain.com/telegram/webhook):"
read WEBHOOK_URL

if [ -z "$WEBHOOK_URL" ]; then
    echo "❌ Webhook URL is required"
    exit 1
fi

echo ""
echo "Setting webhook to: $WEBHOOK_URL"

# Set webhook
RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
     -d "url=${WEBHOOK_URL}")

echo "Response: $RESPONSE"
echo ""

# Check webhook info
echo "Current webhook info:"
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool

echo ""
echo "✅ Webhook setup complete!"
echo ""
echo "Test your bot by sending /start or /list"
