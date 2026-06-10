"""
Telegram bot message handlers.
All logic lives here; the Vercel webhook calls process_update().
"""
import os
import io
import requests
import telebot
from telebot import types

from .session import get_session, set_session, clear_session, save_pdf, load_pdf
from .parsers import parse_forumias_pdf, parse_vajiram, parse_vision

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

MENU_TEXT = (
    "👋 *UPSC PDF → TXT Converter Bot*\n\n"
    "Convert UPSC test PDFs into perfectly formatted `.txt` files\\.\n\n"
    "🟡 *ForumIAS SFG* — 50 Questions\n"
    "   Upload the *Solutions PDF* only\n\n"
    "🟢 *Vajiram & Ravi* — 100 Questions\n"
    "   Upload *Test PDF* first, then *Solutions PDF*\n\n"
    "🔵 *VisionIAS* — 100 Questions\n"
    "   Upload *Test PDF* first, then *Solutions PDF*\n\n"
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
        parse_mode='MarkdownV2',
        reply_markup=KEYBOARD_MAIN
    )


def _cancel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return kb


def _back_to_menu_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏠 Convert Another", callback_data="back_menu"))
    return kb


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
    step = 'waiting_sol' if mode == 'forumias' else 'waiting_test'
    set_session(uid, {'mode': mode, 'step': step})

    bot.answer_callback_query(call.id)

    if mode == 'forumias':
        bot.send_message(
            cid,
            "📄 *ForumIAS SFG Mode*\n\nSend me the *Solutions PDF* now\\.\n"
            "_\\(The one with Ans\\) and Exp\\) blocks for all 50 questions\\)_",
            parse_mode='MarkdownV2',
            reply_markup=_cancel_kb()
        )
    elif mode == 'vajiram':
        bot.send_message(
            cid,
            "📝 *Vajiram & Ravi Mode* — Step 1/2\n\n"
            "Send me the *Test Booklet PDF* \\(the question paper\\) first\\.",
            parse_mode='MarkdownV2',
            reply_markup=_cancel_kb()
        )
    elif mode == 'vision':
        bot.send_message(
            cid,
            "📋 *VisionIAS Mode* — Step 1/2\n\n"
            "Send me the *Test PDF* \\(the question booklet\\) first\\.",
            parse_mode='MarkdownV2',
            reply_markup=_cancel_kb()
        )


@bot.callback_query_handler(func=lambda c: c.data in ('cancel', 'back_menu'))
def cb_cancel_or_menu(call: types.CallbackQuery):
    clear_session(call.from_user.id)
    bot.answer_callback_query(call.id)
    _send_menu(call.message.chat.id)


