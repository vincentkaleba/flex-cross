from pyrogram import Client, filters, enums
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from ..database.database import db
from ..database.models import User
from ..utils.i18n import i18n
from ..utils.helpers import get_input, get_channel_info, is_admin_or_owner
from ..config import config
from ..utils.menu import Menu
import pendulum
import asyncio
import aiohttp
from deep_translator import GoogleTranslator

menu_manager = Menu()

async def get_timezone_from_coords(lat, lon):
    """Fetch timezone from coordinates using public APIs."""
    headers = {"User-Agent": "AdsBot/1.0"}
    try:
        # Primary API
        url = f"https://timeapi.io/api/Timezone/coordinate?latitude={lat}&longitude={lon}"
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("timeZone") # Capital Z!
                
        # Backup API
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}"
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    # Look for timezone in informative field
                    for info in data.get("localityInfo", {}).get("informative", []):
                        if info.get("description") == "time zone":
                            return info.get("name")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error detecting timezone: {e}")
        return None

@Client.on_callback_query(filters.regex(r"^settings$"))
async def settings_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    settings = await db.get_settings(bot_id)
    
    # Fetch active schedule
    cursor = db.adscross.find({"status": "active", "bot_id": bot_id}).sort("created_at", -1).limit(1)
    results = [doc async for doc in cursor]
    if results:
        settings._schedule = results[0].get("schedule_times", [])
    else:
        settings._schedule = []

    text = i18n.get("admin_settings_msg", lang=lang)
    reply_markup = menu_manager.get_menu("settings", lang=lang, settings=settings, is_clone=getattr(client, "is_clone", False))
    
    await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^cancel_setting$"))
async def cancel_setting_callback(client: Client, callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    await callback.answer(i18n.get("admin_canceled", lang=lang))
    await callback.from_user.stop_listening()
    await back_to_start(client, callback)

@Client.on_callback_query(filters.regex(r"^(ban|unban)_channel$"))
async def manual_channel_action_callback(client: Client, callback: CallbackQuery):
    action = callback.matches[0].group(1) # "ban" or "unban"
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    prompt = i18n.get(f"prompt_{action}_channel", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if not msg: return
    
    # Try to extract channel info
    real_chat_id = None
    
    if msg.forward_from_chat:
        real_chat_id = msg.forward_from_chat.id
    elif msg.text:
        text = msg.text.strip()
        if text.startswith("-100") or text.isdigit():
            real_chat_id = int(text)
        elif text.startswith("@") or "t.me/" in text:
            try:
                chat = await client.get_chat(text)
                real_chat_id = chat.id
            except: pass
            
    if not real_chat_id:
        return await callback.message.reply_text(i18n.get("msg_channel_not_found", lang=lang))
        
    ch = await db.get_channel(real_chat_id, bot_id)
    if not ch:
        return await callback.message.reply_text(i18n.get("msg_channel_not_found", lang=lang))
        
    if action == "ban":
        await db.ban_channel(real_chat_id, bot_id)
        success_text = i18n.get("msg_channel_banned_success", lang=lang, title=ch.title)
    else:
        await db.unban_channel(real_chat_id, bot_id)
        success_text = i18n.get("msg_channel_unbanned_success", lang=lang, title=ch.title)
        
    await callback.message.reply_text(success_text)
    
    # Notify the user who added the channel
    if ch.added_by:
        try:
            target_user = await db.get_user(ch.added_by, bot_id)
            target_lang = target_user.language if target_user else "fr"
            notif_key = "msg_your_channel_banned" if action == "ban" else "msg_your_channel_unbanned"
            notif_text = i18n.get(notif_key, lang=target_lang, title=ch.title)
            await client.send_message(ch.added_by, notif_text)
        except RPCError as e:
            import logging
            logging.warning(f"Failed to notify added_by user {ch.added_by} about {action}: {e}")
        except Exception: pass
        
    await back_to_start(client, callback)

@Client.on_callback_query(filters.regex(r"^manage_users$"))
async def manage_users_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    text = "<b>" + i18n.get("admin_manage_users", lang=lang, skip_emojis=True) + "</b>\n\n" + i18n.get("msg_select_action", lang=lang)
    reply_markup = menu_manager.get_menu("manage_users", lang=lang, is_clone=getattr(client, "is_clone", False))
    try:
        await callback.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^add_admin$"))
async def add_admin_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id):
        return await callback.answer(i18n.get("error_owner_only", lang=lang, default="Seul le propriétaire peut ajouter des admins."), show_alert=True)
        
    prompt = i18n.get("prompt_add_admin", lang=lang, default="Veuillez envoyer l'ID de l'utilisateur ou transférer un de ses messages :")
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    
    target_user_id = None
    if msg.forward_from:
        target_user_id = msg.forward_from.id
    elif msg.text and msg.text.isdigit():
        target_user_id = int(msg.text)
        
    if not target_user_id:
        error_msg = i18n.get("error_invalid_user_id", lang=lang, default="ID invalide ou utilisateur masqué.")
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)

    target_user = await db.get_user(target_user_id, bot_id)
    if not target_user:
        error_msg = i18n.get("error_user_not_found", lang=lang, default="Utilisateur introuvable. Demandez-lui de lancer le bot d'abord.")
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(3)
        await tmp.delete()
        return await manage_users_callback(client, callback)

    target_user.is_admin = True
    await db.add_user(target_user)
    
    success_msg = i18n.get("msg_admin_added", lang=lang, default="Administrateur ajouté ! ✅", user_id=target_user_id)
    tmp = await client.send_message(callback.message.chat.id, success_msg)
    await manage_users_callback(client, callback)
    await asyncio.sleep(2)
    await tmp.delete()

