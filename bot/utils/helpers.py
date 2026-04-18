import asyncio
from pyrogram import Client
from pyrogram.errors import RPCError
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from .i18n import i18n
from ..database.database import db
import logging

try:
    from pyromod.exceptions import ListenerStopped
except ImportError:
    class ListenerStopped(Exception): pass

logger = logging.getLogger(__name__)

def is_admin_or_owner(client: Client, user_id: int, user_model = None) -> bool:
    """Check if a user is an admin or the owner of the current bot instance."""
    from ..config import config
    
    # Global owner always has access
    if user_id == config.telegram.owner_id:
        return True
        
    # Check if user is an admin in this bot's context
    if user_model and getattr(user_model, "is_admin", False):
        return True
        
    # Check if this is a clone and the user is the clone owner
    if getattr(client, "is_clone", False):
        if user_id == getattr(client, "clone_owner_id", None):
            return True
            
    return False

async def get_input(client: Client, callback: CallbackQuery, prompt_text: str, lang: str):
    """
    Helper to get user input by editing the current message and adding a cancel button.
    Uses pyromod's listen() to wait for a message from the user.
    """
    cancel_btn = InlineKeyboardButton(i18n.get("btn_cancel", lang=lang, skip_emojis=True), callback_data="cancel_setting")
    keyboard = InlineKeyboardMarkup([[cancel_btn]])
    
    try:
        await callback.edit_message_text(prompt_text, reply_markup=keyboard)
    except Exception:
        pass
    
    try:
        msg = await callback.from_user.listen(timeout=300)
        if msg:
            # Delete user message to keep chat clean
            try: await msg.delete()
            except: pass

            if getattr(msg, "text", None) == "/cancel":
                return None
            return msg
    except asyncio.TimeoutError:
        try:
            await callback.message.reply_text(i18n.get("error_timeout", lang=lang, default="Temps d'attente écoulé. ⏱"))
        except: pass
        return None
    except ListenerStopped:
        return None
    except Exception as e:
        logger.error(f"Error in get_input ({type(e).__name__}): {e}")
        return None
    
    return None
async def get_channel_info(client: Client, message: Message):
    """
    Extracts channel title and calculates an invite link if possible.
    Works with forwarded messages or usernames/links in message text.
    Returns (title, link) or (None, None).
    """
    chat = None
    if message.forward_from_chat:
        chat = message.forward_from_chat
    elif message.text:
        text = message.text.strip()
        if text.startswith("@") or "t.me/" in text or text.isdigit() or text.startswith("-100"):
            try:
                chat = await client.get_chat(text)
            except:
                pass
        else:
            # Treat as manual name if no obvious link/username
            return text, None
            
    if chat:
        title = getattr(chat, "title", "Canal")
        link = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
        if not link:
            try:
                invite = await client.export_chat_invite_link(chat.id)
                link = invite
            except:
                pass
        return title, link
        
    return None, None

def get_next_pub_time(ad_schedule_times, ad_schedule_days, tz_name="UTC"):
    """Calculates the next scheduled publication time string."""
    import pendulum
    try:
        now = pendulum.now(tz_name)
    except:
        now = pendulum.now("UTC")
        
    if not ad_schedule_times or not ad_schedule_days:
        return "N/A"
        
    found = False
    for i in range(8): # Check up to 7 days ahead
        day = now.add(days=i)
        if day.day_of_week in ad_schedule_days:
            for t_str in sorted(ad_schedule_times):
                try:
                    h, m = map(int, t_str.split(":"))
                    t_dt = day.set(hour=h, minute=m, second=0)
                    if t_dt > now:
                        return t_dt.format("HH:mm (DD/MM)")
                except: continue
    return "N/A"

async def handle_channel_failure(client: Client, channel_id: int, bot_id: int = None):
    """Increments failure count, warns owner, and bans if threshold reached."""
    if bot_id is None:
        bot_id = client.me.id
        
    ch_data = await db.report_channel_failure(channel_id, bot_id)
    if not ch_data: 
        return
    
    # Use owner_id for notifications
    owner_id = ch_data.owner_id
    if not owner_id:
        return
        
    user = await db.get_user(owner_id, bot_id)
    lang = user.language if user else "fr"
    
    if ch_data.failure_count >= 3:
        await db.ban_channel(channel_id, bot_id)
        msg = i18n.get("msg_channel_banned", lang=lang, title=ch_data.title)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.get("btn_support", lang=lang), callback_data="start_support")]])
        try:
            await client.send_message(owner_id, msg, reply_markup=keyboard)
            logging.info(f"Channel {ch_data.title} ({channel_id}) BANNED after 3 failures.")
        except RPCError as e:
            logging.warning(f"Telegram RPC error notifying owner {owner_id} about ban: {e}")
        except Exception as e:
            logging.warning(f"Unexpected error notifying owner {owner_id} about ban: {e}", exc_info=True)
    else:
        msg = i18n.get("msg_channel_failure_warning", lang=lang, title=ch_data.title, count=ch_data.failure_count)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.get("btn_support", lang=lang), callback_data="start_support")]])
        try:
            await client.send_message(owner_id, msg, reply_markup=keyboard)
            logging.info(f"Channel {ch_data.title} ({channel_id}) Warned (Failure {ch_data.failure_count}/3).")
        except RPCError as e:
            logging.warning(f"Telegram RPC error notifying owner {owner_id} about failure: {e}")
        except Exception as e:
            logging.warning(f"Unexpected error notifying owner {owner_id} about failure: {e}", exc_info=True)