@bot.message_handler(content_types=['document'])
def handle_document(message: types.Message):
    uid = message.from_user.id
    cid = message.chat.id
    session = get_session(uid)

    if not session or 'mode' not in session:
        bot.send_message(cid, "Please choose a converter first\\.", parse_mode='MarkdownV2',
                         reply_markup=KEYBOARD_MAIN)
        return

    doc = message.document
    if not doc.file_name.lower().endswith('.pdf'):
        bot.send_message(cid, "❌ Please send a PDF file\\.", parse_mode='MarkdownV2')
        return

    mode = session['mode']
    step = session.get('step', '')

    # ── ForumIAS: single PDF ──────────────────────────────────────────────────
    if mode == 'forumias' and step == 'waiting_sol':
        msg = bot.send_message(cid, "⏳ Downloading and processing your PDF\\.\\.\\. \\(30–60 sec\\)",
                               parse_mode='MarkdownV2')
        try:
            pdf_bytes = _download_file(doc.file_id)
            result = parse_forumias_pdf(pdf_bytes)
            if not result.strip():
                bot.edit_message_text(
                    "❌ No questions found\\. Make sure this is a text\\-based ForumIAS Solutions PDF\\.",
                    cid, msg.message_id, parse_mode='MarkdownV2')
                return
            q_count = result.count('\n😂\n')
            _send_result(cid, msg.message_id, result, doc.file_name, q_count, 50)
            clear_session(uid)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {_escape(str(e)[:300])}", cid, msg.message_id,
                                  parse_mode='MarkdownV2')
            clear_session(uid)
        return

    # ── Vajiram step 1: receive Test PDF ─────────────────────────────────────
    if mode == 'vajiram' and step == 'waiting_test':
        prog = bot.send_message(cid, "📥 Downloading Test PDF\\.\\.\\.", parse_mode='MarkdownV2')
        try:
            test_bytes = _download_file(doc.file_id)
            save_pdf(uid, 'test', test_bytes)           # save bytes to /tmp
            session['test_file_id'] = doc.file_id
            session['test_file_name'] = doc.file_name
            session['step'] = 'waiting_sol'
            set_session(uid, session)
            bot.edit_message_text(
                f"✅ Test PDF received: `{_escape(doc.file_name)}`\n\n"
                "Now send me the *Solutions / Answer Key PDF* \\(Step 2/2\\)\\.",
                cid, prog.message_id, parse_mode='MarkdownV2',
                reply_markup=_cancel_kb()
            )
        except Exception as e:
            bot.edit_message_text(f"❌ Could not download: {_escape(str(e)[:200])}",
                                  cid, prog.message_id, parse_mode='MarkdownV2')
        return

    # ── Vajiram step 2: receive Solution PDF ─────────────────────────────────
    if mode == 'vajiram' and step == 'waiting_sol':
        msg = bot.send_message(cid, "⏳ Processing both PDFs\\.\\.\\. \\(60–90 sec\\)",
                               parse_mode='MarkdownV2')
        try:
            # Load test PDF from /tmp (reliable) OR re-download by file_id
            test_bytes = load_pdf(uid, 'test')
            if not test_bytes:
                if session.get('test_file_id'):
                    test_bytes = _download_file(session['test_file_id'])
                else:
                    raise ValueError("Test PDF not found. Please start over with /start")
            sol_bytes = _download_file(doc.file_id)
            result = parse_vajiram(test_bytes, sol_bytes)
            if not result.strip():
                bot.edit_message_text(
                    "❌ No questions found\\. Make sure both PDFs are text\\-based Vajiram files\\.",
                    cid, msg.message_id, parse_mode='MarkdownV2')
                return
            q_count = result.count('\n😂\n')
            _send_result(cid, msg.message_id, result,
                         session.get('test_file_name', 'vajiram'), q_count, 100)
            clear_session(uid)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {_escape(str(e)[:300])}", cid, msg.message_id,
                                  parse_mode='MarkdownV2')
            clear_session(uid)
        return

    # ── VisionIAS step 1: receive Test PDF ───────────────────────────────────
    if mode == 'vision' and step == 'waiting_test':
        prog = bot.send_message(cid, "📥 Downloading Test PDF\\.\\.\\.", parse_mode='MarkdownV2')
        try:
            test_bytes = _download_file(doc.file_id)
            save_pdf(uid, 'test', test_bytes)           # save bytes to /tmp
            session['test_file_id'] = doc.file_id
            session['test_file_name'] = doc.file_name
            session['step'] = 'waiting_sol'
            set_session(uid, session)
            bot.edit_message_text(
                f"✅ Test PDF received: `{_escape(doc.file_name)}`\n\n"
                "Now send me the *Solution PDF* \\(with `Q 1\\.A` style answers\\) — Step 2/2\\.",
                cid, prog.message_id, parse_mode='MarkdownV2',
                reply_markup=_cancel_kb()
            )
        except Exception as e:
            bot.edit_message_text(f"❌ Could not download: {_escape(str(e)[:200])}",
                                  cid, prog.message_id, parse_mode='MarkdownV2')
        return

    # ── VisionIAS step 2: receive Solution PDF ────────────────────────────────
    if mode == 'vision' and step == 'waiting_sol':
        msg = bot.send_message(cid, "⏳ Processing both PDFs\\.\\.\\. \\(60–90 sec\\)",
                               parse_mode='MarkdownV2')
        try:
            test_bytes = load_pdf(uid, 'test')
            if not test_bytes:
                if session.get('test_file_id'):
                    test_bytes = _download_file(session['test_file_id'])
                else:
                    raise ValueError("Test PDF not found. Please start over with /start")
            sol_bytes = _download_file(doc.file_id)
            result = parse_vision(test_bytes, sol_bytes)
            if not result.strip():
                bot.edit_message_text(
                    "❌ No questions found\\. Make sure both PDFs are text\\-based VisionIAS files\\.",
                    cid, msg.message_id, parse_mode='MarkdownV2')
                return
            q_count = result.count('\n😂\n')
            _send_result(cid, msg.message_id, result,
                         session.get('test_file_name', 'vision'), q_count, 100)
            clear_session(uid)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {_escape(str(e)[:300])}", cid, msg.message_id,
                                  parse_mode='MarkdownV2')
            clear_session(uid)
        return

    bot.send_message(cid, "⚠️ Unexpected state\\. Use /start to begin again\\.",
                     parse_mode='MarkdownV2')
    clear_session(uid)


def _escape(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    for ch in r'_*[]()~`>#+-=|{}.!\\':
        text = text.replace(ch, '\\' + ch)
    return text


def _send_result(chat_id: int, processing_msg_id: int, result: str,
                 original_filename: str, q_count: int, expected: int):
    txt_bytes = result.encode('utf-8')
    base = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
    out_filename = f"{base}_CONVERTED.txt"

    icon = "✅" if q_count >= expected else "⚠️"
    note = ("All questions extracted successfully\\." if q_count >= expected
            else f"Only {q_count} questions found — review output carefully\\.")
    caption = (
        f"{icon} *Conversion Complete\\!*\n\n"
        f"📊 Questions: `{q_count}` / `{expected}`\n"
        f"📁 `{_escape(out_filename)}`\n\n_{note}_"
    )

    bot.edit_message_text(f"{icon} Done\\! Sending file\\…", chat_id, processing_msg_id,
                          parse_mode='MarkdownV2')
    bot.send_document(
        chat_id,
        document=io.BytesIO(txt_bytes),
        visible_file_name=out_filename,
        caption=caption,
        parse_mode='MarkdownV2',
        reply_markup=_back_to_menu_kb()
    )


@bot.message_handler(func=lambda m: True)
def handle_other(message: types.Message):
    uid = message.from_user.id
    session = get_session(uid)
    mode_names = {'forumias': 'ForumIAS SFG', 'vajiram': 'Vajiram & Ravi', 'vision': 'VisionIAS'}
    if session.get('mode'):
        step = session.get('step', '')
        step_hint = {
            'waiting_test': 'Waiting for Test PDF',
            'waiting_sol': 'Waiting for Solutions PDF',
        }.get(step, step)
        bot.send_message(
            message.chat.id,
            f"📎 I'm in *{_escape(mode_names.get(session['mode'], ''))}* mode\\.\n"
            f"Status: _{_escape(step_hint)}_\n\n"
            "Please send a PDF file, or /start to go back to the menu\\.",
            parse_mode='MarkdownV2'
        )
    else:
        _send_menu(message.chat.id)


def process_update(json_string: str):
    """Entry point called from the Vercel webhook handler."""
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
