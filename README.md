# 🤖 UPSC PDF → TXT Converter Telegram Bot

A Telegram bot that converts UPSC test-series PDFs into perfectly formatted .txt files. Ported from the original HTML suite — same exact parsing logic, same output format, all running serverless on Vercel.

## 🎯 Features

- **⚡ ForumIAS SFG Converter** — Single PDF upload, extracts all 50 questions with ✅ answers and explanations
- **⚙️ Vajiram & Ravi Converter** — Two-column spatial parsing, processes test booklet + solutions PDF for all 100 questions
- **🔮 VisionIAS Converter** — Anchor-based option parsing, processes test + solution PDFs for all 100 questions

## 📁 Project Structure

```
upsc-bot/
├── api/
│   └── webhook.js          ← Vercel serverless function (Telegram webhook receiver)
├── lib/
│   ├── api.js              ← Telegram Bot API helpers
│   ├── bot.js              ← Main bot router & conversation logic
│   ├── sfg.js              ← ForumIAS SFG 50-Q parser
│   ├── vajiram.js          ← Vajiram 100-Q two-column parser
│   └── vision.js           ← VisionIAS 100-Q anchor-based parser
├── package.json
├── vercel.json
├── setup.js                ← One-time webhook registration script
├── .env.example            ← Environment variables template
└── README.md               ← You are here
```

## 🚀 Deploy to Vercel (Step by Step)

### 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts to name your bot
4. **Copy the bot token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Deploy to Vercel

#### Option A: Using Vercel CLI (Recommended)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Set environment variables
vercel env add BOT_TOKEN          # Paste your bot token
vercel env add VERCEL_URL         # Your vercel.app domain (e.g., my-bot.vercel.app)

# Register webhook
vercel run setup.js
```

#### Option B: Using Vercel Dashboard

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click **"New Project"**
3. Import this repository
4. Add environment variables:
   - `BOT_TOKEN` = your Telegram bot token
   - `VERCEL_URL` = your vercel.app domain (without `https://`)
5. Deploy

### 3. Register the Webhook

After deployment, run:

```bash
# With Vercel CLI
vercel run setup.js

# Or manually
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://<YOUR_VERCEL_URL>/api/webhook&allowed_updates=[\"message\",\"callback_query\"]"
```

### 4. Test Your Bot

1. Open Telegram
2. Search for your bot by username
3. Send `/start`
4. Choose a converter mode
5. Send a PDF file
6. Wait for processing
7. Download the formatted .txt file!

## 🔧 Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram Bot API token | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `VERCEL_URL` | Your Vercel deployment URL (without https://) | `my-bot-project.vercel.app` |

## 📝 Usage

```
/start      → Show main menu with converter options
/menu       → Return to main menu
/help       → Show help instructions

Then:
1. Select a converter mode (⚡ ForumIAS SFG / ⚙️ Vajiram / 🔮 VisionIAS)
2. Send PDF file(s) as document attachments
3. Bot processes and sends back a formatted .txt file
```

## 🎨 Output Format (Same as HTML Version)

```
Q1. In which one of the following regions was Dhanyakataka, which flourished as a prominent Buddhist centre under the Mahasanghikas, located?
😂
Andhra ✅
Gandhara
Kalinga
Magadha
Ex: Dharanikota is a town near Amaravati in the Guntur district of Andhra Pradesh in India. It is the site of the ancient Dhanyakataka which was the capital of the Satavahana kingdom, also known as Andhras which ruled in the Deccan around the 1st to 3rd centuries A.D.

Q2. With reference to the Gupta ruler Chandragupta II, consider the following statements:
1. Similar to Samudragupta, there are instances where the obverse of coins issued by him depicts him playing the vina/veena.
2. He is known by the epithet parama-bhagavata.
3. He entered into a matrimonial alliance with the Vakatakas of Deccan.
How many of the statements given above are correct?
😂
Only one
Only two ✅
All the three
None
Ex: Statement I is incorrect because there is no instance of Chandragupta II playing the veena depicted on his coins. Statement II is correct as Chandragupta II adopted epithets like parama-bhagavata and Vikramaditya. Statement III is correct as he secured his position by marrying his daughter Prabhavatigupta to the Vakataka king Rudrasena II.
```

## 📌 Notes

- **File size limit**: 50 MB per PDF (Telegram Bot API limit)
- **Processing time**: Usually completes in 10-30 seconds depending on PDF size
- **Serverless limits**: Vercel functions have a 10-second timeout for Hobby plan, 60 seconds for Pro
- **PDF requirements**: Must be text-based (selectable text), not scanned images
- **Sessions**: Session state is stored in memory per warm container — for heavy usage, consider adding Redis

## 🛠️ Tech Stack

- **Runtime**: Node.js 18+
- **Framework**: Vercel Serverless Functions
- **PDF Parser**: pdfjs-dist (Mozilla's PDF.js for Node.js)
- **Telegram API**: Raw HTTP calls (no heavy dependencies)
- **Deployment**: Vercel (free tier friendly)

## 📜 License

MIT
