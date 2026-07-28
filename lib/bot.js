/**
 * Core bot handler — routes updates to the right conversation flow.
 *
 * Conversation state is stored in a simple in-memory Map keyed by chatId.
 * Since Vercel serverless functions are stateless between cold starts,
 * the session data survives as long as the container stays warm (~5-15 min),
 * which is enough for a single conversion session.
 */

const { sendMessage, sendDocument, sendChatAction, editMessageText, answerCallbackQuery } = require('./api');
const { processSfg } = require('./sfg');
const { processVajiram } = require('./vajiram');
const { processVision } = require('./vision');

// ── In-memory session store ──────────────────────────────────────────
/** @type {Map<string, { mode: string, files: { test?: Buffer, sol?: Buffer } }>} */
const sessions = new Map();

// ── Keyboard helpers ─────────────────────────────────────────────────
function mainKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: '⚡ ForumIAS SFG (50 Q)', callback_data: 'mode:sfg' },
      ],
      [
        { text: '⚙️ Vajiram & Ravi (100 Q)', callback_data: 'mode:vajiram' },
      ],
      [
        { text: '🔮 VisionIAS (100 Q)', callback_data: 'mode:vision' },
      ],
    ],
  };
}

function backKeyboard() {
  return {
    inline_keyboard: [
      [{ text: '↩️ Back to Menu', callback_data: 'menu' }],
    ],
  };
}

// ── Command: /start ──────────────────────────────────────────────────
async function handleStart(chatId) {
  await sendMessage(chatId,
`👋 <b>Welcome to UPSC PDF → TXT Converter Bot!</b>

This bot converts UPSC test-series PDFs into a perfectly formatted .txt file @Shrma_Ishuu_bot — exactly like the HTML version, but right here in Telegram.

<b>Choose a converter:</b>`,
    { reply_markup: mainKeyboard() }
  );
}

// ── Command: /menu ───────────────────────────────────────────────────
async function handleMenu(chatId) {
  sessions.delete(chatId);
  await sendMessage(chatId,
`🏠 <b>Main Menu</b>

Choose a converter mode:`,
    { reply_markup: mainKeyboard() }
  );
}

// ── Inline callback query handler ────────────────────────────────────
async function handleCallback(chatId, msgId, data, callbackQueryId) {
  if (callbackQueryId) {
    await answerCallbackQuery(callbackQueryId);
  }

  // ── Navigation ──
  if (data === 'menu') {
    sessions.delete(chatId);
    await editMessageText(chatId, msgId,
`🏠 <b>Main Menu</b>

Choose a converter mode:`,
      { reply_markup: mainKeyboard() }
    );
    return;
  }

  // ── Mode selection ──
  const modeMatch = data.match(/^mode:(\w+)$/);
  if (modeMatch) {
    const mode = modeMatch[1];
    sessions.set(chatId, { mode, files: {} });

    if (mode === 'sfg') {
      await editMessageText(chatId, msgId,
`⚡ <b>ForumIAS SFG Converter</b> (50 Questions)

📄 <b>Send your Solutions PDF now.</b>

The bot will extract all 50 questions with correct answers ✅ and explanations, then give you a formatted .txt file to download.

💡 <i>Single PDF upload — just send the solutions file.</i>`,
        { reply_markup: backKeyboard() }
      );
    } else if (mode === 'vajiram') {
      await editMessageText(chatId, msgId,
`⚙️ <b>Vajiram & Ravi Converter</b> (100 Questions)

📝 <b>Step 1 of 2 —</b> Send the <b>Test Booklet PDF</b> (questions).
📄 <b>Step 2 of 2 —</b> Then send the <b>Solutions PDF</b> (answers + explanations).

You can send them in any order — the bot will auto-detect which is which based on content.

⏳ <i>Awaiting files…</i>`,
        { reply_markup: backKeyboard() }
      );
    } else if (mode === 'vision') {
      await editMessageText(chatId, msgId,
`🔮 <b>VisionIAS Converter</b> (100 Questions)

📋 <b>Step 1 of 2 —</b> Send the <b>Test PDF</b> (question booklet).
💡 <b>Step 2 of 2 —</b> Send the <b>Solution PDF</b> (answers + explanations).

Send them one after the other — the bot will detect which is which.

⏳ <i>Awaiting files…</i>`,
        { reply_markup: backKeyboard() }
      );
    }
    return;
  }
}