@Client.on_callback_query(filters.regex(r"^list_admins$"))
async def list_admins_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id):
        return await callback.answer(i18n.get("error_owner_only", lang=lang), show_alert=True)
        
    cursor = db.users.find({"is_admin": True, "bot_id": bot_id})
    admins = [doc async for doc in cursor]
    
    if not admins:
        admins_list = i18n.get("error_no_admins_found", lang=lang)
    else:
        admins_list = "\n".join([f"• ID : <code>{a.get('user_id')}</code> - {a.get('username') or 'N/A'}" for a in admins])
        
    text = i18n.get("msg_admin_list", lang=lang, admins_list=admins_list)
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="manage_users")]])
    
    try:
        await callback.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^list_users$"))
async def list_users_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("error_owner_only", lang=lang, default="Accès refusé."), show_alert=True)
        
    await callback.answer()
    
    cursor = db.users.find({"bot_id": bot_id})
    users = [doc async for doc in cursor]
    
    total_active = sum(1 for u in users if not u.get("is_banned", False))
    total_banned = sum(1 for u in users if u.get("is_banned", False))
    
    lines = []
    lines.append(i18n.get("msg_user_list_header", lang=lang))
    lines.append(i18n.get("msg_user_list_active", lang=lang, count=total_active))
    lines.append(i18n.get("msg_user_list_banned", lang=lang, count=total_banned))
    lines.append("-" * 43)
    
    for u in users:
        first = u.get("first_name", "") or ""
        last = u.get("last_name", "") or ""
        nom = f"{first} {last}".strip()
        if not nom:
            nom = i18n.get("msg_not_specified", lang=lang)
            
        username = f"@{u.get('username')}" if u.get('username') else i18n.get("msg_not_specified", lang=lang)
        is_admin = "True" if u.get('is_admin') else "False"
        
        lines.append(f"ID : {u.get('user_id')}")
        lines.append(f"nom : {nom}")
        lines.append(f"username : {username}")
        lines.append(f"lang : {u.get('language', 'fr')}")
        lines.append(f"is admin : {is_admin}")
        lines.append("-------------------------------------------")
        
    full_text = "\n".join(lines)
    
    import io
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.get("btn_close", lang=lang, skip_emojis=True, default="❌ Fermer"), callback_data="close_msg")]])
    if len(full_text) > 4000:
        file = io.BytesIO(full_text.encode('utf-8'))
        file.name = "liste_utilisateurs.txt"
        await client.send_document(
            chat_id=callback.message.chat.id,
            document=file,
            caption=i18n.get("msg_list_too_long_file", lang=lang),
            reply_markup=reply_markup
        )
    else:
        await client.send_message(
            chat_id=callback.message.chat.id,
            text=full_text,
            reply_markup=reply_markup
        )

@Client.on_callback_query(filters.regex(r"^close_msg$"))
async def close_msg_callback(client: Client, callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        await callback.answer()

@Client.on_callback_query(filters.regex(r"^revoke_admin$"))
async def revoke_admin_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id):
        return await callback.answer(i18n.get("error_owner_only", lang=lang), show_alert=True)
        
    prompt = i18n.get("prompt_revoke_admin", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    
    target_user_id = None
    if msg.forward_from:
        target_user_id = msg.forward_from.id
    elif msg.text and msg.text.isdigit():
        target_user_id = int(msg.text)
        
    if not target_user_id:
        error_msg = i18n.get("error_invalid_user_id", lang=lang)
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)

    if target_user_id == config.telegram.owner_id:
        error_msg = i18n.get("error_cannot_revoke_owner", lang=lang)
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)
        
    target_user = await db.get_user(target_user_id, bot_id)
    if target_user:
        target_user.is_admin = False
        await db.add_user(target_user)
        
    success_msg = i18n.get("msg_admin_revoked", lang=lang, user_id=target_user_id)
    tmp = await client.send_message(callback.message.chat.id, success_msg)
    await manage_users_callback(client, callback)
    await asyncio.sleep(2)
    await tmp.delete()

