#!/bin/bash

# Telegram Configuration Helper
echo "=== Telegram Configuration Helper ==="
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file"
fi

echo "Current .env contents:"
cat .env
echo ""

# Check if variables are set
if grep -q "your_bot_token_here" .env || grep -q "your_chat_id_here" .env; then
    echo "⚠️  WARNING: You need to update .env with your actual Telegram credentials!"
    echo ""
    echo "Steps to get credentials:"
    echo "1. Bot Token: Talk to @BotFather on Telegram"
    echo "   - Send /newbot"
    echo "   - Follow instructions"
    echo "   - Copy the token"
    echo ""
    echo "2. Chat ID: Send a message to your bot, then visit:"
    echo "   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
    echo "   - Look for 'chat':{'id': YOUR_CHAT_ID}"
    echo ""
    echo "3. Edit .env file and replace the placeholders"
    echo ""
else
    echo "✅ .env appears to be configured"
    echo ""
    echo "Testing Telegram connection..."
    
    # Load .env
    export $(cat .env | xargs)
    
    # Test message
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
         -d "chat_id=${TELEGRAM_CHAT_ID}" \
         -d "text=🧪 Test message from backend setup script" \
         > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ Test message sent successfully! Check your Telegram."
    else
        echo "❌ Failed to send test message. Please verify your credentials."
    fi
fi

echo ""
echo "To apply changes, restart your backend server."