// ── File/document message handler ────────────────────────────────────
async function handleDocument(chatId, msgId, file) {
  const session = sessions.get(chatId);
  if (!session || !session.mode) {
    await sendMessage(chatId,
`⚠️ Please select a converter mode first by sending /start or /menu.`,
      { reply_markup: mainKeyboard() }
    );
    return;
  }

  // Download the file
  const buffer = await downloadFile(file.file_id);

  if (session.mode === 'sfg') {
    await handleSfgFile(chatId, msgId, buffer, file.file_name);
  } else if (session.mode === 'vajiram') {
    await handleVajiramFile(chatId, msgId, buffer, file.file_name);
  } else if (session.mode === 'vision') {
    await handleVisionFile(chatId, msgId, buffer, file.file_name);
  }
}

// ── Download a file from Telegram ────────────────────────────────────
async function downloadFile(fileId) {
  const BOT_TOKEN = process.env.BOT_TOKEN;
  const fileInfo = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/getFile?file_id=${fileId}`).then(r => r.json());
  if (!fileInfo.ok) throw new Error(`getFile failed: ${fileInfo.description}`);
  const filePath = fileInfo.result.file_path;
  const url = `https://api.telegram.org/file/bot${BOT_TOKEN}/${filePath}`;
  const res = await fetch(url);
  return Buffer.from(await res.arrayBuffer());
}

// ═════════════════════════════════════════════════════════════════════
//  SFG HANDLER
// ═════════════════════════════════════════════════════════════════════
async function handleSfgFile(chatId, msgId, buffer, filename) {
  const statusMsg = await sendMessage(chatId,
`⚡ <b>Processing ForumIAS SFG PDF…</b>

📄 File: <code>${filename}</code>
🔄 Extracting text…`,
    { reply_markup: backKeyboard() }
  );
  const statusMsgId = statusMsg.message_id;

  try {
    await sendChatAction(chatId, 'typing');
    const result = await processSfg(buffer, (progress) => {
      editMessageText(chatId, statusMsgId,
`⚡ <b>Processing ForumIAS SFG PDF…</b>

📄 File: <code>${filename}</code>
🔄 Progress: ${progress}%`,
        { reply_markup: backKeyboard() }
      ).catch(() => {});
    });

    if (!result.success) {
      await editMessageText(chatId, statusMsgId,
`❌ <b>Error processing PDF:</b>\n\n<code>${result.error}</code>\n\nPlease try again or send a different PDF.`,
        { reply_markup: backKeyboard() }
      );
      return;
    }

    const outputBuffer = Buffer.from(result.output, 'utf-8');
    const outputFilename = (filename || 'SFG').replace(/\.pdf$/i, '') + '_CONVERTED.txt';

    await editMessageText(chatId, statusMsgId,
`✅ <b>ForumIAS SFG conversion complete!</b>

📊 Questions extracted: <b>${result.questionCount}</b>
📄 Lines: <b>${result.lineCount}</b>
📦 Size: <b>${(outputBuffer.length / 1024).toFixed(1)} KB</b>
${result.questionCount < 50 ? '\n⚠️ <i>Expected 50 questions — got ' + result.questionCount + '. Some formatting may differ from standard.</i>' : '\n✅ All 50 questions extracted successfully!'}`,
      { reply_markup: backKeyboard() }
    );

    await sendDocument(chatId, outputBuffer, outputFilename);
  } catch (err) {
    console.error('SFG error:', err);
    await editMessageText(chatId, statusMsgId,
`❌ <b>Unexpected error:</b>\n\n<code>${err.message}</code>\n\nPlease try again.`,
      { reply_markup: backKeyboard() }
    );
  }

  // Reset session
  sessions.delete(chatId);
}

