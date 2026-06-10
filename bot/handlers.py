"""
Telegram bot message handlers.
All logic lives here; the Vercel webhook calls process_update().
"""
import os
import io
import requests
import telebot
from telebot import types

from .session import get_session, set_session, clear_session
from .parsers import parse_forumias_pdf, parse_vajiram, parse_vision

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

MENU_TEXT = (
    "👋 *UPSC PDF → TXT Converter Bot*\n\n"
    "Convert UPSC test PDFs into perfectly formatted `.txt` files.\n\n"
    "🟡 *ForumIAS SFG* — 50 Questions\n"
    "   Upload the *Solutions PDF* only\n\n"
    "🟢 *Vajiram & Ravi* — 100 Questions\n"
    "   Upload *Test PDF* + *Solutions PDF*\n\n"
    "🔵 *VisionIAS* — 100 Questions\n"
    "   Upload *Test PDF* + *Solutions PDF*\n\n"
    "Choose a converter below 👇"
)

KEYBOARD_MAIN = types.InlineKeyboardMarkup(row_width=1)
KEYBOARD_MAIN.add(
    types.InlineKeyboardButton("⚡ ForumIAS SFG — 50Q", callback_data="mode_forumias"),
    types.InlineKeyboardButton("⚙️ Vajiram & Ravi — 100Q", callback_data="mode_vajiram"),
    types.InlineKeyboardButton("🔮 VisionIAS — 100Q", callback_data="mode_vision"),
)


def _download_file(file_id: str) -> bytes:
    """Download a Telegram file by file_id and return bytes."""
    file_info = bot.get_file(file_id)
    url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}'
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def _send_menu(chat_id: int):
    bot.send_message(
        chat_id,
        MENU_TEXT,
        parse_mode='Markdown',
        reply_markup=KEYBOARD_MAIN
    )


@bot.message_handler(commands=['start', 'help', 'menu'])
def cmd_start(message: types.Message):
    clear_session(message.from_user.id)
    _send_menu(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith('mode_'))
def cb_mode(call: types.CallbackQuery):
    mode = call.data.split('_', 1)[1]
    uid = call.from_user.id
    cid = call.message.chat.id

    clear_session(uid)
    set_session(uid, {'mode': mode, 'step': 'waiting_test' if mode != 'forumias' else 'waiting_sol'})

    bot.answer_callback_query(call.id)

    if mode == 'forumias':
        bot.send_message(
            cid,
            "📄 *ForumIAS SFG Mode*\n\n"
            "Send me the *Solutions PDF* file now.\n"
            "_(The one with Ans\\) and Exp\\) blocks for all 50 questions)_",
            parse_mode='Markdown'
        )
    elif mode == 'vajiram':
        bot.send_message(
            cid,
            "📝 *Vajiram & Ravi Mode* — Step 1/2\n\n"
            "Send me the *Test Booklet PDF* \\(the question paper\\) now.",
            parse_mode='MarkdownV2'
        )
    elif mode == 'vision':
        bot.send_message(
            cid,
            "📋 *VisionIAS Mode* — Step 1/2\n\n"
            "Send me the *Test PDF* \\(the question booklet\\) now.",
            parse_mode='MarkdownV2'
        )


@bot.callback_query_handler(func=lambda c: c.data == 'cancel')
def cb_cancel(call: types.CallbackQuery):
    clear_session(call.from_user.id)
    bot.answer_callback_query(call.id, "Cancelled.")
    _send_menu(call.message.chat.id)


