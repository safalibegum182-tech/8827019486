# RIYA Bot FINAL

## Automatic Group Activation
No `/setupgroup` command is needed.

When RIYA is promoted to **Administrator** in a group/supergroup:
- 👑 Group mode automatically turns ON
- 💬 RIYA replies to ordinary text messages
- ✨ RIYA tries to add random emoji reactions
- 🎉 RIYA sends an activation message

If RIYA is demoted or removed, group mode automatically turns OFF.

## Required hosting Variables
BOT_TOKEN=YOUR_NEW_TELEGRAM_BOT_TOKEN
OWNER_ID=YOUR_NUMERIC_TELEGRAM_USER_ID

Optional:
ENABLE_VOICE=true
REACTION_ENABLED=true
DB_PATH=riya.db

## Files
- riya_bot.py
- requirements.txt
- start.sh
- README.md

## Run
pip install -r requirements.txt
python riya_bot.py

## Important Telegram settings
For the bot to receive ordinary group messages, disable Group Privacy for the bot in BotFather.

Do NOT put the bot token inside the Python source code.
Use a newly generated token if an old token was ever exposed.
