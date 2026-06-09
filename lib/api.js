/**
 * Telegram API helpers
 */

const BOT_TOKEN = process.env.BOT_TOKEN || '';
const BASE_URL = BOT_TOKEN ? `https://api.telegram.org/bot${BOT_TOKEN}` : '';

async function api(method, body = {}) {
  const res = await fetch(`${BASE_URL}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!data.ok) {
    console.error(`Telegram API error on ${method}:`, data);
    throw new Error(`Telegram API: ${data.description || JSON.stringify(data)}`);
  }
  return data.result;
}

module.exports = {
  async sendMessage(chatId, text, extra = {}) {
    return api('sendMessage', {
      chat_id: chatId,
      text,
      parse_mode: 'HTML',
      disable_web_page_preview: true,
      ...extra,
    });
  },

  async sendDocument(chatId, fileBuffer, filename) {
    const form = new FormData();
    form.append('chat_id', String(chatId));
    form.append('document', new Blob([fileBuffer]), filename);
    const res = await fetch(`${BASE_URL}/sendDocument`, { method: 'POST', body: form });
    const data = await res.json();
    if (!data.ok) throw new Error(`sendDocument failed: ${data.description || JSON.stringify(data)}`);
    return data.result;
  },

  async sendChatAction(chatId, action = 'typing') {
    return api('sendChatAction', { chat_id: chatId, action }).catch(() => {});
  },

  async editMessageText(chatId, messageId, text, extra = {}) {
    return api('editMessageText', {
      chat_id: chatId,
      message_id: messageId,
      text,
      parse_mode: 'HTML',
      ...extra,
    });
  },

  async answerCallbackQuery(callbackQueryId, text) {
    return api('answerCallbackQuery', { callback_query_id: callbackQueryId, text });
  },
};
