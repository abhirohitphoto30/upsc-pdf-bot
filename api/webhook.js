/**
 * Telegram Webhook Endpoint — receives all updates from Telegram.
 * 
 * ⚠️ IMPORTANT: Telegram sends updates as application/json POST bodies,
 * not as URL-encoded form data. Vercel parses this automatically.
 * 
 * ⚠️ PDF files sent by users arrive as separate file downloads via
 * Telegram's file API — the bot downloads them synchronously during
 * the document handler call.
 * 
 * ⚠️ Vercel serverless timeout: 
 *    - Hobby plan: 10 seconds
 *    - Pro plan: 60 seconds (configurable up to 300s with maxDuration)
 * 
 * For large PDFs, consider upgrading to Vercel Pro or using a dedicated
 * server. The polling mode (start.js) avoids this limitation entirely.
 */
const { handleWebhook } = require('../lib/bot');

module.exports = async (req, res) => {
  if (req.method === 'POST') {
    try {
      await handleWebhook(req.body);
      res.status(200).send('OK');
    } catch (err) {
      console.error('Webhook error:', err);
      res.status(200).send('OK'); // always 200 to Telegram
    }
  } else if (req.method === 'GET') {
    res.status(200).send('Bot is running.');
  } else {
    res.status(405).send('Method Not Allowed');
  }
};