@Client.on_callback_query(filters.regex(r"^ban_user$"))
async def ban_user_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    prompt = i18n.get("prompt_ban_user", lang=lang, default="Envoyez l'ID de l'utilisateur à bannir :")
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    
    target_user_id = None
    if msg.forward_from:
        target_user_id = msg.forward_from.id
    elif msg.text and msg.text.isdigit():
        target_user_id = int(msg.text)
        
    if not target_user_id:
        error_msg = i18n.get("error_invalid_user_id", lang=lang)
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)

    target_user = await db.get_user(target_user_id, client.me.id)
    if not target_user:
        error_msg = i18n.get("error_user_not_found", lang=lang, default="Cet utilisateur n'existe pas en DB.")
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)

    if getattr(target_user, "is_admin", False) or target_user_id == config.telegram.owner_id:
        error_msg = i18n.get("error_cannot_ban_admin", lang=lang, default="Impossible de bannir un admin.")
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)
        
    target_user.is_banned = True
    await db.add_user(target_user)
        
    success_msg = i18n.get("msg_user_banned", lang=lang, default="Utilisateur banni ! 🚫", user_id=target_user_id)
    tmp = await client.send_message(callback.message.chat.id, success_msg)
    await manage_users_callback(client, callback)
    await asyncio.sleep(2)
    await tmp.delete()

@Client.on_callback_query(filters.regex(r"^unban_user$"))
async def unban_user_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    prompt = i18n.get("prompt_unban_user", lang=lang, default="Envoyez l'ID de l'utilisateur à débannir :")
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    
    target_user_id = None
    if msg.forward_from:
        target_user_id = msg.forward_from.id
    elif msg.text and msg.text.isdigit():
        target_user_id = int(msg.text)
        
    if not target_user_id:
        error_msg = i18n.get("error_invalid_user_id", lang=lang)
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)

    target_user = await db.get_user(target_user_id, client.me.id)
    if not target_user:
        error_msg = i18n.get("error_user_not_found", lang=lang, default="Cet utilisateur n'existe pas en DB.")
        tmp = await client.send_message(callback.message.chat.id, error_msg)
        await asyncio.sleep(2)
        await tmp.delete()
        return await manage_users_callback(client, callback)

    target_user.is_banned = False
    await db.add_user(target_user)
        
    success_msg = i18n.get("msg_user_unbanned", lang=lang, default="Utilisateur débanni ! ✅", user_id=target_user_id)
    tmp = await client.send_message(callback.message.chat.id, success_msg)
    await manage_users_callback(client, callback)
    await asyncio.sleep(2)
    await tmp.delete()



