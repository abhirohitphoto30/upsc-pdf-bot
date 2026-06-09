#!/usr/bin/env node
/**
 * start.js — Run the bot in polling mode (local development or non-webhook deployment).
 * 
 * Usage: node start.js
 * 
 * Set BOT_TOKEN in your environment or .env file.
 * Set POLLING=true to enable polling (default when running this file).
 */

require('dotenv').config();

const { BOT_TOKEN } = process.env;

if (!BOT_TOKEN) {
  console.error('❌ BOT_TOKEN is not set.');
  console.error('   Create a .env file with: BOT_TOKEN=your_bot_token_here');
  process.exit(1);
}

// Simple long-polling Telegram bot runner
const { handleWebhook } = require('./lib/bot');

const BASE_URL = `https://api.telegram.org/bot${BOT_TOKEN}`;
let offset = 0;

async function getUpdates() {
  try {
    const res = await fetch(`${BASE_URL}/getUpdates?offset=${offset}&timeout=30&allowed_updates=["message","callback_query"]`);
    const data = await res.json();
    if (!data.ok) {
      console.error('Telegram API error:', data);
      return [];
    }
    return data.result;
  } catch (err) {
    console.error('Network error:', err.message);
    return [];
  }
}

async function processUpdate(update) {
  offset = update.update_id + 1;
  try {
    await handleWebhook(update);
  } catch (err) {
    console.error('Error processing update:', err);
  }
}

async function poll() {
  console.log('🤖 Bot started in polling mode...');
  console.log(`📡 Listening for updates (offset: ${offset})`);
  
  while (true) {
    const updates = await getUpdates();
    for (const update of updates) {
      await processUpdate(update);
    }
    // Small delay before next poll to avoid rate limiting
    await new Promise(r => setTimeout(r, 500));
  }
}

poll().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