@bot.message_handler(content_types=['document'])
def handle_document(message: types.Message):
    uid = message.from_user.id
    cid = message.chat.id
    session = get_session(uid)

    if not session or 'mode' not in session:
        bot.send_message(
            cid,
            "Please select a converter mode first.",
            reply_markup=KEYBOARD_MAIN
        )
        return

    doc = message.document
    if not doc.file_name.lower().endswith('.pdf'):
        bot.send_message(cid, "❌ Please send a PDF file.")
        return

    mode = session['mode']
    step = session.get('step', '')

    # ── ForumIAS: single PDF ─────────────────────────────────────────────────
    if mode == 'forumias' and step == 'waiting_sol':
        msg = bot.send_message(cid, "⏳ Processing your PDF… This may take 30–60 seconds.")
        try:
            pdf_bytes = _download_file(doc.file_id)
            result = parse_forumias_pdf(pdf_bytes)
            if not result.strip():
                bot.edit_message_text("❌ Could not extract any questions. Make sure this is a text-based ForumIAS solutions PDF.",
                                      cid, msg.message_id)
                return
            q_count = result.count('\n😂\n')
            _send_result(cid, msg.message_id, result, doc.file_name, q_count, 50)
            clear_session(uid)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)[:300]}", cid, msg.message_id)
            clear_session(uid)
        return

    # ── Vajiram: step 1 → receive test PDF ──────────────────────────────────
    if mode == 'vajiram' and step == 'waiting_test':
        session['test_file_id'] = doc.file_id
        session['test_file_name'] = doc.file_name
        session['step'] = 'waiting_sol'
        set_session(uid, session)
        cancel_kb = types.InlineKeyboardMarkup()
        cancel_kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
        bot.send_message(
            cid,
            f"✅ Test PDF received: `{doc.file_name}`\n\n"
            "Now send me the *Solutions / Answer Key PDF*.",
            parse_mode='Markdown',
            reply_markup=cancel_kb
        )
        return

    if mode == 'vajiram' and step == 'waiting_sol':
        msg = bot.send_message(cid, "⏳ Processing both PDFs… This may take 60–90 seconds.")
        try:
            test_bytes = _download_file(session['test_file_id'])
            sol_bytes = _download_file(doc.file_id)
            result = parse_vajiram(test_bytes, sol_bytes)
            if not result.strip():
                bot.edit_message_text("❌ Could not extract questions. Make sure both PDFs are text-based Vajiram files.",
                                      cid, msg.message_id)
                return
            q_count = result.count('\n😂\n')
            _send_result(cid, msg.message_id, result, session.get('test_file_name', 'vajiram'), q_count, 100)
            clear_session(uid)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)[:300]}", cid, msg.message_id)
            clear_session(uid)
        return

    # ── VisionIAS: step 1 → receive test PDF ────────────────────────────────
    if mode == 'vision' and step == 'waiting_test':
        session['test_file_id'] = doc.file_id
        session['test_file_name'] = doc.file_name
        session['step'] = 'waiting_sol'
        set_session(uid, session)
        cancel_kb = types.InlineKeyboardMarkup()
        cancel_kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
        bot.send_message(
            cid,
            f"✅ Test PDF received: `{doc.file_name}`\n\n"
            "Now send me the *Solution PDF* \\(with `Q 1\\.A` style answers\\).",
            parse_mode='MarkdownV2',
            reply_markup=cancel_kb
        )
        return

    if mode == 'vision' and step == 'waiting_sol':
        msg = bot.send_message(cid, "⏳ Processing both PDFs… This may take 60–90 seconds.")
        try:
            test_bytes = _download_file(session['test_file_id'])
            sol_bytes = _download_file(doc.file_id)
            result = parse_vision(test_bytes, sol_bytes)
            if not result.strip():
                bot.edit_message_text("❌ Could not extract questions. Make sure both PDFs are text-based VisionIAS files.",
                                      cid, msg.message_id)
                return
            q_count = result.count('\n😂\n')
            _send_result(cid, msg.message_id, result, session.get('test_file_name', 'vision'), q_count, 100)
            clear_session(uid)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)[:300]}", cid, msg.message_id)
            clear_session(uid)
        return

    bot.send_message(cid, "Unexpected state. Use /start to begin again.")
    clear_session(uid)


def _send_result(chat_id: int, processing_msg_id: int, result: str,
                 original_filename: str, q_count: int, expected: int):
    """Send the converted .txt file back to the user."""
    txt_bytes = result.encode('utf-8')
    base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
    out_filename = f"{base_name}_CONVERTED.txt"

    status_icon = "✅" if q_count >= expected else "⚠️"
    caption = (
        f"{status_icon} *Conversion Complete!*\n\n"
        f"📊 Questions extracted: `{q_count}` / `{expected}`\n"
        f"📁 File: `{out_filename}`\n\n"
        f"{'_All questions extracted successfully._' if q_count >= expected else f'_Only {q_count} questions found — review output carefully._'}"
    )

    bot.edit_message_text(
        f"{status_icon} Done! Sending your file…",
        chat_id, processing_msg_id
    )

    bot.send_document(
        chat_id,
        document=io.BytesIO(txt_bytes),
        visible_file_name=out_filename,
        caption=caption,
        parse_mode='Markdown',
        reply_markup=_back_to_menu_kb()
    )


def _back_to_menu_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏠 Convert Another", callback_data="back_menu"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data == 'back_menu')
def cb_back_menu(call: types.CallbackQuery):
    clear_session(call.from_user.id)
    bot.answer_callback_query(call.id)
    _send_menu(call.message.chat.id)


@bot.message_handler(func=lambda m: True)
def handle_other(message: types.Message):
    session = get_session(message.from_user.id)
    if session.get('mode'):
        mode_names = {'forumias': 'ForumIAS SFG', 'vajiram': 'Vajiram & Ravi', 'vision': 'VisionIAS'}
        bot.send_message(
            message.chat.id,
            f"I'm waiting for a PDF file in *{mode_names.get(session['mode'], 'unknown')}* mode.\n"
            "Please send a `.pdf` file, or use /start to go back to the menu.",
            parse_mode='Markdown'
        )
    else:
        _send_menu(message.chat.id)


def process_update(json_string: str):
    """Entry point called from the Vercel webhook handler."""
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
