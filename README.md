# RIYA AI Telegram Bot — Final

## Included features
- User `/start` menu with Rose, Love Chat, Joke, Naughty, Help and Channel buttons
- Admin Dashboard button for admins
- Admin dashboard: statistics, broadcast, add/remove admin, ban/unban, channel setup, group setup, admin list and bot status
- SQLite user/chat/admin tracking
- Bengali text and optional Bengali voice replies
- Random emoji reactions
- Automatic group activation when RIYA becomes an administrator
- Welcome handling for new group members
- Railway-ready deployment

## Railway Variables
Set these in Railway -> Variables:
- `BOT_TOKEN` = your Telegram BotFather token (keep only in Railway)
- `OWNER_ID` = your numeric Telegram user ID
- `ENABLE_VOICE=true`
- `REACTION_ENABLED=true`
- `DB_PATH=riya.db`

## Start command
`python riya_bot.py`

`railway.toml` already contains the start command.

## Telegram setup
1. Add RIYA to your group.
2. Promote RIYA to administrator.
3. Disable Group Privacy in BotFather if RIYA should receive ordinary group messages.
4. The bot automatically handles its own `my_chat_member` updates.

## GitHub safety
Never commit the real Bot Token. `.env` and runtime database files are ignored.
