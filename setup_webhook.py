"""
Run this script ONCE after deploying to Vercel to register the webhook with Telegram.

Usage:
  TELEGRAM_BOT_TOKEN=xxx VERCEL_URL=https://your-app.vercel.app python setup_webhook.py

Optional:
  WEBHOOK_SECRET=your_random_secret   (same value you set in Vercel env vars)
"""
import os
import requests
import sys

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
VERCEL_URL = os.environ.get('VERCEL_URL', '').strip().rstrip('/')
SECRET = os.environ.get('WEBHOOK_SECRET', '').strip()

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
    sys.exit(1)

if not VERCEL_URL:
    print("ERROR: VERCEL_URL is not set.")
    sys.exit(1)

webhook_url = f"{VERCEL_URL}/api/webhook"
payload = {'url': webhook_url, 'max_connections': 40, 'allowed_updates': ['message', 'callback_query']}
if SECRET:
    payload['secret_token'] = SECRET

print(f"Setting webhook to: {webhook_url}")
r = requests.post(f'https://api.telegram.org/bot{TOKEN}/setWebhook', json=payload)
print(f"Status: {r.status_code}")
print(r.json())

info = requests.get(f'https://api.telegram.org/bot{TOKEN}/getWebhookInfo')
print("\nWebhook info:")
print(info.json())
