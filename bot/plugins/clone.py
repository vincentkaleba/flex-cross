from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import re
from ..database.database import db
from ..database.models import CloneBot
from ..utils.clone_manager import clone_manager
from ..utils.i18n import i18n
from ..config import config
import logging

logger = logging.getLogger(__name__)

# Regex to detect bot tokens: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ123456789
BOT_TOKEN_RE = re.compile(r"\d{8,10}:[a-zA-Z0-9_-]{35}")

@Client.on_callback_query(filters.regex(r"^create_clone$"))
async def handle_create_clone(client: Client, callback: CallbackQuery):
    from ..utils.helpers import get_input
    
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    # Check if the client is already a clone (don't allow nesting clones)
    if getattr(client, "is_clone", False):
        main_bot = config.telegram.main_bot_username or "FlexAds_robot"
        text = i18n.get("msg_clone_redirect", lang=lang, username=main_bot)
        return await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(i18n.get("btn_create_clone", lang=lang, skip_emojis=True), url=f"https://t.me/{main_bot}"),
                InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")
            ]])
        )
    
    prompt = i18n.get("prompt_send_token", lang=lang, default="🤖 Veuillez envoyer le token de votre bot.")
    
    # Use get_input to wait for token while editing the current message
    msg = await get_input(client, callback, prompt, lang)
    if not msg:
        return # Canceled or timed out
        
    token_match = BOT_TOKEN_RE.search(msg.text or "")
    if not token_match:
        return await callback.message.edit_text(
            "❌ Format de token invalide.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")
            ]])
        )
    
    token = token_match.group(0)
    
    # Edit the same message to show validation status
    await callback.message.edit_text(i18n.get("msg_clone_validating", lang=lang, default="⏳ Validation du token en cours..."))
    
    try:
        # Start the clone via manager
        me = await clone_manager.start_clone(token, callback.from_user.id)
        
        # Save to database
        new_clone = CloneBot(
            user_id=callback.from_user.id,
            bot_token=token,
            bot_id=me.id,
            username=me.username
        )
        await db.add_clone(new_clone)
        
        success_text = i18n.get(
            "msg_clone_success", 
            lang=lang, 
            username=me.username, 
            default=f"✅ Votre bot a été cloné avec succès !\n\nLien : @{me.username}"
        )
        await callback.message.edit_text(success_text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")
        ]]))
        
        # We can also notify main bot owners here if needed
        
    except Exception as e:
        logger.error(f"Error cloning bot: {e}")
        error_text = i18n.get("error_cloning_failed", lang=lang, default=f"❌ Échec du clonage. Vérifiez le token.")
        await callback.message.edit_text(error_text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")
        ]]))

@Client.on_callback_query(filters.regex(r"^manage_(my|all)_clones(?:_(\d+))?$"))
async def list_clones_callback(client: Client, callback: CallbackQuery):
    mode = callback.matches[0].group(1) # "my" or "all"
    page = int(callback.matches[0].group(2)) if callback.matches[0].group(2) else 0
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    is_admin_mode = (mode == "all")
    if is_admin_mode:
        from ..utils.helpers import is_admin_or_owner
        if not is_admin_or_owner(client, callback.from_user.id, user):
            return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        clones = await db.get_clones() # All clones
        text = i18n.get("msg_admin_clones_list", lang=lang)
    else:
        clones = await db.get_clones(callback.from_user.id) # User's clones
        text = i18n.get("msg_my_clones_list", lang=lang)
        
    from ..utils.menu import Menu
    menu = Menu()
    reply_markup = menu.get_menu("manage_clones", lang=lang, clones=clones, is_admin_mode=is_admin_mode, page=page)
    await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^clone_info_(\d+)_(adm|usr)$"))
async def clone_info_callback(client: Client, callback: CallbackQuery):
    target_bot_id = int(callback.matches[0].group(1))
    mode = callback.matches[0].group(2)
    is_admin_mode = (mode == "adm")
    
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    # Verify ownership or admin
    clone_data = await db.db["clones"].find_one({"bot_id": target_bot_id})
    if not clone_data:
        return await callback.answer("Clone non trouvé.", show_alert=True)
    
    if not is_admin_mode and clone_data.get("user_id") != callback.from_user.id:
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    status_text = i18n.get("status_online", lang=lang) if target_bot_id in clone_manager.clones else i18n.get("status_offline", lang=lang)
    date_str = clone_data.get("created_at", "N/A")
    if hasattr(date_str, "strftime"):
        date_str = date_str.strftime("%Y-%m-%d %H:%M")
        
    text = i18n.get("msg_clone_details", lang=lang, username=clone_data.get("username"), bot_id=target_bot_id, status=status_text, date=date_str)
    
    from ..utils.menu import Menu
    menu = Menu()
    reply_markup = menu.get_menu("clone_details", lang=lang, bot_id=target_bot_id, is_admin_mode=is_admin_mode)
    await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^(stop|restart|delete)_clone_(\d+)_(adm|usr)$"))
async def clone_action_callback(client: Client, callback: CallbackQuery):
    action = callback.matches[0].group(1)
    target_bot_id = int(callback.matches[0].group(2))
    mode = callback.matches[0].group(3)
    is_admin_mode = (mode == "adm")
    
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    clone_data = await db.db["clones"].find_one({"bot_id": target_bot_id})
    if not clone_data:
        return await callback.answer("Clone non trouvé.", show_alert=True)
        
    if not is_admin_mode and clone_data.get("user_id") != callback.from_user.id:
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    if action == "stop":
        await clone_manager.stop_clone(target_bot_id)
        await callback.answer("Bot arrêté.")
    elif action == "restart":
        await callback.answer("Démarrage en cours...", show_alert=False)
        try:
            await clone_manager.start_clone(clone_data["bot_token"], clone_data["user_id"])
            await callback.answer("Bot redémarré avec succès !")
        except Exception as e:
            await callback.answer(f"Erreur: {e}", show_alert=True)
    elif action == "delete":
        await clone_manager.stop_clone(target_bot_id)
        await db.remove_clone(target_bot_id)
        await callback.answer("Clone supprimé définitivement.")
        return await list_clones_callback(client, callback) # Back to list
        
    # Refresh info view
    await clone_info_callback(client, callback)