// ═════════════════════════════════════════════════════════════════════
//  VAJIRAM HANDLER
// ═════════════════════════════════════════════════════════════════════
async function handleVajiramFile(chatId, msgId, buffer, filename) {
  const session = sessions.get(chatId);
  if (!session) return;

  // Determine which file this is
  const hasTest = session.files.test;
  const hasSol = session.files.sol;

  if (!hasTest) {
    session.files.test = buffer;
    session.files.testName = filename;

    await sendMessage(chatId,
`✅ <b>Test Booklet received!</b>

📄 <code>${filename}</code>
📏 Size: ${(buffer.length / 1024).toFixed(1)} KB

📄 Now please send the <b>Solutions PDF</b> to complete the conversion.`
    );
    return;
  }

  if (!hasSol) {
    session.files.sol = buffer;
    session.files.solName = filename;

    const statusMsg = await sendMessage(chatId,
`⚙️ <b>Compiling Vajiram & Ravi PDFs…</b>

📝 Test: <code>${session.files.testName}</code>
📄 Sol: <code>${filename}</code>
🔄 Processing…`,
      { reply_markup: backKeyboard() }
    );
    const statusMsgId = statusMsg.message_id;

    try {
      await sendChatAction(chatId, 'typing');
      const result = await processVajiram(
        session.files.test,
        session.files.sol,
        (progress, label) => {
          editMessageText(chatId, statusMsgId,
`⚙️ <b>Compiling Vajiram & Ravi PDFs…</b>

📝 Test: <code>${session.files.testName}</code>
📄 Sol: <code>${filename}</code>
🔄 ${label} (${Math.round(progress)}%)`,
            { reply_markup: backKeyboard() }
          ).catch(() => {});
        }
      );

      if (!result.success) {
        await editMessageText(chatId, statusMsgId,
`❌ <b>Error processing PDFs:</b>\n\n<code>${result.error}</code>\n\nPlease try again with valid Vajiram PDFs.`,
          { reply_markup: backKeyboard() }
        );
        return;
      }

      const outputBuffer = Buffer.from(result.output, 'utf-8');
      const outputFilename = (session.files.testName || 'VAJIRAM').replace(/\.pdf$/i, '') + '_COMPILED.txt';

      await editMessageText(chatId, statusMsgId,
`✅ <b>Vajiram & Ravi compilation complete!</b>

📊 Questions extracted: <b>${result.questionCount}</b>
📄 Lines: <b>${result.lineCount}</b>
📦 Size: <b>${(outputBuffer.length / 1024).toFixed(1)} KB</b>`,
        { reply_markup: backKeyboard() }
      );

      await sendDocument(chatId, outputBuffer, outputFilename);
    } catch (err) {
      console.error('Vajiram error:', err);
      await editMessageText(chatId, statusMsgId,
`❌ <b>Unexpected error:</b>\n\n<code>${err.message}</code>\n\nPlease try again.`,
        { reply_markup: backKeyboard() }
      );
    }

    sessions.delete(chatId);
    return;
  }

  // Both files already received
  await sendMessage(chatId,
`⚠️ Processing already complete. Send /menu to start again.`
  );
}

// ═════════════════════════════════════════════════════════════════════
//  VISION HANDLER
// ═════════════════════════════════════════════════════════════════════
async function handleVisionFile(chatId, msgId, buffer, filename) {
  const session = sessions.get(chatId);
  if (!session) return;

  const hasTest = session.files.test;
  const hasSol = session.files.sol;

  if (!hasTest) {
    session.files.test = buffer;
    session.files.testName = filename;

    await sendMessage(chatId,
`✅ <b>Test PDF received!</b>

📄 <code>${filename}</code>
📏 Size: ${(buffer.length / 1024).toFixed(1)} KB

💡 Now please send the <b>Solution PDF</b> to complete the conversion.`
    );
    return;
  }

  if (!hasSol) {
    session.files.sol = buffer;
    session.files.solName = filename;

    const statusMsg = await sendMessage(chatId,
`🔮 <b>Converting VisionIAS PDFs…</b>

📋 Test: <code>${session.files.testName}</code>
💡 Sol: <code>${filename}</code>
🔄 Processing…`,
      { reply_markup: backKeyboard() }
    );
    const statusMsgId = statusMsg.message_id;

    try {
      await sendChatAction(chatId, 'typing');
      const result = await processVision(
        session.files.test,
        session.files.sol,
        (progress, label) => {
          editMessageText(chatId, statusMsgId,
`🔮 <b>Converting VisionIAS PDFs…</b>

📋 Test: <code>${session.files.testName}</code>
💡 Sol: <code>${filename}</code>
🔄 ${label} (${Math.round(progress)}%)`,
            { reply_markup: backKeyboard() }
          ).catch(() => {});
        }
      );

      if (!result.success) {
        await editMessageText(chatId, statusMsgId,
`❌ <b>Error processing PDFs:</b>\n\n<code>${result.error}</code>\n\nPlease try again with valid VisionIAS PDFs.`,
          { reply_markup: backKeyboard() }
        );
        return;
      }

      const outputBuffer = Buffer.from(result.output, 'utf-8');
      const outputFilename = (session.files.testName || 'VISIONIAS').replace(/\.pdf$/i, '') + '_CONVERTED.txt';

      await editMessageText(chatId, statusMsgId,
`✅ <b>VisionIAS conversion complete!</b>

📊 Questions extracted: <b>${result.questionCount}</b>
📄 Lines: <b>${result.lineCount}</b>
📦 Size: <b>${(outputBuffer.length / 1024).toFixed(1)} KB</b>`,
        { reply_markup: backKeyboard() }
      );

      await sendDocument(chatId, outputBuffer, outputFilename);
    } catch (err) {
      console.error('Vision error:', err);
      await editMessageText(chatId, statusMsgId,
`❌ <b>Unexpected error:</b>\n\n<code>${err.message}</code>\n\nPlease try again.`,
        { reply_markup: backKeyboard() }
      );
    }

    sessions.delete(chatId);
    return;
  }

  await sendMessage(chatId,
`⚠️ Processing already complete. Send /menu to start again.`
  );
}

