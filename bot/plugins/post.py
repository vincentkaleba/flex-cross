from pyrogram import Client, filters, enums
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from ..utils.helpers import preload_peers, send_promo_to_channel
from ..database.database import db
from ..database.models import Adscross, AdType, PaidPromo, AdStatus, Post
import logging
logger = logging.getLogger(__name__)
from ..utils.i18n import i18n
from ..utils.helpers import get_input, get_channel_info, get_next_pub_time, handle_channel_failure, is_admin_or_owner
from ..config import config
from ..utils.menu import Menu
from ..utils.promo_generator import PromoGenerator
from pyrogram.errors import RPCError
import asyncio
import json

menu_manager = Menu()
pending_paid_promos = {}
pending_ads = {}

@Client.on_callback_query(filters.regex(r"^create_post$"))
async def create_post_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    # Ask for Name
    prompt_name = i18n.get("prompt_ad_name", lang=lang)
    msg_name = await get_input(client, callback, prompt_name, lang)
    if msg_name is None: return
    
    pending_ads[callback.from_user.id] = {"name": msg_name.text}
    
    # Ask for ad type
    prompt_ad_type = i18n.get("prompt_ad_type", lang=lang)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.get("btn_ad_bouton", lang=lang, skip_emojis=True), callback_data="adtype_bouton")],
        [InlineKeyboardButton(i18n.get("btn_ad_folder", lang=lang, skip_emojis=True), callback_data="adtype_folder")],
        [InlineKeyboardButton(i18n.get("btn_ad_text", lang=lang, skip_emojis=True), callback_data="adtype_text")],
        [InlineKeyboardButton(i18n.get("btn_cancel", lang=lang, skip_emojis=True), callback_data="cancel_setting")]
    ])
    
    try:
        await callback.message.edit_text(prompt_ad_type, reply_markup=keyboard)
    except:
        await callback.message.reply_text(prompt_ad_type, reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^adtype_(bouton|folder|text)$"))
async def handle_ad_type_selection(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    ad_type_str = callback.matches[0].group(1)
    
    ad_type = AdType.BOUTON
    if ad_type_str == "folder": ad_type = AdType.FOLDER
    elif ad_type_str == "text": ad_type = AdType.TEXT
    
    folder_link = None
    folder_msg_content = None
    if ad_type == AdType.FOLDER:
        prompt_folder = i18n.get("prompt_folder_link", lang=lang)
        msg_folder = await get_input(client, callback, prompt_folder, lang)
        if msg_folder is None: return
        new_fld = getattr(msg_folder, "text", None) or getattr(msg_folder, "caption", None)
        folder_link = new_fld.strip() if new_fld else None
        
        # If the user sent a full formatted message (photo/video/buttons) as the folder link step
        # treat it as the content step too, and extract the t.me link from caption
        if getattr(msg_folder, "photo", None) or getattr(msg_folder, "video", None) or msg_folder.reply_markup:
            folder_msg_content = msg_folder
            # If they sent a photo+caption containing the link, extract it
            import re
            if not folder_link or "t.me" not in (folder_link or ""):
                raw_caption = getattr(msg_folder, "caption", None) or ""
                m = re.search(r'(https?://t\.me/\S+)', raw_caption)
                if m:
                    folder_link = m.group(1).rstrip(')"\'>')
        
    if folder_msg_content:
        msg = folder_msg_content
    else:
        prompt_content = i18n.get("prompt_ad_content", lang=lang)
        msg = await get_input(client, callback, prompt_content, lang)
        if msg is None: return
    
    media_id = None
    media_type = None
    
    if msg.photo: 
        media_id = msg.photo.file_id
        media_type = "photo"
    elif msg.video:
        media_id = msg.video.file_id
        media_type = "video"
    elif msg.animation:
        media_id = msg.animation.file_id
        media_type = "animation"
    elif msg.document:
        media_id = msg.document.file_id
        media_type = "document"
        
    content = client.parser.unparse(msg.text or msg.caption or "", msg.entities or msg.caption_entities or [], is_html=True)
        
    if not content and not media_id and ad_type_str != "text":
        content = i18n.get("default_ad_content", lang=lang)

    # Create new Adscross, marking old active ones as completed
    cursor = db.adscross.find({"status": "active", "bot_id": bot_id})
    async for old_ad in cursor:
        await db.adscross.update_one({"_id": old_ad["_id"]}, {"$set": {"status": "completed"}})
        
    # Get all channels for the target list
    targets = []
    ch_cursor = db.channels.find({"is_active": True, "bot_id": bot_id})
    async for ch in ch_cursor:
        targets.append(ch["channel_id"])
        
    data = pending_ads.pop(callback.from_user.id, {})
    ad_name = data.get("name", i18n.get("msg_ad_no_name", lang=lang))
    
    new_ad = Adscross(
        creator_id=callback.from_user.id,
        content=content,
        name=ad_name,
        status=AdStatus.ACTIVE,
        target_channels=targets,
        ad_type=ad_type,
        folder_link=folder_link,
        media_id=media_id,
        media_type=media_type,
        bot_id=bot_id,
        reply_markup=json.loads(str(msg.reply_markup)) if msg.reply_markup else None
    )
    
    await db.create_ad(new_ad)
    
    success_msg = i18n.get("msg_ad_created", lang=lang)
    try:
        await callback.answer(success_msg, show_alert=True)
    except Exception:
        # Fallback if callback expired
        await client.send_message(callback.from_user.id, success_msg)
    
    from .admin import back_to_start
    await back_to_start(client, callback)

@Client.on_callback_query(filters.regex(r"^preview_promo(_(\d+))?$"))
async def preview_promo_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Safely extract page
    page = 1
    if callback.data.startswith("preview_promo_"):
        try:
            page = int(callback.data.split("_")[-1])
        except:
            page = 1
    elif hasattr(callback, "matches") and callback.matches and len(callback.matches[0].groups()) >= 2:
        try:
            val = callback.matches[0].group(2)
            if val: page = int(val)
        except:
            page = 1
    limit = 5
    skip = (page - 1) * limit
    
    query = {"bot_id": bot_id}
    cursor = db.adscross.find(query).sort("created_at", -1).skip(skip).limit(limit)
    ads = [Adscross.from_dict(doc) async for doc in cursor]
    total_ads = await db.adscross.count_documents(query)
    
    if not ads and page == 1:
        # If no ads left (e.g. after deletion), show a clean "no ads" screen
        buttons = [[InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")]]
        text = i18n.get("error_no_active_ad", lang=lang)
        try:
            return await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except:
            return await callback.answer(text, show_alert=True)
            
    buttons = []
    for ad in ads:
        label = ad.name if ad.name else (ad.content[:20] + "...")
        if not label.strip(): label = f"ID: {str(ad.ad_id)[:8]}"
        
        # Status-colored indicator
        status_key = "status_active" if ad.status == AdStatus.ACTIVE else "status_suspended" if ad.status == AdStatus.SUSPENDED else "status_completed"
        indicator = i18n.get(status_key, lang=lang, skip_emojis=True)
        
        buttons.append([InlineKeyboardButton(f"{indicator} {label}", callback_data=f"info_ad_{ad.ad_id}")])
        
        # Action row
        status_icon = "⏸️" if ad.status == AdStatus.ACTIVE else "▶️"
        status_action = "susp" if ad.status == AdStatus.ACTIVE else "cont"
        
        action_row = [
            InlineKeyboardButton(status_icon, callback_data=f"{status_action}_ad_{ad.ad_id}"),
            InlineKeyboardButton("📝", callback_data=f"edit_ad_{ad.ad_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"del_ad_{ad.ad_id}"),
            InlineKeyboardButton("👁️", callback_data=f"sel_ad_prev_{ad.ad_id}")
        ]
        buttons.append(action_row)
        
    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"preview_promo_{page-1}"))
    if total_ads > skip + limit:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"preview_promo_{page+1}"))
    if nav:
        buttons.append(nav)
        
    buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")])
    
    legend = i18n.get("ad_list_legend", lang=lang)
    text = i18n.get("msg_select_ad_to_preview", lang=lang) + legend
    
    await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^delete_promo(_(\d+))?$"))
async def delete_promo_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Safely extract page
    page = 1
    if callback.data.startswith("delete_promo_"):
        try: page = int(callback.data.split("_")[-1])
        except: page = 1
    elif hasattr(callback, "matches") and callback.matches and len(callback.matches[0].groups()) >= 2:
        try:
            val = callback.matches[0].group(2)
            if val: page = int(val)
        except: page = 1

    limit = 5
    skip = (page - 1) * limit
    
    # NEW LOGIC: Look for ads that have active posts in channels
    active_ad_ids = await db.posts.distinct("ad_id", {"status": "active", "bot_id": bot_id})
    
    from bson import ObjectId
    obj_ids = []
    for aid in active_ad_ids:
        try: obj_ids.append(ObjectId(aid))
        except: continue
        
    total_active = len(obj_ids)
    paged_ids = obj_ids[skip : skip + limit]
    
    cursor = db.adscross.find({"_id": {"$in": paged_ids}, "bot_id": bot_id}).sort("created_at", -1)
    ads = [Adscross.from_dict(doc) async for doc in cursor]
    
    if not ads and page == 1:
        buttons = [[InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")]]
        return await callback.message.edit_text(i18n.get("error_no_active_ad", lang=lang), reply_markup=InlineKeyboardMarkup(buttons))
            
    buttons = []
    for ad in ads:
        label = ad.name if ad.name else (ad.content[:20] + "...")
        if not label.strip(): label = f"ID: {str(ad.ad_id)[:8]}"
        
        # Use del_brd_ to trigger message removal from Telegram, or resend_brd_ to delete and restart
        buttons.append([
            InlineKeyboardButton(f"🗑️ {label}", callback_data=f"del_brd_{ad.ad_id}"),
            InlineKeyboardButton(i18n.get("btn_resend", lang=lang, skip_emojis=True), callback_data=f"resend_brd_{ad.ad_id}")
        ])
        
    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"delete_promo_{page-1}"))
    if total_active > skip + limit:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"delete_promo_{page+1}"))
    if nav:
        buttons.append(nav)
    
    # Delete All Active
    buttons.append([InlineKeyboardButton("🛑 TOUT RETIRER DES CANAUX", callback_data="confirm_delete_all_broadcasts")])
    buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")])
    
    await callback.message.edit_text(i18n.get("msg_select_ad_to_delete", lang=lang), reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^confirm_delete_all_broadcasts$"))
async def confirm_delete_all_broadcasts_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_confirm_delete", lang=lang, skip_emojis=True), callback_data="exec_delete_all_broadcasts")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="delete_promo")]
    ]
    await callback.message.edit_text(i18n.get("prompt_confirm_delete_ad", lang=lang), reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^exec_delete_all_broadcasts$"))
async def exec_delete_all_broadcasts_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    active_ad_ids = await db.posts.distinct("ad_id", {"status": "active", "bot_id": bot_id})
    
    if not active_ad_ids:
        return await callback.answer("Aucune diffusion active à supprimer.", show_alert=True)
        
    # Reuse delete_broadcast_posts_callback logic for each ad? Or implement bulk
    # For now, let's just do it sequentially or tell user to wait
    await callback.message.edit_text("⏳ Retrait massif en cours... Veuillez patienter.")
    
    for aid in active_ad_ids:
        # Simplified bulk deletion without multiple progress messages
        cursor = db.posts.find({"ad_id": aid, "status": "active", "bot_id": bot_id})
        posts = [Post.from_dict(p) async for p in cursor]
        for post in posts:
            try:
                await client.delete_messages(post.channel_id, post.message_id)
            except Exception: pass
        await db.posts.update_many({"ad_id": aid, "status": "active", "bot_id": bot_id}, {"$set": {"status": "deleted"}})

    await callback.answer(i18n.get("msg_all_promos_deleted", lang=lang), show_alert=True)
    from .admin import back_to_start
    await back_to_start(client, callback)

@Client.on_callback_query(filters.regex(r"^(susp|cont|del|cdel|info)_ad_(.*)$"))
async def management_actions_callback(client: Client, callback: CallbackQuery):
    action = callback.matches[0].group(1)
    ad_id = callback.matches[0].group(2)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    from bson import ObjectId
    try: obj_id = ObjectId(ad_id)
    except: return await callback.answer(i18n.get("error_invalid_id", lang=lang))
    
    if action == "susp":
        await db.adscross.update_one({"_id": obj_id, "bot_id": bot_id}, {"$set": {"status": AdStatus.SUSPENDED}})
        await callback.answer(i18n.get("msg_ad_suspended", lang=lang))
    elif action == "cont":
        await db.adscross.update_one({"_id": obj_id, "bot_id": bot_id}, {"$set": {"status": AdStatus.ACTIVE}})
        await callback.answer(i18n.get("msg_ad_reactivated", lang=lang))
    elif action == "del":
        # Double confirmation prompt
        buttons = [
            [InlineKeyboardButton(i18n.get("btn_confirm_delete", lang=lang, skip_emojis=True), callback_data=f"cdel_ad_{ad_id}")],
            [InlineKeyboardButton(i18n.get("btn_cancel_delete", lang=lang, skip_emojis=True), callback_data="preview_promo")]
        ]
        await callback.message.edit_text(
            i18n.get("prompt_confirm_delete_ad", lang=lang),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    elif action == "cdel":
        await db.adscross.delete_one({"_id": obj_id, "bot_id": bot_id})
        await callback.answer(i18n.get("msg_ad_deleted", lang=lang))
    elif action == "info":
        ad_doc = await db.adscross.find_one({"_id": obj_id, "bot_id": bot_id})
        if ad_doc:
            ad = Adscross.from_dict(ad_doc)
            info = i18n.get("msg_ad_info_alert", lang=lang, 
                            name=ad.name or i18n.get("msg_none", lang=lang),
                            date=ad.created_at.strftime('%Y-%m-%d %H:%M'),
                            type=ad.ad_type.value,
                            status=ad.status.value)
            return await callback.answer(info, show_alert=True)
            
    # Refresh the list
    if i18n.get("msg_select_ad_to_delete", lang=lang) in callback.message.text:
        await delete_promo_callback(client, callback)
    else:
        await preview_promo_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^edit_ad_(.*)$"))
async def modify_ad_callback(client: Client, callback: CallbackQuery):
    ad_id = callback.matches[0].group(1)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Choice menu
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_edit_content", lang=lang, skip_emojis=True), callback_data=f"edit_cont_{ad_id}")],
        [InlineKeyboardButton(i18n.get("btn_edit_folder_link", lang=lang, skip_emojis=True), callback_data=f"edit_fld_{ad_id}")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="preview_promo")]
    ]
    await callback.message.edit_text(
        i18n.get("prompt_edit_ad_choice", lang=lang),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^(edit_cont|edit_fld)_(.*)$"))
async def process_edit_callback(client: Client, callback: CallbackQuery):
    action = callback.matches[0].group(1)
    ad_id = callback.matches[0].group(2)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Answer early to prevent QueryIdInvalid during get_input
    try: await callback.answer()
    except: pass

    from bson import ObjectId
    try: obj_id = ObjectId(ad_id)
    except: return await callback.answer(i18n.get("error_invalid_id", lang=lang))

    if action == "edit_cont":
        prompt = i18n.get("prompt_edit_ad_content", lang=lang)
        msg = await get_input(client, callback, prompt, lang)
        if msg is None: return
        
        # Preserve formatting using HTML
        content = client.parser.unparse(msg.text or msg.caption or "", msg.entities or msg.caption_entities or [], is_html=True)
            
        media_id = None
        media_type = None
        if msg.photo:
            media_id = msg.photo.file_id
            media_type = "photo"
        elif msg.video:
            media_id = msg.video.file_id
            media_type = "video"
        elif msg.animation:
            media_id = msg.animation.file_id
            media_type = "animation"
        elif msg.document:
            media_id = msg.document.file_id
            media_type = "document"

        update_data = {
            "content": content,
            "media_id": media_id,
            "media_type": media_type,
            "reply_markup": json.loads(str(msg.reply_markup)) if msg.reply_markup else None
        }
        await db.adscross.update_one({"_id": obj_id, "bot_id": bot_id}, {"$set": update_data})
        
    elif action == "edit_fld":
        prompt = i18n.get("prompt_edit_ad_folder_link", lang=lang)
        msg = await get_input(client, callback, prompt, lang)
        if msg is None: return
        
        new_fld = getattr(msg, "text", None) or getattr(msg, "caption", None)
        folder_link = new_fld.strip() if new_fld else ""
        await db.adscross.update_one({"_id": obj_id, "bot_id": bot_id}, {"$set": {"folder_link": folder_link}})
        
    try:
        await callback.answer(i18n.get("msg_ad_updated", lang=lang))
    except Exception:
        # Fallback if callback expired
        await client.send_message(callback.from_user.id, i18n.get("msg_ad_updated", lang=lang))
    
    await preview_promo_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^sel_ad_prev_(.*)$"))
async def select_ad_format_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    ad_id = callback.matches[0].group(1)
    
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_preview_buttons", lang=lang, skip_emojis=True), callback_data=f"gen_prev_{ad_id}_buttons")],
        [InlineKeyboardButton(i18n.get("btn_preview_text", lang=lang, skip_emojis=True), callback_data=f"gen_prev_{ad_id}_text")],
        [InlineKeyboardButton(i18n.get("btn_preview_folder", lang=lang, skip_emojis=True), callback_data=f"gen_prev_{ad_id}_folder")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="preview_promo")]
    ]
    
    await callback.edit_message_text(
        i18n.get("msg_select_preview_format", lang=lang, ad_id=ad_id[:8]),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^gen_prev_(.*)_(buttons|text|folder)$"))
async def generate_ad_preview_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    ad_id = callback.matches[0].group(1)
    format_type = callback.matches[0].group(2)
    
    ad_doc = await db.adscross.find_one({"_id": ad_id, "bot_id": bot_id})
    if not ad_doc:
        # If not found by string ID, try with ObjectId if necessary (but Adscross.ad_id is usually string)
        from bson import ObjectId
        try: ad_doc = await db.adscross.find_one({"_id": ObjectId(ad_id), "bot_id": bot_id})
        except: pass
        
    if not ad_doc:
        return await callback.answer(i18n.get("error_ad_not_found", lang=lang), show_alert=True)
        
    ad = Adscross.from_dict(ad_doc)
    # Override ad_type for preview
    original_type = ad.ad_type
    if format_type == "buttons": ad.ad_type = AdType.BOUTON
    elif format_type == "text": ad.ad_type = AdType.TEXT
    elif format_type == "folder": ad.ad_type = AdType.FOLDER
    
    settings = await db.get_settings(bot_id)
    
    # Load paid promos
    paid_promos = []
    if hasattr(db, "paid_promos"):
        # Share global sponsors (bot_id=main_bot_id) in preview
        query = {"is_active": True, "$or": [{"bot_id": bot_id}, {"bot_id": config.telegram.main_bot_id}]}
        cursor_paid = db.paid_promos.find(query)
        paid_promos = [PaidPromo.from_dict(doc) async for doc in cursor_paid]
    
    from bot.database.models import Channel
    ch_cursor = db.channels.find({"is_active": True, "bot_id": bot_id}).limit(settings.max_buttons or 50)
    all_channels = [Channel.from_dict(doc) async for doc in ch_cursor]
    
    promo_data = PromoGenerator.generate_promo(
        bot_username=client.me.username if client.me else None,
        ad=ad,
        channels=all_channels,
        settings=settings,
        paid_promos=paid_promos,
        is_clone=getattr(client, "is_clone", False)
    )
    
    try:
        # We send as a NEW message to not mess up the menu
        await send_promo_to_channel(
            client=client,
            chat_id=callback.from_user.id,
            text=promo_data["text"],
            parse_mode=enums.ParseMode.HTML if settings.parse_mode == "html" else enums.ParseMode.MARKDOWN,
            reply_markup=promo_data["reply_markup"],
            ad=ad
        )
        await callback.answer(i18n.get("msg_preview_sent", lang=lang))
    except Exception as e:
        await callback.answer(i18n.get("error_preview", lang=lang, error=str(e)), show_alert=True)

@Client.on_callback_query(filters.regex(r"^send_paid_promo$"))
async def send_paid_promo_callback(client: Client, callback: CallbackQuery):
    if getattr(client, "is_clone", False):
        return await callback.answer("Cette fonctionnalité est réservée au bot principal.", show_alert=True)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Step 0: Ask for internal name
    name_msg = await get_input(client, callback, i18n.get("prompt_paid_promo_name", lang=lang), lang)
    if name_msg is None: return
    internal_name = name_msg.text
    await name_msg.delete()
    
    prompt = i18n.get("prompt_paid_promo_start", lang=lang)
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    
    title, link = await get_channel_info(client, msg)
    
    if not title:
        try:
            return await callback.message.edit_text(i18n.get("error_paid_promo_fetch", lang=lang))
        except:
            return await callback.message.reply_text(i18n.get("error_paid_promo_fetch", lang=lang))
        
    if not link:
        prompt_url = i18n.get("prompt_paid_promo_url_manual", lang=lang)
        msg_url = await get_input(client, callback, prompt_url, lang)
        if msg_url is None: return
        link = msg_url.text

    import uuid
    promo_id = str(uuid.uuid4())
    pending_paid_promos[callback.from_user.id] = {
        "promo_id": promo_id,
        "name": internal_name,
        "text": title,
        "url": link,
        "categories": [],
        "languages": []
    }
    
    await show_target_categories(client, callback, lang)

async def show_target_categories(client, callback, lang):
    cat_keys = ["crypto", "humor", "news", "gaming", "movies", "series", "anime", "business", "music", "sport", "tech", "art", "food", "fashion", "books", "other"]
    buttons = []
    row = []
    for k in cat_keys:
        row.append(InlineKeyboardButton(i18n.get(f"cat_{k}", lang=lang, skip_emojis=True), callback_data=f"tgt_cat_{k}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(i18n.get("btn_all_categories", lang=lang, skip_emojis=True), callback_data="tgt_cat_all")])
    
    await callback.message.edit_text(
        i18n.get("prompt_paid_promo_target_cat", lang=lang),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^tgt_cat_(.*)$"))
async def target_category_selected(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    cat = callback.matches[0].group(1)
    
    data = pending_paid_promos.get(callback.from_user.id)
    if not data: return
    
    if cat != "all":
        data["categories"] = [cat]
    else:
        data["categories"] = []
        
    await show_target_languages(client, callback, lang)

async def show_target_languages(client, callback, lang):
    langs = ["fr", "en", "ar"]
    buttons = []
    for l in langs:
        buttons.append([InlineKeyboardButton(l.upper(), callback_data=f"tgt_lang_{l}")])
    buttons.append([InlineKeyboardButton(i18n.get("btn_all_languages", lang=lang, skip_emojis=True), callback_data="tgt_lang_all")])
    
    await callback.message.edit_text(
        i18n.get("prompt_paid_promo_target_lang", lang=lang),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^tgt_lang_(.*)$"))
async def target_language_selected(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    l = callback.matches[0].group(1)
    
    data = pending_paid_promos.pop(callback.from_user.id, None)
    if not data: return
    
    if l != "all":
        data["languages"] = [l]
    else:
        data["languages"] = []
        
    from ..database.models import PaidPromo
    new_promo = PaidPromo(
        promo_id=data["promo_id"],
        owner_id=callback.from_user.id,
        name=data.get("name"),
        text=data["text"],
        url=data["url"],
        categories=data["categories"],
        languages=data["languages"],
        bot_id=bot_id
    )
    
    if not hasattr(db, "paid_promos"):
        db.paid_promos = db.db["paid_promos"]
        
    await db.paid_promos.insert_one(new_promo.to_dict())
    await callback.answer(i18n.get("msg_paid_promo_added", lang=lang, text=data["text"]), show_alert=True)
    
    from .admin import back_to_start
    await back_to_start(client, callback)
    
@Client.on_callback_query(filters.regex(r"^delete_paid_promo(_(\d+))?$"))
async def delete_paid_promo_callback(client: Client, callback: CallbackQuery):
    if getattr(client, "is_clone", False):
        return await callback.answer("Cette fonctionnalité est réservée au bot principal.", show_alert=True)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    if not hasattr(db, "paid_promos"):
        db.paid_promos = db.db["paid_promos"]
        
    page = 1
    if callback.data.startswith("delete_paid_promo_"):
        try: page = int(callback.data.split("_")[-1])
        except: page = 1
    elif hasattr(callback, "matches") and callback.matches and len(callback.matches[0].groups()) >= 2:
        try:
            val = callback.matches[0].group(2)
            if val: page = int(val)
        except: page = 1
        
    limit = 5
    skip = (page - 1) * limit
    
    cursor = db.paid_promos.find({"bot_id": bot_id}).sort("added_date", -1).skip(skip).limit(limit)
    promos = [PaidPromo.from_dict(doc) async for doc in cursor]
    total_promos = await db.paid_promos.count_documents({"bot_id": bot_id})
    
    if not promos and page == 1:
        # If no promos, offer to clean all or back
        buttons = [[InlineKeyboardButton(i18n.get("btn_back", lang, skip_emojis=True), callback_data="start")]]
        return await callback.message.edit_text(i18n.get("error_no_active_ad", lang=lang), reply_markup=InlineKeyboardMarkup(buttons))

    buttons = []
    for p in promos:
        label = p.name if p.name else (p.text[:20] + "...")
        buttons.append([InlineKeyboardButton(f"💲 {label}", callback_data="noop")])
        buttons.append([
            InlineKeyboardButton("🗑️", callback_data=f"del_paid_{p.promo_id}"),
            InlineKeyboardButton("👁️", url=p.url)
        ])
    
    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"delete_paid_promo_{page-1}"))
    if total_promos > skip + limit:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"delete_paid_promo_{page+1}"))
    if nav: buttons.append(nav)
    
    # Delete All option
    buttons.append([InlineKeyboardButton("🛑 SUPPRIMER TOUT", callback_data="confirm_delete_paid_all")])
    buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")])
    
    await callback.message.edit_text(
        i18n.get("msg_select_paid_promo_to_manage", lang=lang),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^del_paid_(.*)$"))
async def del_single_paid_callback(client: Client, callback: CallbackQuery):
    promo_id = callback.matches[0].group(1)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Double confirmation
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_confirm_delete", lang=lang, skip_emojis=True), callback_data=f"cpdel_{promo_id}")],
        [InlineKeyboardButton(i18n.get("btn_cancel_delete", lang=lang, skip_emojis=True), callback_data="delete_paid_promo")]
    ]
    await callback.message.edit_text(
        i18n.get("prompt_confirm_delete_ad", lang=lang),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^cpdel_(.*)$"))
async def confirm_single_paid_delete_callback(client: Client, callback: CallbackQuery):
    promo_id = callback.matches[0].group(1)
    if not hasattr(db, "paid_promos"):
        db.paid_promos = db.db["paid_promos"]
        
    bot_id = client.me.id
    await db.paid_promos.delete_one({"promo_id": promo_id, "bot_id": bot_id})
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    await callback.answer(i18n.get("msg_ad_deleted", lang=lang))
    await delete_paid_promo_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^confirm_delete_paid_all$"))
async def confirm_delete_paid_all_callback(client: Client, callback: CallbackQuery):
    if not hasattr(db, "paid_promos"):
        db.paid_promos = db.db["paid_promos"]
        
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    await db.paid_promos.delete_many({"bot_id": bot_id})
    await callback.answer(i18n.get("msg_paid_promos_deleted", lang=lang), show_alert=True)
    
    from .admin import back_to_start
    await back_to_start(client, callback)

@Client.on_callback_query(filters.regex(r"^send_promo(_(\d+))?$"))
async def send_promo_callback(client: Client, callback: CallbackQuery):
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    page = 1
    if callback.matches[0].group(2):
        page = int(callback.matches[0].group(2))
        
    limit = 5
    skip = (page - 1) * limit
    
    # List only active ads for sending
    query = {"status": AdStatus.ACTIVE, "bot_id": bot_id}
    cursor = db.adscross.find(query).sort("created_at", -1).skip(skip).limit(limit)
    ads = [Adscross.from_dict(doc) async for doc in cursor]
    total_ads = await db.adscross.count_documents(query)
    
    if not ads and page == 1:
        return await callback.answer(i18n.get("error_no_active_ad", lang=lang), show_alert=True)

    buttons = []
    for ad in ads:
        label = ad.name if ad.name else (ad.content[:20] + "...")
        buttons.append([InlineKeyboardButton(f"🚀 {label}", callback_data=f"sel_send_{ad.ad_id}")])
    
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"send_promo_{page-1}"))
    if total_ads > skip + limit:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"send_promo_{page+1}"))
    if nav: buttons.append(nav)
    
    buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")])
    
    await callback.message.edit_text(
        i18n.get("msg_select_ad_to_preview", lang=lang), # Reusing similar string
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^sel_send_(.*)$"))
async def select_send_ad_callback(client: Client, callback: CallbackQuery):
    ad_id = callback.matches[0].group(1)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # Choose format
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_preview_buttons", lang, skip_emojis=True), callback_data=f"exec_send_{ad_id}_button")],
        [InlineKeyboardButton(i18n.get("btn_preview_text", lang, skip_emojis=True), callback_data=f"exec_send_{ad_id}_text")],
        [InlineKeyboardButton(i18n.get("btn_preview_folder", lang, skip_emojis=True), callback_data=f"exec_send_{ad_id}_folder")],
        [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="send_promo")]
    ]
    
    await callback.message.edit_text(
        i18n.get("msg_select_preview_format", lang=lang, ad_id=ad_id[:8]),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
        
@Client.on_callback_query(filters.regex(r"^exec_send_(.*)_(button|text|folder)$"))
async def exec_send_promo_callback(client: Client, callback: CallbackQuery):
    ad_id = callback.matches[0].group(1)
    fmt_choice = callback.matches[0].group(2)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    from bson import ObjectId
    ad_doc = await db.adscross.find_one({"_id": ObjectId(ad_id), "bot_id": bot_id})
    if not ad_doc:
        return await callback.answer(i18n.get("error_ad_not_found", lang=lang), show_alert=True)
    
    ad = Adscross.from_dict(ad_doc)
    # Override ad type based on selection
    if fmt_choice == "button": ad.ad_type = AdType.BOUTON
    elif fmt_choice == "text": ad.ad_type = AdType.TEXT
    elif fmt_choice == "folder": ad.ad_type = AdType.FOLDER
    
    from datetime import datetime
    await db.adscross.update_one({"_id": ObjectId(ad_id), "bot_id": bot_id}, {"$set": {"last_sent_at": datetime.now()}})
 
    ch_cursor = db.channels.find({"is_active": True, "bot_id": bot_id})
    from bot.database.models import Channel
    all_channels = [Channel.from_dict(doc) async for doc in ch_cursor]
    
    if not all_channels:
        return await callback.answer(i18n.get("error_no_channels", lang=lang), show_alert=True)
        
    all_channels_dict = {ch.channel_id: ch for ch in all_channels}
    target_ch_objects = all_channels
    
    if not target_ch_objects:
        return await callback.answer(i18n.get("error_no_target_channels", lang=lang), show_alert=True)
 
    settings = await db.get_settings(bot_id)
    paid_promos = []
    if hasattr(db, "paid_promos"):
        # Share main bot sponsors (bot_id=main_bot_id) with clones
        cursor_paid = db.paid_promos.find({"is_active": True, "$or": [{"bot_id": bot_id}, {"bot_id": config.telegram.main_bot_id}]})
        paid_promos = [PaidPromo.from_dict(doc) async for doc in cursor_paid]

    # Progress message (NEW MESSAGE to free the menu)
    success = 0
    failed = 0
    total = len(target_ch_objects)
    
    progress_msg = await client.send_message(
        chat_id=callback.from_user.id,
        text=i18n.get("msg_broadcast_progress", lang=lang, success=0, failed=0, remaining=total)
    )
    
    # Restore admin menu for the callback
    from .admin import back_to_start
    await back_to_start(client, callback)

    
    parse_mode = enums.ParseMode.HTML if settings.parse_mode == "html" else enums.ParseMode.MARKDOWN
    bot_username = client.me.username if client.me else None
    
    chunk_size = settings.max_buttons if settings.max_buttons > 0 else 50
    chunks = [target_ch_objects[i:i + chunk_size] for i in range(0, len(target_ch_objects), chunk_size)]
    
    for chunk in chunks:
        promo_data = PromoGenerator.generate_promo(
            bot_username=bot_username,
            ad=ad,
            channels=chunk,
            settings=settings,
            paid_promos=paid_promos,
            is_clone=getattr(client, "is_clone", False)
        )
        
        for ch in chunk:
            try:
                msg = await send_promo_to_channel(
                    client=client,
                    chat_id=ch.channel_id,
                    text=promo_data["text"],
                    parse_mode=parse_mode,
                    reply_markup=promo_data["reply_markup"],
                    ad=ad
                )

                await db.add_post(Post(ad_id=str(ad.ad_id), channel_id=ch.channel_id, message_id=msg.id, bot_id=bot_id))
                success += 1
                # Reset failures on success
                await db.reset_channel_failures(ch.channel_id)
            except RPCError as e:
                logger.error(f"Telegram RPC error sending to {ch.channel_id}: {e}")
                failed += 1
                await handle_channel_failure(client, ch.channel_id)
            except Exception as e:
                logger.error(f"Unexpected error sending to {ch.channel_id} ({type(e).__name__}): {e}")
                failed += 1
                await handle_channel_failure(client, ch.channel_id)
            
            # Update progress every 5 channels to avoid flood
            if (success + failed) % 5 == 0:
                try:
                    await progress_msg.edit_text(
                        i18n.get("msg_broadcast_progress", lang=lang, success=success, failed=failed, remaining=total-(success+failed))
                    )
                except: pass

    # Final Report
    import pendulum
    tz = settings.fuseau_horaire or "UTC"
    now = pendulum.now(tz)
    delete_time = now.add(minutes=settings.delete_after_minutes).format("HH:mm") if settings.auto_delete_ads else "N/A"
    
    # Calculate Next Publication using helper
    next_pub = get_next_pub_time(ad.schedule_times, ad.schedule_days, tz)

    report_text = i18n.get("msg_broadcast_report", lang=lang, success=success, failed=failed, delete_time=delete_time, next_time=next_pub)
    
    # Save report metadata to DB for later editing by scheduler
    await db.adscross.update_one(
        {"_id": ad.ad_id, "bot_id": bot_id}, 
        {"$set": {
            "report_message_id": progress_msg.id, 
            "report_chat_id": callback.message.chat.id
        }}
    )
    
    buttons = [
        [InlineKeyboardButton(i18n.get("btn_resend", lang=lang, skip_emojis=True), callback_data=f"sel_send_{ad.ad_id}")],
        [InlineKeyboardButton(i18n.get("btn_delete_posts", lang=lang, skip_emojis=True), callback_data=f"del_brd_{ad.ad_id}")],
        [InlineKeyboardButton(i18n.get("btn_cancel_broadcast", lang=lang, skip_emojis=True), callback_data="start")]
    ]
    
    await progress_msg.edit_text(report_text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^resend_brd_(.*)$"))
async def resend_broadcast_callback(client: Client, callback: CallbackQuery):
    ad_id = callback.matches[0].group(1)
    # 1. Delete active posts
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
    
    # 1. Delete active posts
    posts = await db.get_active_posts(bot_id)
    count = 0
    for p in posts:
        if p.ad_id == ad_id:
            try:
                await client.delete_messages(p.channel_id, p.message_id)
                await db.mark_post_deleted(p.ad_id, p.channel_id, p.message_id, bot_id)
                count += 1
            except Exception as e:
                logger.error(f"Error deleting post from {p.channel_id} during resend: {e}")
                pass
    
    # 2. Inform user and proceed to resend menu
    # await callback.answer(i18n.get("msg_posts_deleted_count", lang=lang, count=count)) # Optional flash
    
    # Reuse select_send_ad_callback logic
    # We need to manually call it or trigger it
    # Since select_send_ad_callback uses regex matches, we should mock it or just call it directly with tweaked callback
    callback.data = f"sel_send_{ad_id}" # Tweak data for the next handler if needed (though we call it)
    await select_send_ad_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^del_brd_(.*)$"))
async def delete_broadcast_posts_callback(client: Client, callback: CallbackQuery):
    ad_id = callback.matches[0].group(1)
    bot_id = client.me.id
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    
    if not is_admin_or_owner(client, callback.from_user.id, user):
        return await callback.answer(i18n.get("admin_access_denied", lang=lang), show_alert=True)
        
    # Delete all active posts for this ad
    posts = await db.get_active_posts(bot_id)
    count = 0
    for p in posts:
        if p.ad_id == ad_id:
            try:
                await client.delete_messages(p.channel_id, p.message_id)
                await db.mark_post_deleted(p.ad_id, p.channel_id, p.message_id, bot_id)
                count += 1
            except Exception as e:
                logger.error(f"Error deleting post from {p.channel_id}: {e}", exc_info=True)
                pass
    
    user = await db.get_user(callback.from_user.id, bot_id)
    lang = user.language if user else "fr"
    await callback.answer(i18n.get("msg_posts_deleted_count", lang=lang, count=count), show_alert=True)
    
    # Refresh logic
    if i18n.get("msg_select_ad_to_delete", lang=lang) in (callback.message.text or ""):
        await delete_promo_callback(client, callback)
    else:
        from .admin import back_to_start
        await back_to_start(client, callback)

