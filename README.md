# bot-discord-backup

A Python script for server administrators to create a best-effort offline backup of every channel, message, attachment, sticker, thread, and scheduled event from a Discord server (guild) using a bot account.

This tool is designed for personal archiving, server migration preparation, or recovery from potential data loss, raids, or unanticipated policy changes by Discord. It produces JSONL files + downloaded media, with every effort made to preserve metadata provided by discord.py.

## Features

- Backs up all text channels, threads (active + archived, public + private)
- Captures every message field: content (raw & clean), embeds, reactions, attachments, stickers, polls, interaction metadata, references/replies, flags, pins, etc.
- Downloads attachments and stickers to a local folder
- Serializes scheduled events (name, times, description, recurrence, location, interested user count — optional)
- Uses NDJSON (.jsonl) format per channel/thread → easy to parse, stream, or import later
- Safe filename handling, dated backup folders, logging with progress
- Environment variable configuration (no hard-coded tokens)
- Handles rate limits reasonably (with room for improvement)

## Requirements

- Python 3.10+ (tested with 3.12)
- discord.py 2.6.4 (or compatible)
- Other dependencies: aiohttp, aiofiles, python-dotenv (listed in `environment.yml`)

## Installation

1. Clone or download this repository:

```
git clone https://github.com/praetorlabs/bot-discord-backup.git
cd bot-discord-backup
```

2. Create and activate a Conda environment (recommended):

```
conda env create -f environment.yml
conda activate discord-backup
```

Alternatively, install dependencies manually:

```
pip install -r requirements.txt
```

3. Create a `.env` file in the project root (copy from `.env.template` and fill in):

```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=123456789012345678  # Your server ID (right-click server → Copy Server ID)
```

**Note**: Ensure your bot has the necessary intents enabled in the Discord Developer Portal (Members and Message Content) and is invited to the server with read permissions for channels/history.

## Usage

Run the script:

```
python backup.py
```

- Backups are saved to a timestamped folder in `./backup/` (e.g., `ServerName_YYYYMMDD_HHMMSS`).
- Logs progress and any errors to console.
- To skip media downloads (for testing), uncomment the skip line in `download_file()`.

## Output Structure

- `attachments/`: Downloaded files (attachments + stickers)
- `channels/text/`: Text channel messages (.jsonl), pinned (.jsonl), permissions (.jsonl), members_effective (.jsonl)
- `channels/voice/`: Voice channel members (.jsonl), messages (.jsonl if text chat), etc.
- `channels/threads/`: Thread messages (.jsonl), etc.
- `conf/`: Guild metadata (.json), members (.jsonl), roles (.jsonl), channels_metadata (.jsonl)
- `scheduled_events/`: Event files (.json)

## Limitations

- Does not back up voice audio (impossible via bot API).
- Polls use a private discord.py method (TODO: custom serializer).
- Large guilds may hit rate limits—run during off-peak or add retries.
- Bot must have View Channel/Read History permissions everywhere.
- No restore functionality (export-only).

## Contributing

Pull requests welcome! For major changes, open an issue first. Focus on robustness, async efficiency, and metadata completeness.

## License

MIT License

Made with ❤️ for server owners who want to keep their history safe.
