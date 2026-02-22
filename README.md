# bot-discord-backup

A Python script for server administrators to create a best-effort offline backup of every channel, message, attachment, sticker, thread, and scheduled event from a Discord server (guild) using a bot account.

This tool is designed for personal archiving, server migration preparation, or recovery from potential data loss/raids/unanticipated policy changes on behalf of discord. It produces JSONL files + downloaded media, with every effort made to preserve metadata provided by discord.py

## Features

- Backs up all text channels, threads (active + archived, public + private)
- Captures every message field: content (raw & clean), embeds, reactions, attachments, stickers, polls, interaction metadata, references/replies, flags, pins, etc.
- Downloads attachments and stickers to a local folder
- Serializes scheduled events (name, times, description, recurrence, location, interested user count — optional)
- Uses NDJSON (.jsonl) format per channel/thread → easy to parse, stream, or import later
- Safe filename handling, dated backup folders, logging with progress
- Environment variable configuration (no hard-coded tokens)
- Handles rate limits reasonably (with room for improvement)

## Installation

1. Clone or download this repository

2. Create and activate a Conda environment (recommended):
   ```
   conda env create -f environment.yml
   conda activate discord-backup
   ```

3. Create a .env file in the project root:

```
# you may copy/paste/rename the `.env.template` file to `.env` filling in the appropriate values
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=123456789012345678   # Your server ID (right-click server → Copy Server ID)
```

## Running

- run `python backup.py`

## License

MIT License

Made with ❤️ for server owners who want to keep their history safe.
