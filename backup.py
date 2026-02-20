import discord
import asyncio
import json
import os
import aiohttp
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

import aiofiles  # pip install aiofiles

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

# Load configuration from environment variables
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set.")

try:
    GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', '0'))
    if GUILD_ID == 0:
        raise ValueError
except ValueError:
    raise ValueError("DISCORD_GUILD_ID environment variable is not set or is not a valid integer.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)


async def download_file(session: aiohttp.ClientSession, url: str, path: Path) -> None:
    """Download a file asynchronously with a shared session for efficiency."""
    logging.warning("skipped downloading file, stop skipping before running actual backup")
    return
    async with session.get(url) as resp:
        if resp.status == 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(path, 'wb') as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    await f.write(chunk)


def serialize_permissions(value: int) -> Dict[str, Any]:
    """Return dict with raw bitfield + readable named permissions."""
    if value == 0:
        return {'raw_flag_value': 0, 'named_permissions': {}}
    
    perms = discord.Permissions(value)
    named_permissions = {name: True for name, value in perms if value is True}
    
    return {
        'raw_flag_value': value,
        'named_permissions': named_permissions
    }


def sanitize_filename(name: str) -> str:
    """Sanitize channel/thread name for filesystem safety."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def serialize_interaction_metadata(
    metadata: Optional[discord.MessageInteractionMetadata]
) -> Optional[Dict[str, Any]]:
    """
    Convert discord.MessageInteractionMetadata → plain dict suitable for JSON.
    
    Returns None if input is None.
    Explicitly maps every relevant public field to basic types.
    """
    if metadata is None:
        return None

    result: Dict[str, Any] = {
        # Core command/interaction identifiers
        "type": metadata.type.value if metadata.type else None,  # int (ApplicationCommandType)
        "command_name": metadata.command_name if hasattr(metadata, 'command_name') else None,
        "command_id": metadata.command_id if hasattr(metadata, 'command_id') else None,
        
        # Original message this interaction responded to (ephemeral/followup related)
        "original_response_message_id": metadata.original_response_message_id,
        
        # Who triggered it
        "user_id": metadata.user.id if metadata.user else None,
        "user": (
            {
                "id": metadata.user.id,
                "username": metadata.user.name,
                "global_name": metadata.user.global_name,
                "display_name": metadata.user.display_name,
                # discriminator only exists in older user objects; safe to include conditionally
                "discriminator": getattr(metadata.user, "discriminator", None),
            }
            if metadata.user
            else None
        ),
        
        # Context menu / message / user targets
        "target_user_id": (
            metadata.target_user.id if metadata.target_user else None
        ),
        "target_message_id": metadata.target_message_id,
        "target_channel_id": metadata.target_channel_id if hasattr(metadata, 'target_channel_id') else None,
        
        # Location context
        "guild_id": metadata.guild_id if hasattr(metadata, 'guild_id') else None,
        "channel_id": metadata.channel_id if hasattr(metadata, 'channel_id') else None,
        
        # Permissions & locale
        "app_permissions": (
            metadata.app_permissions.value if (hasattr(metadata, 'app_permissions') and metadata.app_permissions) else None
        ),
        "locale": metadata.locale if hasattr(metadata, 'locale') else None,           # user's locale string
        "guild_locale": metadata.guild_locale if hasattr(metadata, 'guild_locale') else None,  # server's locale or None
    }

    # Optional: Clean up None values if you prefer a more compact dict
    # (uncomment if desired)
    # result = {k: v for k, v in result.items() if v is not None}

    return result


def serialize_message(message: discord.Message) -> dict[str, Any]:
    """Serialize a discord.Message into a rich dictionary."""
    return {
        'id': message.id,
        'author': {
            'id': message.author.id if message.author else None,
            'username': message.author.name if message.author else None,
            'display_name': message.author.display_name if message.author else None,
            'global_name': message.author.global_name if message.author else None,
            'is_bot': message.author.bot if message.author else None,
        },
        'content': message.content,
        'clean_content': message.clean_content,
        'system_content': message.system_content or None,
        'timestamp': message.created_at.isoformat(),
        'edited_timestamp': message.edited_at.isoformat() if message.edited_at else None,
        'type': str(message.type),
        'jump_url': message.jump_url,
        'pinned': message.pinned,
        'tts': message.tts,
        'mention_everyone': message.mention_everyone,
        'flags': message.flags.value,
        'webhook_id': message.webhook_id,
        'reference': {
            'message_id': message.reference.message_id if message.reference else None,
            'channel_id': message.reference.channel_id if message.reference else None,
            'guild_id': message.reference.guild_id if message.reference else None,
        } if message.reference else None,
        'reactions': [{'emoji': str(r.emoji), 'count': r.count} for r in message.reactions],
        'attachments': [],
        'stickers': [],
        'embeds': [embed.to_dict() for embed in message.embeds],
        'components': [component.to_dict() for component in message.components],
        'poll': message.poll._to_dict() if message.poll else None, # TODO this is a private method, might be deprecated/break in the future, replace as necessary with own function (see sereialize_interaction_metadata)
        'interaction_metadata': serialize_interaction_metadata(message.interaction_metadata),
        'thread_started': message.thread.id if message.thread else None,
    }


async def backup_messagable(
    messagable: discord.abc.Messageable,
    backup_dir: Path,
    attachments_dir: Path,
    session: aiohttp.ClientSession,
) -> None:
    """Backup all messages from a messageable (TextChannel or Thread)."""
    if not (
        messagable.permissions_for(messagable.guild.me).view_channel and
        messagable.permissions_for(messagable.guild.me).read_message_history
    ):
        logging.warning('Skipping #%s (insufficient permissions)', messagable.name)
        return

    safe_name = sanitize_filename(getattr(messagable, 'name', 'unknown'))
    channel_file = backup_dir / f'{messagable.id}-{safe_name}_messages.jsonl'

    logging.info('Backing up #%s (ID: %s)', messagable.name, messagable.id)

    count = 0
    media_id = 0

    try:
        async with aiofiles.open(channel_file, 'w', encoding='utf-8') as messages_file_handle:
            async for message in messagable.history(limit=None, oldest_first=True):
                msg_data = serialize_message(message)

                # Attachments
                for attachment in message.attachments:
                    ext = attachment.filename.split('.')[-1] if '.' in attachment.filename else 'file'
                    saved_name = f'attach_{messagable.id}_{message.id}_{media_id}.{ext}'
                    saved_path = attachments_dir / saved_name
                    await download_file(session, attachment.url, saved_path)

                    msg_data['attachments'].append({
                        'original_name': attachment.filename,
                        'saved_as': saved_name,
                        'url': attachment.url,
                        'size': attachment.size,
                    })
                    media_id += 1

                # Stickers
                for sticker in message.stickers:
                    ext = sticker.format.name.lower()
                    saved_name = f'sticker_{sticker.id}_{media_id}.{ext}'
                    saved_path = attachments_dir / saved_name
                    await download_file(session, sticker.url, saved_path)

                    msg_data['stickers'].append({
                        'id': sticker.id,
                        'name': sticker.name,
                        'format': sticker.format.name,
                        'saved_as': saved_name,
                        'url': sticker.url,
                    })
                    media_id += 1

                await messages_file_handle.write(json.dumps(msg_data, ensure_ascii=False) + '\n')
                count += 1

                if count % 1000 == 0:
                    logging.info('  Processed %s messages from #%s...', count, messagable.name)

        logging.info('Finished #%s — %s messages total', messagable.name, count)

        try:
            pinned_messages = await messagable.pins()
            if pinned_messages:
                pinned_data = [serialize_message(msg) for msg in pinned_messages]

                pins_file = backup_dir / f'{messagable.id}-{safe_name}_pinned.jsonl'
                async with aiofiles.open(pins_file, 'w', encoding='utf-8') as pinned_file_handle:
                    for msg in pinned_messages:
                        msg_data = serialize_message(msg)
                        await pinned_file_handle.write(json.dumps(msg_data, ensure_ascii=False) + '\n')

                logging.info('Saved %d currently pinned messages for #%s', len(pinned_messages), messagable.name)
            else:
                logging.debug('No pinned messages in #%s', messagable.name)
        except discord.Forbidden:
            logging.warning('Cannot fetch pinned messages in #%s (missing View Channel or Read History permission)', messagable.name)
        except discord.HTTPException as e:
            if e.status == 429:
                logging.warning('Rate limited while fetching pins in #%s — skipping pins snapshot', messagable.name)
            else:
                logging.warning('HTTP error fetching pins in #%s: %s', messagable.name, e)
        except Exception as e:
            logging.exception('Unexpected error fetching pins in #%s', messagable.name)
            
        # Snapshot of who can VIEW / READ / SEND in this channel (permission-based)
        try:
            if not hasattr(messagable, 'overwrites'):
                logging.debug('No permission overrides available for %s (likely thread)', messagable.name)
            else:
                viewer_overrides = []
                # @everyone base
                everyone = messagable.guild.default_role
                everyone_perms = messagable.permissions_for(everyone)
                viewer_overrides.append({
                    'type': 'role',
                    'id': everyone.id,
                    'name': '@everyone',
                    'allow': serialize_permissions(everyone_perms.value),
                    'effective_view_channel': everyone_perms.view_channel,
                    'effective_read_history': everyone_perms.read_message_history,
                    'effective_send_messages': everyone_perms.send_messages,
                })

                # Role & user overrides
                for target, overwrite in messagable.overwrites.items():
                    allow, deny = overwrite.pair()  # Returns (Permissions, Permissions)

                    allow_perms = serialize_permissions(allow.value)
                    deny_perms = serialize_permissions(deny.value)

                    # Effective permissions (allow wins over deny if set)
                    effective_view = allow.view_channel if allow.view_channel is not None else not deny.view_channel
                    effective_read = allow.read_message_history if allow.read_message_history is not None else not deny.read_message_history
                    effective_send = allow.send_messages if allow.send_messages is not None else not deny.send_messages

                    entry = {
                        'type': 'role' if isinstance(target, discord.Role) else 'user',
                        'id': target.id,
                        'name': target.name if isinstance(target, discord.Role) else target.display_name,
                        'allow': allow_perms,
                        'deny': deny_perms,
                        'effective_view_channel': effective_view,
                        'effective_read_history': effective_read,
                        'effective_send_messages': effective_send,
                    }
                    viewer_overrides.append(entry)

                if viewer_overrides:
                    viewers_file = backup_dir / f'{messagable.id}-{safe_name}_access.jsonl'
                    async with aiofiles.open(viewers_file, 'w', encoding='utf-8') as access_file_handle:
                        for override in viewer_overrides:
                            await access_file_handle.write(json.dumps(override, ensure_ascii=False) + '\n')
                    logging.info('Saved channel access snapshot (%d entries) for #%s', len(viewer_overrides), messagable.name)

        except Exception as e:
            logging.warning('Error snapshotting channel access in #%s: %s', messagable.name, e)

    except Exception as e:
        logging.exception('Error backing up #%s', messagable.name)


@client.event
async def on_ready():
    logging.info('Logged in as %s — starting backup', client.user)

    guild = client.get_guild(GUILD_ID)
    if not guild:
        logging.error('Guild not found — check GUILD_ID')
        await client.close()
        return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = Path('backup') / f'{guild.name}_{timestamp}'
    attachments_dir = backup_dir / 'attachments'
    attachments_dir.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        # Regular text channels (including announcement channels)
        for channel in guild.text_channels:
            await backup_messagable(channel, backup_dir, attachments_dir, session)

        # Active threads (covers threads from both text channels and forums)
        logging.info('Backing up active threads...')
        for thread in guild.threads:
            await backup_messagable(thread, backup_dir, attachments_dir, session)

        # Archived threads (public and private) — iterate over possible parents
        logging.info('Backing up archived threads...')
        parents = [c for c in guild.channels if isinstance(c, (discord.TextChannel, discord.ForumChannel))]
        for parent in parents:
            # Public archived
            try:
                async for thread in parent.archived_threads(limit=None):
                    await backup_messagable(thread, backup_dir, attachments_dir, session)
            except discord.Forbidden:
                pass
            except Exception as e:
                logging.warning('Error fetching public archived threads in %s: %s', parent.name, e)

            # Private archived
            try:
                async for thread in parent.archived_threads(limit=None, private=True):
                    await backup_messagable(thread, backup_dir, attachments_dir, session)
            except discord.Forbidden:
                pass
            except Exception as e:
                logging.warning('Error fetching private archived threads in %s: %s', parent.name, e)

        
        # Backup all scheduled events (current and past, if available)
        logging.info('Backing up guild scheduled events...')
        events_dir = backup_dir / 'scheduled_events'
        events_dir.mkdir(exist_ok=True)

        try:
            events = await guild.fetch_scheduled_events(with_counts=True)  # Fetches all, including interested user counts
            for event in events:
                event_data = {
                    'id': event.id,
                    'name': event.name,
                    'description': event.description,
                    'scheduled_start_time': event.start_time.isoformat() if event.start_time else None,
                    'scheduled_end_time': event.end_time.isoformat() if event.end_time else None,
                    'status': str(event.status),  # Scheduled, Active, Completed, Canceled
                    'entity_type': str(event.entity_type),  # Voice, Stage, External
                    'channel_id': event.channel_id,
                    'creator_id': event.creator_id,
                    'user_count': event.user_count,  # Interested users (if with_user_count=True)
                    'privacy_level': str(event.privacy_level),
                    'image': event.image_url if hasattr(event, 'image_url') else None,  # Cover image URL if set
                    # Recurrence (if repeating event)
                    'recurrence_rule': (
                        {
                            'frequency': str(event.recurrence_rule.freq) if event.recurrence_rule else None,
                            'interval': event.recurrence_rule.interval if event.recurrence_rule else None,
                            'by_weekday': [str(d) for d in event.recurrence_rule.by_weekday] if event.recurrence_rule and event.recurrence_rule.by_weekday else None,
                            'by_month': event.recurrence_rule.by_month if event.recurrence_rule else None,
                            'by_month_day': event.recurrence_rule.by_month_day if event.recurrence_rule else None,
                            'end': event.recurrence_rule.end.isoformat() if event.recurrence_rule and event.recurrence_rule.end else None,
                        }
                        if hasattr(event, 'recurrence_rule') and event.recurrence_rule
                        else None
                    ),
                    # Metadata for external events
                    'entity_metadata': {
                        'location': event.entity_metadata.location if event.entity_metadata else None,
                    } if hasattr(event, 'entity_metadata') else None,
                }

                event_file = events_dir / f'event_{event.id}.json'
                async with aiofiles.open(event_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(event_data, ensure_ascii=False, indent=2))

            logging.info(f'Backed up {len(events)} scheduled events to {events_dir}')
        except Exception as e:
            logging.exception('Error fetching scheduled events')
    
    # ── Backup guild roles ──
    logging.info('Backing up guild roles...')
    roles_dir = backup_dir / 'roles'
    roles_dir.mkdir(exist_ok=True)

    try:
        roles_list = []
        for role in guild.roles:
            role_data = {
                'id': role.id,
                'name': role.name,
                'color': role.color.value,
                'hoist': role.hoist,
                'position': role.position,
                'permissions': serialize_permissions(role.permissions.value),  # ← now uses helper with raw + granted
                'mentionable': role.mentionable,
                'managed': role.managed,
                'is_default': role.is_default(),
                'created_at': role.created_at.isoformat() if role.created_at else None,
            }
            roles_list.append(role_data)

        roles_file = roles_dir / 'guild_roles.jsonl'
        async with aiofiles.open(roles_file, 'w', encoding='utf-8') as f:
            for role_data in roles_list:
                await f.write(json.dumps(role_data, ensure_ascii=False) + '\n')
        logging.info(f'Backed up {len(roles_list)} roles to {roles_file}')

    except Exception as e:
        logging.exception('Error backing up guild roles')


    # ── Backup guild members (full list) ──
    logging.info('Backing up guild members...')
    members_dir = backup_dir / 'members'
    members_dir.mkdir(exist_ok=True)

    try:
        # Force full member list load for large guilds
        if guild.large or len(guild.members) < guild.member_count - 50:
            logging.info('Guild is large or cache incomplete — chunking members...')
            await guild.chunk()  # Triggers Discord to send all members via gateway
            # Wait a bit for chunks to arrive (adjust as needed)
            await asyncio.sleep(5)  # Give time; may need more for huge guilds

        members_list = []
        for member in guild.members:
            member_data = {
                'id': member.id,
                'name': member.name,
                'global_name': member.global_name,
                'display_name': member.display_name,
                'discriminator': member.discriminator if hasattr(member, 'discriminator') else None,
                'joined_at': member.joined_at.isoformat() if member.joined_at else None,
                'created_at': member.created_at.isoformat() if member.created_at else None,
                'bot': member.bot,
                'premium_since': member.premium_since.isoformat() if member.premium_since else None,
                'roles': [role.id for role in member.roles],
                'top_role_id': member.top_role.id if member.top_role else None,
                'status': str(member.status),
                'flags': member.public_flags.value if member.public_flags else None,
                'communication_disabled_until': member.communication_disabled_until.isoformat() if hasattr(member, 'communication_disabled_until') else None,
                'avatar_url': member.avatar.url if member.avatar else None,
            }
            members_list.append(member_data)

        if members_list:
            members_file = members_dir / 'guild_members.jsonl'
            async with aiofiles.open(members_file, 'w', encoding='utf-8') as f:
                for member_data in members_list:
                    await f.write(json.dumps(member_data, ensure_ascii=False) + '\n')
            logging.info(f'Backed up {len(members_list)} members to {members_file}')
        else:
            logging.warning('No members loaded — ensure Members Intent is enabled in portal and code')

    except discord.Forbidden:
        logging.warning('Cannot fetch members (Members Intent or permissions missing)')
    except discord.HTTPException as e:
        logging.warning(f'HTTP error during member chunk/fetch: {e}')
    except Exception as e:
        logging.exception('Unexpected error backing up guild members')
        
        
    logging.info('Full backup complete! Files saved to: %s', backup_dir)
    await client.close()

if __name__ == "__main__":
    client.run(TOKEN)