async def preload_peers(client: Client, bot_id: int = None):
    """
    On startup, resolve all active channels to ensure Pyrogram recognizes them.
    This prevents 'Peer id invalid' errors after bot restart.
    """
    if bot_id is None:
        bot_id = client.me.id
        
    logger.info(f"Preloading peer entities for active channels of bot {bot_id}...")
    try:
        channels = await db.get_all_active_channels(bot_id)
        for ch in channels:
            try:
                # Try to resolve by username first if available, it's more robust for initial cache
                target = f"@{ch.username}" if getattr(ch, "username", None) else ch.channel_id
                await client.get_chat(target)
                await asyncio.sleep(0.5) # Avoid flood
            except RPCError as e:
                 logger.warning(f"Telegram error preloading peer {ch.channel_id}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error preloading peer {ch.channel_id} ({type(e).__name__}): {e}")
        
        # Also preload log channel and owner
        from ..config import config
        for extra_id in [config.telegram.log_channel_id, config.telegram.owner_id]:
            if extra_id:
                try:
                    await client.get_chat(extra_id)
                except: pass
                
        logger.info(f"Preloaded {len(channels)} channels.")
    except Exception as e:
        logger.error(f"Error during peer preloading: {e}", exc_info=True)

async def send_promo_to_channel(client: Client, chat_id: int, text: str, parse_mode, reply_markup, ad=None):
    """
    Sends a promotional message with media if available.
    Handles retries for peer resolution issues.
    """
    media_id = getattr(ad, "media_id", None) if ad else None
    media_type = getattr(ad, "media_type", "photo") if ad else None
    
    async def _send():
        if media_id:
            if media_type == "photo":
                return await client.send_photo(chat_id, media_id, caption=text, parse_mode=parse_mode, reply_markup=reply_markup)
            elif media_type == "video":
                return await client.send_video(chat_id, media_id, caption=text, parse_mode=parse_mode, reply_markup=reply_markup)
            elif media_type == "animation":
                return await client.send_animation(chat_id, media_id, caption=text, parse_mode=parse_mode, reply_markup=reply_markup)
            elif media_type == "document":
                return await client.send_document(chat_id, media_id, caption=text, parse_mode=parse_mode, reply_markup=reply_markup)
        
        return await client.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=True)

    try:
        return await _send()
    except (RPCError, ValueError, KeyError) as e:
        if isinstance(e, (ValueError, KeyError)):
             # One retry with peer resolution
             try:
                 await client.get_chat(chat_id)
                 return await _send()
             except: raise e
        else: raise e

async def set_commands(client: Client):
    """Sets the bot commands for the given client in multiple languages."""
    from pyrogram.types import BotCommand
    
    # Default languages supported
    langs = ["fr", "en"]
    
    # Set default commands first (no language_code)
    try:
        default_cmds = [
            BotCommand("start", i18n.get("cmd_start_desc", lang="fr")),
            BotCommand("help", i18n.get("cmd_help_desc", lang="fr")),
            BotCommand("close", i18n.get("cmd_close_desc", lang="fr")),
        ]
        await client.set_bot_commands(default_cmds)
        
        # Now set for each specific language
        for l in langs:
            lang_cmds = [
                BotCommand("start", i18n.get("cmd_start_desc", lang=l)),
                BotCommand("help", i18n.get("cmd_help_desc", lang=l)),
                BotCommand("close", i18n.get("cmd_close_desc", lang=l)),
            ]
            await client.set_bot_commands(lang_cmds, language_code=l)
            
        logger.info(f"Localized bot commands set for @{client.me.username}")
    except Exception as e:
        logger.error(f"Failed to set localized bot commands for @{client.me.username}: {e}")

def get_system_info() -> str:
    """
    Returns a string containing basic system information.
    """
    import platform
    import sys
    import pyrogram
    
    os_name = platform.system()
    os_release = platform.release()
    py_version = sys.version.split()[0]
    pyro_version = pyrogram.__version__
    
    # Layer is often in pyrogram.session.auth.Auth.LAYER or similar
    # In many pyrogram versions it's also available in raw module
    try:
        from pyrogram.raw.all import LAYER
        pyro_layer = LAYER
    except ImportError:
        pyro_layer = "N/A"
        
    return f"{os_name} {os_release} | Python {py_version} | Pyrogram v{pyro_version} (Layer {pyro_layer})"

def get_uptime(start_time: float) -> str:
    """
    Returns a human readable uptime string.
    """
    import time
    delta = int(time.time() - start_time)
    
    days, remainder = divmod(delta, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    if seconds > 0 or not parts: parts.append(f"{seconds}s")
    
    return " ".join(parts)