// ═════════════════════════════════════════════════════════════════════
//  TEXT COMMAND HANDLER
// ═════════════════════════════════════════════════════════════════════
async function handleTextMessage(chatId, msgId, text) {
  const cmd = text.trim().toLowerCase();

  if (cmd === '/start') {
    await handleStart(chatId);
    return;
  }
  if (cmd === '/menu') {
    await handleMenu(chatId);
    return;
  }
  if (cmd === '/help') {
    await sendMessage(chatId,
`<b>🤖 UPSC PDF → TXT Converter Bot</b>

<b>Commands:</b>
/start — Start the bot and choose a converter
/menu — Return to main menu
/help — Show this help message

<b>How to use:</b>
1️⃣ Select a converter from the menu
2️⃣ Send the required PDF file(s)
3️⃣ Wait for processing
4️⃣ Download your formatted .txt file

<b>Supported formats:</b>
⚡ ForumIAS SFG — single solutions PDF
⚙️ Vajiram & Ravi — test booklet + solutions PDF
🔮 VisionIAS — test PDF + solution PDF

<i>All processing happens server-side. Your files are never stored permanently.</i>`
    );
    return;
  }

  // If we're in a session and user sends text instead of file
  const session = sessions.get(chatId);
  if (session) {
    await sendMessage(chatId,
`📄 Please <b>send the PDF file</b> as a document attachment.

If you want to change mode, send /menu.`,
      { reply_markup: backKeyboard() }
    );
    return;
  }

  await sendMessage(chatId,
`Unknown command. Send /start to begin, or /help for instructions.`
  );
}

// ═════════════════════════════════════════════════════════════════════
//  MAIN WEBHOOK ROUTER
// ═════════════════════════════════════════════════════════════════════
async function handleWebhook(update) {
  const chatId = update.message?.chat?.id ?? update.callback_query?.message?.chat?.id;
  if (!chatId) return;

  const msgId = update.message?.message_id ?? update.callback_query?.message?.message_id;

  // Callback query (inline button presses)
  if (update.callback_query) {
    await handleCallback(
      chatId,
      msgId,
      update.callback_query.data,
      update.callback_query.id
    );
    return;
  }

  // Document message
  if (update.message?.document) {
    const doc = update.message.document;
    if (!doc.mime_type || !doc.mime_type.includes('pdf')) {
      await sendMessage(chatId,
`⚠️ Please send a <b>PDF file</b>. The bot only accepts .pdf documents.`
      );
      return;
    }
    if (doc.file_size > 50 * 1024 * 1024) {
      await sendMessage(chatId,
`⚠️ File too large. Maximum size is <b>50 MB</b>.`
      );
      return;
    }
    await handleDocument(chatId, msgId, doc);
    return;
  }

  // Text message
  if (update.message?.text) {
    await handleTextMessage(chatId, msgId, update.message.text);
    return;
  }

  // Photo with caption — try to process as PDF (won't work, but helpful message)
  if (update.message?.photo) {
    await sendMessage(chatId,
`📸 I can't process images. Please send the PDF as a <b>Document</b> (not a photo) so I can extract text from it.

In Telegram, tap the 📎 attachment icon and select <b>File</b> instead of <b>Gallery</b>.`
    );
    return;
  }
}

module.exports = { handleWebhook, handleStart, sessions };
