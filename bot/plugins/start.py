from pyrogram import Client, filters, enums, StopPropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from ..database.database import db
from ..database.models import User
from ..utils.i18n import i18n
from ..config import config
from .. import hub_app

import logging

logger = logging.getLogger(__name__)

from ..utils.menu import Menu

menu = Menu()

@Client.on_message(group=-1)
async def check_banned_message(client: Client, message: Message):
    try:
        if message.from_user:
            user = await db.get_user(message.from_user.id, client.me.id)
            if user and getattr(user, "is_banned", False):
                logger.info(f"Stop Propagation for banned user {message.from_user.id}")
                raise StopPropagation
    except StopPropagation:
        raise
    except Exception as e:
        logger.error(f"Error in check_banned_message: {e}")

@Client.on_callback_query(group=-1)
async def check_banned_callback(client: Client, callback):
    if callback.from_user:
        user = await db.get_user(callback.from_user.id, client.me.id)
        if user and getattr(user, "is_banned", False):
            await callback.answer("🚫 Vous êtes banni de ce bot.", show_alert=True)
            raise StopPropagation

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    # Ignore /start on the Hub bot, it has its own handler in miniapp.py
    is_hub = (hub_app and client.me.id == hub_app.me.id)
    if is_hub:
        logger.info("Ignoring /start on Hub Bot (Handled by miniapp.py)")
        return
    logger.info(f"Received /start command from {message.from_user.id}")
    try:
        tg_user = message.from_user
        user_id = tg_user.id
        username = tg_user.username
        
        # Check if user already exists
        bot_id = client.me.id
        user = await db.get_user(user_id, bot_id)
        is_new = False
        if not user:
            is_new = True
            logger.info(f"Creating new user: {user_id} on bot {bot_id}")
            user = User(
                user_id=user_id, 
                bot_id=bot_id,
                username=username, 
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language=tg_user.language_code or "fr"
            )
            await db.add_user(user)
            
            # Send notification to logs channel
            if config.telegram.log_channel_id:
                log_text = i18n.get(
                    "new_user", 
                    lang=user.language, 
                    username=tg_user.mention,
                    user_id=user_id,
                    language=user.language
                )
                try:
                    await client.send_message(
                        chat_id=config.telegram.log_channel_id,
                        text=log_text,
                        parse_mode=enums.ParseMode.HTML
                    )
                except Exception as log_err:
                    if "Peer id invalid" in str(log_err):
                        logger.error(f"Error sending log message: Peer id invalid ({config.telegram.log_channel_id}). Ensure the bot is a member of the channel and the ID is correct.")
                    else:
                        logger.error(f"Error sending log message: {log_err}")

        # Logic for menu and text based on role
        is_clone = getattr(client, "is_clone", False)
        is_owner = (user_id == config.telegram.owner_id)
        if is_clone:
            # On a clone, the person who created it is also an owner
            clone_owner_id = getattr(client, "clone_owner_id", None)
            if user_id == clone_owner_id:
                is_owner = True
        
        is_admin = (user.is_admin or is_owner)
        bot_username = client.me.username if client.me else "AdsBot"

        if is_admin:
            text = i18n.get("admin_start", lang=user.language, username=tg_user.mention)
            reply_markup = menu.get_menu("admin", lang=user.language, is_clone=is_clone)
        else:
            if is_new:
                text = i18n.get("start_new", lang=user.language)
            else:
                text = i18n.get("start_returning", lang=user.language, username=tg_user.mention or "utilisateur")
            # Check if user has clones for the menu
            user_clones = await db.get_clones(user_id) if not is_clone else []
            has_clones = len(user_clones) > 0
            
            reply_markup = menu.get_menu("start", lang=user.language, bot_username=bot_username, is_clone=is_clone, has_clones=has_clones)
        
        logger.info(f"Sending response to {user_id} (Admin: {is_admin})")
        if config.telegram.start_image:
            try:
                await message.reply_photo(
                    photo=config.telegram.start_image,
                    caption=text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=reply_markup
                )
            except Exception as photo_err:
                logger.error(f"Error sending photo: {photo_err}")
                await message.reply_text(
                    text, 
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=reply_markup
                )
        else:
            await message.reply_text(
                text, 
                parse_mode=enums.ParseMode.HTML,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error in start_command: {e}", exc_info=True)


@Client.on_message(filters.command("help") & filters.private)
async def help_message(client: Client, message: Message):
    user = await db.get_user(message.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    text = i18n.get("help_text", lang=lang, default="<b>Aide</b>\n\nBienvenue dans le menu d'aide.")
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.get("btn_support", lang=lang, skip_emojis=True), callback_data="start_support")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")]
    ])
    await message.reply_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^help$"))
async def help_callback(client: Client, callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    text = i18n.get("help_text", lang=lang, default="<b>Aide</b>\n\nBienvenue dans le menu d'aide.")
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.get("btn_support", lang=lang, skip_emojis=True), callback_data="start_support")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")]
    ])
    await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^guide$"))
async def guide_callback(client: Client, callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    settings = await db.get_settings(client.me.id)
    min_members = settings.min_members if settings else 0
    
    text = i18n.get("guide_text", lang=lang, min=min_members)
    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")
    ]])
    await callback.edit_message_text(text, reply_markup=reply_markup)
