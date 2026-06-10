"""
Vercel serverless function — Telegram webhook endpoint.
Deployed at: POST /api/webhook

Required environment variables:
  TELEGRAM_BOT_TOKEN   — your bot token from @BotFather
  WEBHOOK_SECRET       — a random string you choose (for security)
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, Response
from bot.handlers import process_update

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')


@app.route('/api/webhook', methods=['POST'])
def webhook():
    if WEBHOOK_SECRET:
        token_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if token_header != WEBHOOK_SECRET:
            return Response('Forbidden', status=403)

    content_type = request.headers.get('Content-Type', '')
    if 'application/json' not in content_type:
        return Response('Bad Request', status=400)

    try:
        json_string = request.get_data(as_text=True)
        process_update(json_string)
    except Exception as e:
        print(f"[webhook] Error: {e}", flush=True)

    return Response('OK', status=200)


@app.route('/api/webhook', methods=['GET'])
def health():
    return Response(
        json.dumps({'status': 'running', 'service': 'UPSC PDF Converter Bot'}),
        status=200,
        mimetype='application/json'
    )


@app.route('/', methods=['GET'])
def root():
    return Response(
        json.dumps({'status': 'ok', 'message': 'UPSC PDF Converter Telegram Bot'}),
        status=200,
        mimetype='application/json'
    )