@Client.on_callback_query(filters.regex(r"^set_(header|footer)$"))
async def set_text_settings(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    field = callback.data.split("_")[1]
    
    prompt = i18n.get(f"prompt_set_{field}", lang=lang)
    
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    if msg.text == "/empty":
        new_val = ""
    else:
        # Preserve formatting using HTML
        new_val = client.parser.unparse(msg.text or msg.caption or "", msg.entities or msg.caption_entities or [], is_html=True)
    
    settings = await db.get_settings(bot_id)
    if field == "header":
        settings.message_header = new_val
    else:
        settings.message_footer = new_val
        
    await db.save_settings(settings)
    
    settings._schedule = []
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^set_del_after$"))
@Client.on_callback_query(filters.regex(r"^set_delete$"))
async def set_delete_settings(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    prompt = i18n.get("prompt_set_delete", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    val = msg.text
    
    if not val.isdigit():
        return await callback.answer(i18n.get("error_invalid_value", lang=lang, default="Valeur invalide."), show_alert=True)
    
    settings = await db.get_settings(bot_id)
    settings.delete_after_minutes = int(val)
    await db.save_settings(settings)
    
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^set_members$"))
async def set_members_settings(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    prompt = i18n.get("prompt_set_members", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    val = msg.text
    
    try:
        mini, maxi = map(int, val.split())
        settings = await db.get_settings(bot_id)
        settings.min_members = mini
        settings.max_members = maxi
        await db.save_settings(settings)
        await settings_callback(client, callback)
    except Exception:
        await callback.answer(i18n.get("error_invalid_format", lang=lang, default="Format invalide."), show_alert=True)

@Client.on_callback_query(filters.regex(r"^set_(min|max)_mem$"))
async def set_single_member_limit(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    field = callback.data.split("_")[1]
    
    prompt = i18n.get(f"prompt_set_{field}_mem", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    val = msg.text
    
    if not val.isdigit(): return await callback.answer(i18n.get("error_invalid_value", lang=lang), show_alert=True)
    
    settings = await db.get_settings(bot_id)
    if field == "min":
        settings.min_members = int(val)
    else:
        settings.max_members = int(val)
    await db.save_settings(settings)
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^set_tz$"))
async def set_tz_settings(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    reply_markup = ReplyKeyboardMarkup(
        [
            [KeyboardButton(i18n.get("btn_share_location", lang=lang), request_location=True)],
            [KeyboardButton("UTC"), KeyboardButton(i18n.get("btn_cancel", lang=lang, skip_emojis=True))]
        ],
        resize_keyboard=True, one_time_keyboard=True
    )
    
    # Status in the menu
    status_prompt = i18n.get("msg_waiting_for_tz", lang=lang, default="⏳ En attente du fuseau horaire...")
    
    # 1. Edit the menu message to show we're waiting
    await callback.message.edit_text(
        status_prompt, 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(i18n.get("btn_cancel", lang=lang, skip_emojis=True), callback_data="cancel_setting")]])
    )
    
    # 2. Send the actual prompt with the Location Keyboard
    kb_msg = await client.send_message(
        callback.from_user.id, 
        i18n.get("prompt_set_tz_location", lang=lang), 
        reply_markup=reply_markup
    )
    
    # 3. Use listen() directly instead of get_input because we already handled the UI
    try:
        msg = await callback.from_user.listen(timeout=300)
    except asyncio.TimeoutError:
        msg = None
    
    await kb_msg.delete(revoke=True)
    
    if msg is None:
        return await settings_callback(client, callback)
    
    # Delete user message to keep chat clean
    try: await msg.delete()
    except: pass
    
    if msg.location:
        detected_tz = await get_timezone_from_coords(msg.location.latitude, msg.location.longitude)
        if detected_tz:
            settings = await db.get_settings(bot_id)
            settings.fuseau_horaire = detected_tz
            await db.save_settings(settings)
            await callback.answer(i18n.get("msg_location_received", lang=lang, tz=detected_tz), show_alert=True)
            return await settings_callback(client, callback)
        else:
            await callback.answer(i18n.get("error_tz_not_detected", lang=lang, default="Impossible de détecter le fuseau horaire."), show_alert=True)
            return await set_tz_settings(client, callback)
    
    val = msg.text
    # Validate timezone name if possible
    try:
        pendulum.timezone(val)
    except Exception:
        await callback.answer(i18n.get("error_invalid_tz", lang=lang, default="Fuseau horaire invalide."), show_alert=True)
        return await set_tz_settings(client, callback)

    settings = await db.get_settings(bot_id)
    settings.fuseau_horaire = val
    await db.save_settings(settings)
    
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^set_prefix$"))
async def set_prefix_settings(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    prompt = i18n.get("prompt_set_prefix", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    val = msg.text
    
    settings = await db.get_settings(bot_id)
    settings.button_prefix = val
    await db.save_settings(settings)
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^set_max_(line|col|row|btns)$"))
async def set_max_limits(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    mode = callback.data.split("_")[2]
    
    prompt = i18n.get(f"prompt_max_{mode}", lang=lang)
    
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    val = msg.text
    if not val.isdigit(): return await callback.answer(i18n.get("error_invalid_value", lang=lang), show_alert=True)
    
    num = int(val)
    settings = await db.get_settings(bot_id)
    if mode == "line": settings.max_columns = num # Map "Colonnes" to max_columns
    elif mode == "col": settings.max_columns = num
    elif mode == "row": settings.max_rows = num # Map "Lignes/Bloc" to max_rows
    elif mode == "btns": settings.max_buttons = num
    
    await db.save_settings(settings)
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^set_auto_del$"))
async def set_auto_del_toggle(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    settings = await db.get_settings(bot_id)
    settings.auto_delete_ads = not settings.auto_delete_ads
    await db.save_settings(settings)
    
    status_str = i18n.get("status_enabled", lang=lang) if settings.auto_delete_ads else i18n.get("status_disabled", lang=lang)
    await callback.answer(i18n.get("msg_auto_delete_status", lang=lang, status=status_str), show_alert=True)
    await settings_callback(client, callback)


@Client.on_callback_query(filters.regex(r"^set_schedule$"))
async def set_schedule_handler(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    cursor = db.adscross.find({"status": "active", "bot_id": bot_id}).sort("created_at", -1).limit(1)
    results = [doc async for doc in cursor]
    current_sched = ", ".join(results[0].get("schedule_times", [])) if results else "-"
    
    prompt = i18n.get("prompt_set_schedule", lang=lang, current_sched=current_sched)
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    val = msg.text
    
    times = val.split()
    valid_times = []
    for t in times:
        try:
            parts = t.split(":")
            if len(parts) == 2 and 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59:
                 valid_times.append(t)
        except Exception:
            pass
            
    if not valid_times:
        return await callback.answer(i18n.get("error_invalid_time", lang=lang), show_alert=True)

    if not results:
        return await callback.answer(i18n.get("error_no_active_ad", lang=lang), show_alert=True)
    
    ad_doc = results[0]
    await db.adscross.update_one(
        {"_id": ad_doc["_id"]},
        {"$set": {
            "schedule_times": valid_times,
            "schedule_days": [0, 1, 2, 3, 4, 5, 6],
            "is_scheduled": True
        }}
    )
    
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^set_format$"))
async def set_format_settings(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    settings = await db.get_settings(bot_id)
    # Toggle: html -> markdown -> none -> html
    modes = ["html", "markdown", "none"]
    current_index = modes.index(settings.parse_mode) if settings.parse_mode in modes else 0
    next_index = (current_index + 1) % len(modes)
    settings.parse_mode = modes[next_index]
    
    await db.save_settings(settings)
    await settings_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^start$"))
async def back_to_start(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    if not user: return
    
    lang = user.language
    is_owner = (callback.from_user.id == config.telegram.owner_id)
    is_admin = (user.is_admin or is_owner)
    
    bot_username = client.me.username if client.me else "AdsBot"
    
    if is_admin:
        text = i18n.get("admin_start", lang=lang, username=callback.from_user.mention)
        reply_markup = menu_manager.get_menu("admin", lang=lang, is_clone=getattr(client, "is_clone", False))
    else:
        text = i18n.get("start_returning", lang=lang, username=callback.from_user.mention)
        reply_markup = menu_manager.get_menu("start", lang=lang, bot_username=bot_username, is_clone=getattr(client, "is_clone", False))
        
    await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^user_mode$"))
async def user_mode_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    bot_username = client.me.username if client.me else "AdsBot"
    
    text = i18n.get("start_returning", lang=lang, username=callback.from_user.mention)
    reply_markup = menu_manager.get_menu("start", lang=lang, bot_username=bot_username, is_clone=getattr(client, "is_clone", False))
    
    await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^change_lang$"))
async def change_lang_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    text = i18n.get("msg_select_lang", lang=lang, default="Veuillez sélectionner votre langue :")
    reply_markup = menu_manager.get_menu("language", lang=lang, is_clone=getattr(client, "is_clone", False))
    
    try:
        await callback.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^set_lang_(.*)$"))
async def set_lang_callback(client: Client, callback: CallbackQuery):
    new_lang = callback.data.split("_")[2]
    bot_id = client.me.id
    
    user = await db.get_user(callback.from_user.id, bot_id)
    if user:
        user.language = new_lang
        await db.add_user(user)
        
    await callback.answer(i18n.get("msg_lang_changed", lang=new_lang, default="Langue modifiée !"), show_alert=True)
    await back_to_start(client, callback)

@Client.on_callback_query(filters.regex(r"^(broadcast|announce)$"))
async def broadcast_menu_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    text = "<b>" + i18n.get("admin_manage_users", lang=lang, skip_emojis=True) + "</b>\n\nSélectionnez votre cible :"
    reply_markup = menu_manager.get_menu("broadcast_targets", lang=lang, is_clone=getattr(client, "is_clone", False))
    
    try:
        await callback.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^bc_(all|active|admins|channels)$"))
async def execute_broadcast_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    target_type = callback.matches[0].group(1)
    
    prompt = i18n.get("prompt_broadcast_msg", lang=lang, default="Veuillez envoyer le message que vous souhaitez diffuser :")
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    
    info_msg = await client.send_message(callback.message.chat.id, i18n.get("msg_broadcasting", lang=lang, count="...", default="Diffusion en cours..."))
    
    targets = []
    if target_type == "channels":
        cursor = db.channels.find({"status": "active", "bot_id": bot_id})
        targets = [{"chat_id": doc["channel_id"], "lang": "fr"} async for doc in cursor]
    else:
        query = {"bot_id": bot_id}
        if target_type == "active": query["is_banned"] = {"$ne": True}
        elif target_type == "admins": query["is_admin"] = True
        
        cursor = db.users.find(query)
        targets = [{"chat_id": doc["user_id"], "lang": doc.get("language", "fr")} async for doc in cursor]
        
    source_text = msg.text or msg.caption
    cached_translations = {}
    if source_text:
        cached_translations["fr"] = source_text
        try:
            cached_translations["en"] = GoogleTranslator(source='auto', target='en').translate(source_text)
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            cached_translations["en"] = source_text
            
    success = 0
    failed = 0
    
    report_lines = []
    report_lines.append(f"=== Rapport de Diffusion (Mailing) ===")
    report_lines.append(f"Cible : {target_type.upper()}")
    report_lines.append(f"Date : {pendulum.now().to_datetime_string()}")
    report_lines.append("-------------------------------------------------")
    
    for target in targets:
        target_lang = target["lang"]
        chat_id = target["chat_id"]
        
        try:
            if target_lang == "fr" or not source_text:
                await msg.copy(chat_id)
            else:
                translated = cached_translations.get(target_lang, cached_translations["fr"])
                if msg.text:
                    await client.send_message(chat_id, translated, reply_markup=msg.reply_markup)
                else:
                    await msg.copy(chat_id, caption=translated, reply_markup=msg.reply_markup)
            
            success += 1
            report_lines.append(f"✅ SUCCÈS | ID: {chat_id} | Langue: {target_lang}")
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            report_lines.append(f"❌ ÉCHEC  | ID: {chat_id} | Erreur: {str(e)}")
            
    await info_msg.delete()
    
    report_lines.append("-------------------------------------------------")
    report_lines.append(f"Total Succès : {success}")
    report_lines.append(f"Total Échecs : {failed}")
    
    success_text = i18n.get("msg_broadcast_success", lang=lang, success=success, failed=failed, default=f"Diffusion terminée !\nSuccès : {success}\nÉchecs : {failed}")
    
    import io
    file = io.BytesIO("\n".join(report_lines).encode('utf-8'))
    file.name = f"rapport_diffusion_{pendulum.now().format('YYYYMMDD_HHmmss')}.txt"
    
    await client.send_document(
        chat_id=callback.message.chat.id,
        document=file,
        caption=success_text
    )
    
    await manage_users_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^manage_list(_(\d+))?$"))
async def manage_list_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Fix for regex matching: group(2) might be None
    page_str = callback.matches[0].group(2)
    page = int(page_str) if page_str else 1
    limit = 5
    skip = (page - 1) * limit
    
    query = {"bot_id": bot_id}
    total_channels = await db.channels.count_documents(query)
    cursor = db.channels.find(query).sort("added_date", -1).skip(skip).limit(limit)
    channels = [doc async for doc in cursor]
    
    if not channels and page == 1:
        return await callback.answer(i18n.get("error_no_channels", lang=lang), show_alert=True)
    
    total_pages = (total_channels + limit - 1) // limit
    
    legend = i18n.get("msg_manage_list_legend", lang=lang)
    text = i18n.get("msg_manage_list_header", lang=lang, legend=legend, page=page, total=total_pages)
    
    buttons = []
    for ch in channels:
        status_icon = "✅"
        if ch.get("is_banned"): status_icon = "🚫"
        elif ch.get("failure_count", 0) > 0: status_icon = "⚠️"
        
        # Channel Row
        members = ch.get('members_count', 0)
        title = ch.get('title', 'N/A')
        buttons.append([InlineKeyboardButton(f"{status_icon} {title} ({members})", callback_data="noop")])
        
        # Actions Row
        action_row = [
            InlineKeyboardButton(i18n.get("btn_sync", lang=lang, skip_emojis=True), callback_data=f"sync_ch_{ch['channel_id']}_{page}"),
            InlineKeyboardButton(i18n.get("btn_unban" if ch.get("is_banned") else "btn_ban", lang=lang, skip_emojis=True), callback_data=f"ban_tog_{ch['channel_id']}_{page}")
        ]
        if not getattr(client, "is_clone", False):
            action_row.append(InlineKeyboardButton(i18n.get("btn_promote", lang=lang, skip_emojis=True), callback_data=f"prom_ch_{ch['channel_id']}"))
        buttons.append(action_row)
        
    # Navigation
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"manage_list_{page-1}"))
    if total_channels > skip + limit:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"manage_list_{page+1}"))
    if nav: buttons.append(nav)
    
    buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")])
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await callback.answer()

@Client.on_callback_query(filters.regex(r"^sync_ch_(.*)_(\d+)$"))
async def sync_channel_callback(client: Client, callback: CallbackQuery):
    ch_id = int(callback.matches[0].group(1))
    page = int(callback.matches[0].group(2))
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    try:
        chat = await client.get_chat(ch_id)
        members = await client.get_chat_members_count(ch_id)
        
        await db.channels.update_one(
            {"channel_id": ch_id},
            {"$set": {
                "title": chat.title,
                "username": chat.username,
                "members_count": members,
                "failure_count": 0
            }}
        )
        await callback.answer(i18n.get("msg_channel_synced", lang=lang, title=chat.title, members=members), show_alert=True)
    except Exception as e:
        await callback.answer(f"Erreur Sync: {str(e)}", show_alert=True)
        
    # Trigger refresh
    callback.data = f"manage_list_{page}" # Mock data for refresh
    await manage_list_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^ban_tog_(-?\d+)(_(\d+)|_info)?$"))
async def ban_toggle_callback(client: Client, callback: CallbackQuery):
    ch_id = int(callback.matches[0].group(1))
    page = int(callback.matches[0].group(2))
    bot_id = client.me.id
    
    ch = await db.get_channel(ch_id, bot_id)
    if not ch: return await callback.answer("Canal introuvable")
    
    new_status = not ch.is_banned
    if new_status:
        await db.ban_channel(ch_id, bot_id)
    else:
        await db.unban_channel(ch_id, bot_id)
        
    await callback.answer("Statut mis à jour !")
    
    # Trigger refresh
    if suffix == "_info":
        user = await db.get_user(callback.from_user.id, bot_id)
        lang = user.language if user else "fr"
        await show_specific_channel_info(client, callback, ch_id, lang)
    elif suffix:
        page = int(callback.matches[0].group(3))
        callback.data = f"manage_list_{page}" # Mock data for refresh
        await manage_list_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^prom_ch_(.*)$"))
async def promote_to_paid_callback(client: Client, callback: CallbackQuery):
    ch_id = int(callback.matches[0].group(1))
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if getattr(client, "is_clone", False):
        return await callback.answer("Cette fonctionnalité est réservée au bot principal.", show_alert=True)
        
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    ch = await db.get_channel(ch_id, bot_id)
    if not ch: return await callback.answer("Canal introuvable")
    
    import uuid
    from .post import pending_paid_promos, show_target_categories
    
    promo_id = str(uuid.uuid4())
    pending_paid_promos[callback.from_user.id] = {
        "promo_id": promo_id,
        "name": f"Promo: {ch.title}",
        "text": ch.title,
        "url": f"https://t.me/{ch.username}" if ch.username else f"https://t.me/c/{str(ch_id)[4:]}/1",
        "categories": [],
        "languages": []
    }
    
    await show_target_categories(client, callback, lang)

@Client.on_callback_query(filters.regex(r"^channel_info$"))
async def channel_info_prompt_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    prompt = i18n.get("prompt_show_channel", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if not msg: return
    
    # Extract ID
    real_chat_id = None
    if msg.forward_from_chat:
        real_chat_id = msg.forward_from_chat.id
    elif msg.text:
        text = msg.text.strip()
        if text.startswith("-100") or text.isdigit():
            try: real_chat_id = int(text)
            except: pass
        elif text.startswith("@") or "t.me/" in text:
            try:
                chat = await client.get_chat(text)
                real_chat_id = chat.id
            except: pass
            
    if not real_chat_id:
        return await client.send_message(callback.message.chat.id, i18n.get("msg_channel_not_found", lang=lang))
        
    await show_specific_channel_info(client, callback, real_chat_id, bot_id, lang)

async def show_specific_channel_info(client: Client, callback: CallbackQuery, channel_id: int, bot_id: int, lang: str):
    ch = await db.get_channel(channel_id, bot_id)
    if not ch:
        return await client.send_message(callback.message.chat.id, i18n.get("msg_channel_not_found", lang=lang))
        
    status = i18n.get("status_suspended" if ch.is_banned else "status_active", lang=lang)
    
    text = i18n.get("msg_admin_channel_info", lang=lang,
                    title=ch.title,
                    id=ch.channel_id,
                    username=f"@{ch.username}" if ch.username else "N/A",
                    members=ch.members_count,
                    added_by=f"<code>{ch.added_by}</code>",
                    category=ch.category or "N/A",
                    language=ch.language or "N/A",
                    status=status,
                    failures=ch.failure_count)
    
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_sync", lang=lang, skip_emojis=True), callback_data=f"sync_info_{channel_id}")],
        [InlineKeyboardButton(i18n.get("btn_unban" if ch.is_banned else "btn_ban", lang=lang, skip_emojis=True), callback_data=f"ban_tog_{channel_id}_info")],
        [InlineKeyboardButton(i18n.get("btn_delete_channel", lang=lang, skip_emojis=True), callback_data=f"del_ch_{channel_id}")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")]
    ]
    
    try:
        await client.send_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^sync_info_(.*)$"))
async def sync_info_callback(client: Client, callback: CallbackQuery):
    ch_id = int(callback.matches[0].group(1))
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    try:
        chat = await client.get_chat(ch_id)
        members = await client.get_chat_members_count(ch_id)
        await db.channels.update_one(
            {"channel_id": ch_id, "bot_id": bot_id},
            {"$set": {
                "title": chat.title,
                "username": chat.username,
                "members_count": members,
                "failure_count": 0
            }}
        )
        await callback.answer(i18n.get("msg_channel_synced", lang=lang, title=chat.title, members=members), show_alert=True)
    except Exception as e:
        await callback.answer(f"Erreur Sync: {str(e)}", show_alert=True)
        
    await show_specific_channel_info(client, callback, ch_id, bot_id, lang)

@Client.on_callback_query(filters.regex(r"^del_ch_(.*)$"))
async def delete_channel_callback(client: Client, callback: CallbackQuery):
    ch_id = int(callback.matches[0].group(1))
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    ch = await db.get_channel(ch_id, bot_id)
    if ch:
        await db.channels.delete_one({"channel_id": ch_id, "bot_id": bot_id})
        await callback.answer(i18n.get("msg_channel_removed", lang=lang, title=ch.title), show_alert=True)
    
    await back_to_start(client, callback)

@Client.on_callback_query(filters.regex(r"^stats$"))
async def admin_stats_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # 1. Gather Global Counts
    users_total = await db.users.count_documents({"bot_id": bot_id})
    users_active = await db.users.count_documents({"is_banned": {"$ne": True}, "bot_id": bot_id})
    users_banned = await db.users.count_documents({"is_banned": True, "bot_id": bot_id})
    
    channels_total = await db.channels.count_documents({"bot_id": bot_id})
    channels_active = await db.channels.count_documents({"is_banned": {"$ne": True}, "bot_id": bot_id})
    channels_banned = await db.channels.count_documents({"is_banned": True, "bot_id": bot_id})
    
    ads_total = await db.adscross.count_documents({"bot_id": bot_id})
    ads_active = await db.adscross.count_documents({"status": "active", "bot_id": bot_id})
    ads_completed = await db.adscross.count_documents({"status": "completed", "bot_id": bot_id})
    
    posts_total = await db.posts.count_documents({"bot_id": bot_id})
    
    text = i18n.get("msg_admin_stats_header", lang=lang,
                    users_total=users_total, users_active=users_active, users_banned=users_banned,
                    channels_total=channels_total, channels_active=channels_active, channels_banned=channels_banned,
                    ads_total=ads_total, ads_active=ads_active, ads_completed=ads_completed,
                    posts_total=posts_total)
    
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_generate_chart", lang=lang, skip_emojis=True), callback_data="gen_admin_chart")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="manage_users")]
    ]
    
    if callback.message.photo:
        try: await callback.message.delete()
        except: pass
        await client.send_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await client.send_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^update_subs$"))
async def update_subs_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # 1. Start message (Edit current message to show start)
    await callback.answer("Synchronisation commencée...")
    status_msg = await callback.message.reply_text(i18n.get("msg_sync_progress", lang=lang, current=0, total="?", success=0, failed=0))
    
    # 2. Get all non-banned channels
    query = {"is_banned": {"$ne": True}, "bot_id": bot_id}
    cursor = db.channels.find(query)
    total = await db.channels.count_documents(query)
    
    success = 0
    failed = 0
    count = 0
    
    async for ch in cursor:
        count += 1
        ch_id = ch["channel_id"]
        try:
            # Sync member count
            members = await client.get_chat_members_count(ch_id)
            await db.channels.update_one(
                {"channel_id": ch_id, "bot_id": bot_id},
                {"$set": {"members_count": members, "failure_count": 0}}
            )
            success += 1
        except Exception as e:
            failed += 1
            # Optional: increment failure count if bot was kicked
            if "CHAT_ADMIN_REQUIRED" in str(e) or "USER_NOT_PARTICIPANT" in str(e):
                await db.channels.update_one({"channel_id": ch_id, "bot_id": bot_id}, {"$inc": {"failure_count": 1}})
            
        # Update progress every 5 channels or at the end
        if count % 5 == 0 or count == total:
            progress_text = i18n.get("msg_sync_progress", lang=lang, current=count, total=total, success=success, failed=failed)
            try: await status_msg.edit_text(progress_text)
            except: pass
            
        # Rate limiting: wait 0.5s between requests
        await asyncio.sleep(5)
        
    # Final Result
    final_text = i18n.get("msg_sync_complete", lang=lang, success=success, failed=failed)
    buttons = [[InlineKeyboardButton(i18n.get("btn_close", lang=lang, skip_emojis=True), callback_data="start")]]
    await status_msg.edit_text(final_text, reply_markup=InlineKeyboardMarkup(buttons))
    
    # Go back to admin menu automatically or after a delay
    await asyncio.sleep(2)
    await manage_users_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^gen_admin_chart$"))
async def generate_admin_chart_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    await callback.answer(i18n.get("msg_generating_chart", lang=lang))
    
    # 1. Gather stats for caption
    users_total = await db.users.count_documents({"bot_id": bot_id})
    users_active = await db.users.count_documents({"is_banned": {"$ne": True}, "bot_id": bot_id})
    users_banned = await db.users.count_documents({"is_banned": True, "bot_id": bot_id})
    channels_total = await db.channels.count_documents({"bot_id": bot_id})
    channels_active = await db.channels.count_documents({"is_banned": {"$ne": True}, "bot_id": bot_id})
    channels_banned = await db.channels.count_documents({"is_banned": True, "bot_id": bot_id})
    ads_total = await db.adscross.count_documents({"bot_id": bot_id})
    ads_active = await db.adscross.count_documents({"status": "active", "bot_id": bot_id})
    ads_completed = await db.adscross.count_documents({"status": "completed", "bot_id": bot_id})
    posts_total = await db.posts.count_documents({"bot_id": bot_id})
    
    text = i18n.get("msg_admin_stats_header", lang=lang,
                    users_total=users_total, users_active=users_active, users_banned=users_banned,
                    channels_total=channels_total, channels_active=channels_active, channels_banned=channels_banned,
                    ads_total=ads_total, ads_active=ads_active, ads_completed=ads_completed,
                    posts_total=posts_total)

    # 2. Fetch snapshots from stats_history
    cursor = db.db["stats_history"].find({"bot_id": bot_id}).sort("date", 1)
    history = [doc async for doc in cursor]
    
    # Map to what generate_growth_chart expects
    plot_data = []
    for h in history:
        plot_data.append({
            "date": h["date"],
            "total": h["total_users"], 
            "bot_joins": 0
        })
        
    from ..utils.plotter import generate_growth_chart
    buf = generate_growth_chart(plot_data, timeframe_days=30, lang=lang)
    
    # 3. Delete old menu and send photo with caption
    try: await callback.message.delete()
    except: pass

    buttons = [
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="stats")],
        [InlineKeyboardButton(i18n.get("btn_close", lang=lang, skip_emojis=True), callback_data="back_to_start")]
    ]
    
    await client.send_photo(
        chat_id=callback.message.chat.id,
        photo=buf,
        caption=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
