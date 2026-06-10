# UPSC PDF → TXT Converter — Telegram Bot

Converts UPSC test PDFs into perfectly formatted `.txt` files via Telegram.  
Supports **ForumIAS SFG** (50Q), **Vajiram & Ravi** (100Q), and **VisionIAS** (100Q).

## Output Format

```
Q1.Question text here
1. Statement one
2. Statement two
Which of the statements given above is/are correct?
😂
Option A
Option B ✅
Option C
Option D
Ex: Full explanation from the solution PDF...

Q2.Next question...
```

---

## Deploy to Vercel in 5 Steps

### Step 1 — Create a Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** you receive

### Step 2 — Clone & deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd telegram-bot
vercel
```

### Step 3 — Set Environment Variables in Vercel Dashboard

Go to your project → **Settings → Environment Variables** and add:

| Variable | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `WEBHOOK_SECRET` | Any random string (e.g. `my_secret_abc123`) |

Redeploy after adding variables: `vercel --prod`

### Step 4 — Register the Webhook

```bash
TELEGRAM_BOT_TOKEN=your_token \
VERCEL_URL=https://your-app.vercel.app \
WEBHOOK_SECRET=my_secret_abc123 \
python setup_webhook.py
```

### Step 5 — Test the Bot

Open your bot in Telegram and send `/start`.

---

## How to Use the Bot

| Mode | PDFs Required | Command |
|---|---|---|
| ForumIAS SFG | Solutions PDF only | `/start` → ⚡ ForumIAS |
| Vajiram & Ravi | Test PDF + Solutions PDF | `/start` → ⚙️ Vajiram |
| VisionIAS | Test PDF + Solutions PDF | `/start` → 🔮 VisionIAS |

---

## Local Development

```bash
pip install -r requirements.txt

# Set env vars
export TELEGRAM_BOT_TOKEN=your_token
export WEBHOOK_SECRET=my_secret

# Run locally (for testing parsers)
python -c "
from bot.parsers import parse_forumias_pdf
with open('test.pdf','rb') as f:
    print(parse_forumias_pdf(f.read())[:500])
"
```

---

## Notes

- PDFs must be **text-based** (not scanned images)
- Processing time: 30–90 seconds depending on PDF size
- Maximum file size: 20 MB (Telegram Bot API limit)
- Session state is stored in `/tmp` — resets if the Vercel instance cold-starts
