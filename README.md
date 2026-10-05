# RIYA Telegram Bot

## Railway Variables
Set these in Railway -> Variables:

- `BOT_TOKEN` = your Telegram BotFather token (keep this only in Railway)
- `OWNER_ID` = your numeric Telegram user ID
- `ENABLE_VOICE=true`
- `REACTION_ENABLED=true`
- `DB_PATH=riya.db`

## Start command
`railway.toml` already sets:

`python riya_bot.py`

## Telegram group setup
1. Add RIYA to your group.
2. Promote RIYA to administrator.
3. Disable Group Privacy in BotFather if you want RIYA to receive ordinary group messages.
4. RIYA will automatically activate group mode when it becomes an administrator.

## GitHub safety
Do not commit the real bot token. `.env` and runtime database files are ignored.

## Local run
```bash
pip install -r requirements.txt
export BOT_TOKEN="YOUR_TOKEN"
export OWNER_ID="YOUR_NUMERIC_ID"
python riya_bot.py
```
