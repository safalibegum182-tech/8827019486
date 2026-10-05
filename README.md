# RIYA AI Telegram Bot

## Railway setup

The Telegram bot token is kept only in Railway Variables. Do NOT put the real token in GitHub.

Required Railway Variables:

- `BOT_TOKEN` = your Telegram BotFather token
- `OWNER_ID` = your numeric Telegram user ID

Optional/default Variables:

- `ENABLE_VOICE=true`
- `REACTION_ENABLED=true`
- `DB_PATH=riya.db`

The repository includes `railway.toml`, so Railway has an explicit start command:

`python riya_bot.py`

## GitHub

Safe to upload this project to a private or public GitHub repository as long as you never add your real `.env` or token. `.gitignore` excludes local secrets and the SQLite runtime database.

## Telegram

For ordinary group messages, disable Group Privacy for the bot in BotFather. The bot also needs to be promoted to administrator in a group for the automatic group activation logic.

## Run locally

```bash
pip install -r requirements.txt
export BOT_TOKEN="YOUR_TOKEN"
export OWNER_ID="YOUR_NUMERIC_ID"
python riya_bot.py
```
