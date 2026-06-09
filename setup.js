#!/usr/bin/env node
/**
 * setup.js — One-time setup script to register the Telegram webhook.
 * Run this after deploying to Vercel.
 * 
 * Usage: node setup.js
 */

require('dotenv').config();

const BOT_TOKEN = process.env.BOT_TOKEN;
const VERCEL_URL = process.env.VERCEL_URL;

if (!BOT_TOKEN) {
  console.error('❌ BOT_TOKEN is not set in environment variables.');
  console.error('   Create a .env file with BOT_TOKEN=your_bot_token_here');
  process.exit(1);
}

// If VERCEL_URL is not set, use the default vercel.app domain
const WEBHOOK_URL = VERCEL_URL
  ? `https://${VERCEL_URL}/api/webhook`
  : null;

if (!WEBHOOK_URL) {
  console.error('❌ VERCEL_URL is not set.');
  console.error('   After deploying, set VERCEL_URL to your vercel.app domain (without https://)');
  console.error('   Example: my-bot-project.vercel.app');
  process.exit(1);
}

async function setupWebhook() {
  console.log(`🔗 Registering webhook: ${WEBHOOK_URL}`);
  
  try {
    const res = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/setWebhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: WEBHOOK_URL,
        allowed_updates: ['message', 'callback_query'],
      }),
    });

    const data = await res.json();

    if (data.ok) {
      console.log('✅ Webhook registered successfully!');
      console.log(`   URL: ${data.result.url}`);
      console.log(`   Pending updates: ${data.result.pending_update_count || 0}`);
    } else {
      console.error(`❌ Failed to register webhook:`);
      console.error(`   ${data.description}`);
      process.exit(1);
    }
  } catch (err) {
    console.error(`❌ Network error: ${err.message}`);
    process.exit(1);
  }
}

setupWebhook();
