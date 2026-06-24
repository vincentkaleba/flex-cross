from pyrogram import Client, filters, enums
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from ..database.database import db
from ..utils.i18n import i18n
from ..utils.menu import Menu
from .admin import get_input
import asyncio
from langdetect import detect
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from ..config import config
import logging
from ..utils.media_manager import download_channel_photo

logger = logging.getLogger(__name__)

menu_manager = Menu()

@Client.on_callback_query(filters.regex(r"^add_channel$"))
async def add_channel_callback(client: Client, callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    prompt = i18n.get("prompt_add_channel", lang=lang, default="Envoyez l'ID, le @username ou transférez un message de votre canal :")
    msg = await get_input(client, callback, prompt, lang)
    if msg is None: return
    
    chat_id = None
    if msg.forward_from_chat:
        chat_id = msg.forward_from_chat.id
    elif msg.text:
        chat_id = msg.text.strip()
        if chat_id.isdigit() or chat_id.startswith("-100"):
            chat_id = int(chat_id)
            
    if not chat_id:
        await callback.answer(i18n.get("error_channel_not_found", lang=lang, default="Canal introuvable."), show_alert=True)
        from .admin import back_to_start
        return await back_to_start(client, callback)
        
    await msg.delete() # Delete user's message to keep chat clean
    info_msg = callback.message
    await info_msg.edit_text(i18n.get("msg_channel_processing", lang=lang, default="Analyse..."))
    
    try:
        chat = await client.get_chat(chat_id)
        if chat.type != enums.ChatType.CHANNEL:
            await info_msg.edit_text(i18n.get("error_not_a_channel", lang=lang, default="Ce n'est pas un canal."))
            from .admin import back_to_start
            await asyncio.sleep(3)
            return await back_to_start(client, callback)
            
        real_chat_id = chat.id
        
        # Member count validation (Only at addition)
        settings = await db.get_settings(client.me.id)
        if chat.members_count < settings.min_members:
            await info_msg.edit_text(i18n.get("error_min_members", lang=lang, min=settings.min_members))
            return
        if chat.members_count > settings.max_members:
            await info_msg.edit_text(i18n.get("error_max_members", lang=lang, max=settings.max_members))
            return
    except Exception as e:
        await info_msg.edit_text(i18n.get("error_channel_not_found", lang=lang, default="Canal introuvable."))
        from .admin import back_to_start
        await asyncio.sleep(3)
        return await back_to_start(client, callback)
        
    try:
        bot_member = await client.get_chat_member(real_chat_id, "me")
        if bot_member.status != enums.ChatMemberStatus.ADMINISTRATOR or not bot_member.privileges.can_post_messages or not bot_member.privileges.can_invite_users:
            await info_msg.edit_text(i18n.get("error_bot_not_admin", lang=lang, default="Le bot n'a pas les droits requis."))
            return
    except Exception:
        await info_msg.edit_text(i18n.get("error_bot_not_admin", lang=lang, default="Impossible de vérifier les droits du bot."))
        return
        
    try:
        user_member = await client.get_chat_member(real_chat_id, callback.from_user.id)
        if user_member.status == enums.ChatMemberStatus.OWNER:
            pass
        elif user_member.status == enums.ChatMemberStatus.ADMINISTRATOR and getattr(user_member.privileges, "can_invite_users", False):
            pass
        else:
            await info_msg.edit_text(i18n.get("error_user_not_admin", lang=lang, default="Vous devez être administrateur avec droit d'invitation."))
            return
    except Exception:
        await info_msg.edit_text(i18n.get("error_user_not_admin", lang=lang, default="Impossible de vérifier vos droits."))
        return
        
    invite_link = chat.invite_link
    if not invite_link:
        try:
            invite_link = await client.export_chat_invite_link(real_chat_id)
        except Exception:
            invite_link = ""
            
    promo_link = ""
    try:
        promo_obj = await client.create_chat_invite_link(real_chat_id, name="AdsBot Promo")
        promo_link = promo_obj.invite_link
    except Exception:
        pass
            
    owner_id = callback.from_user.id
    try:
        admin_list = []
        async for adm in client.get_chat_members(real_chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
            admin_list.append(adm)
        for adm in admin_list:
            if adm.status == enums.ChatMemberStatus.OWNER:
                owner_id = adm.user.id
                break
    except Exception:
        pass
        
    text_content = ""
    try:
        async for hist_msg in client.get_chat_history(real_chat_id, limit=20):
            if hist_msg.text: text_content += hist_msg.text + " "
            elif hist_msg.caption: text_content += hist_msg.caption + " "
    except Exception:
        pass
        
    detected_lang = "fr"
    if text_content.strip():
        try:
            detected_lang = detect(text_content)
        except Exception:
            pass
            
    about = getattr(chat, "description", "") or ""
    photo_filename = await download_channel_photo(client, chat)
    
    temp_data = {
        "channel_id": real_chat_id,
        "bot_id": client.me.id,
        "title": chat.title,
        "username": chat.username,
        "link": invite_link or (f"https://t.me/{chat.username}" if chat.username else ""),
        "promo_link": promo_link,
        "owner_id": owner_id,
        "added_by": callback.from_user.id,
        "language": detected_lang,
        "about": about,
        "photo": photo_filename,
        "is_active": False # Pending category selection
    }
    
    await db.channels.update_one(
        {"channel_id": real_chat_id, "bot_id": client.me.id},
        {"$set": temp_data},
        upsert=True
    )
    
    prompt_cat = i18n.get("prompt_category", lang=lang, title=chat.title, detected_lang=detected_lang.upper(), default="Choisissez la catégorie :")
    reply_markup = menu_manager.get_menu("categories", lang=lang, channel_id=real_chat_id)
    await info_msg.edit_text(prompt_cat, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^set_cat_(.*)_(.*)$"))
async def set_category_callback(client: Client, callback: CallbackQuery):
    cat_key = callback.matches[0].group(1)
    channel_id_str = callback.matches[0].group(2)
    
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    try:
        channel_id = int(channel_id_str)
    except ValueError:
        return await callback.answer(i18n.get("error_invalid_id", lang=lang), show_alert=True)
        
    doc = await db.channels.find_one({"channel_id": channel_id, "bot_id": client.me.id})
    if not doc or doc.get("added_by") != callback.from_user.id:
        return await callback.answer("Opération invalide ou expirée.", show_alert=True)
        
    await db.channels.update_one(
        {"channel_id": channel_id, "bot_id": client.me.id},
        {"$set": {"category": cat_key, "is_active": True, "members_count": 0, "is_banned": False}}
    )
    
    success_text = i18n.get("msg_channel_added", lang=lang, title=doc.get("title"), default="Canal ajouté avec succès !")
    await callback.message.edit_text(success_text)
    
    # Send notification to logs channel
    if config.telegram.log_channel_id:
        try:
            log_text = i18n.get(
                "log_new_channel",
                lang=lang,
                user=callback.from_user.mention,
                title=doc.get("title"),
                channel_id=channel_id,
                category=i18n.get(f"cat_{cat_key}", lang=lang),
                language=doc.get("language", "N/A").upper()
            )
            await client.send_message(
                chat_id=config.telegram.log_channel_id,
                text=log_text,
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error sending new channel log: {e}")
    
    await asyncio.sleep(2)
    from .admin import back_to_start
    await back_to_start(client, callback)

import math

@Client.on_callback_query(filters.regex(r"^my_channels(?:_(\d+))?$"))
async def my_channels_callback(client: Client, callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    page = 0
    if callback.matches and callback.matches[0].group(1):
        page = int(callback.matches[0].group(1))
        
    limit = 5
    skip = page * limit
    
    cursor = db.channels.find({"added_by": callback.from_user.id, "is_active": True, "bot_id": client.me.id}).sort("_id", 1)
    total_channels = await db.channels.count_documents({"added_by": callback.from_user.id, "is_active": True, "bot_id": client.me.id})
    
    channels = []
    async for ch in cursor.skip(skip).limit(limit):
        channels.append(ch)
        
    total_pages = math.ceil(total_channels / limit) or 1
    
    if total_channels == 0:
        text = i18n.get("user_no_channels", lang=lang, default="Vous n'avez publié aucun canal pour le moment.")
    else:
        text = i18n.get("user_my_channels_msg", lang=lang, total=total_channels, default=f"<b>Vos Canaux ({total_channels})</b>\n\nSélectionnez un canal pour voir ses détails :")
        
    reply_markup = menu_manager.get_menu("user_my_channels", lang=lang, channels=channels, page=page, total_pages=total_pages)
    if callback.message.photo:
        from pyrogram.types import InputMediaPhoto
        from ..config import config
        if getattr(config.telegram, "start_image", None):
            await callback.edit_message_media(InputMediaPhoto(config.telegram.start_image, caption=text), reply_markup=reply_markup)
        else:
            await callback.message.delete()
            await callback.message.reply_text(text, reply_markup=reply_markup)
    else:
        await callback.edit_message_text(text, reply_markup=reply_markup)

async def show_user_channel_info(client: Client, callback: CallbackQuery, channel_id: int):
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    ch = await db.channels.find_one({"channel_id": channel_id, "added_by": callback.from_user.id, "bot_id": client.me.id})
    if not ch:
        return await callback.answer(i18n.get("error_channel_not_found", lang=lang, default="Canal introuvable."), show_alert=True)
        
    text = i18n.get("user_channel_details", lang=lang, 
                    title=ch.get("title", i18n.get("msg_none", lang=lang)), 
                    username=ch.get("username") or i18n.get("msg_private", lang=lang), 
                    category=i18n.get(f"cat_{ch.get('category', 'other')}", lang=lang),
                    lang_cat=ch.get("language", i18n.get("msg_none", lang=lang)).upper(),
                    members=ch.get("members_count", 0))
                    
    reply_markup = menu_manager.get_menu("user_channel_info", lang=lang, channel_id=channel_id)
    if callback.message.photo:
        from pyrogram.types import InputMediaPhoto
        from ..config import config
        if getattr(config.telegram, "start_image", None):
            await callback.edit_message_media(InputMediaPhoto(config.telegram.start_image, caption=text), reply_markup=reply_markup)
        else:
            await callback.message.delete()
            await callback.message.reply_text(text, reply_markup=reply_markup)
    else:
        await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^uchannel_(-?\d+)$"))
async def user_channel_info_callback(client: Client, callback: CallbackQuery):
    channel_id = int(callback.matches[0].group(1))
    await show_user_channel_info(client, callback, channel_id)

@Client.on_callback_query(filters.regex(r"^udel_(-?\d+)$"))
async def user_remove_channel_callback(client: Client, callback: CallbackQuery):
    channel_id = int(callback.matches[0].group(1))
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    text = i18n.get("prompt_confirm_remove", lang=lang, default="Êtes-vous sûr de vouloir retirer ce canal de la plateforme ? Cette action est irréversible.")
    reply_markup = menu_manager.get_menu("user_confirm_remove", lang=lang, channel_id=channel_id)
    await callback.edit_message_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^uconfirm_(-?\d+)$"))
async def user_confirm_remove_callback(client: Client, callback: CallbackQuery):
    channel_id = int(callback.matches[0].group(1))
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    
    ch = await db.channels.find_one({"channel_id": channel_id, "added_by": callback.from_user.id, "bot_id": client.me.id})
    if ch:
        # Send notification to logs channel before deletion
        if config.telegram.log_channel_id:
            try:
                log_text = i18n.get(
                    "log_removed_channel",
                    lang=lang,
                    user=callback.from_user.mention,
                    title=ch.get("title"),
                    channel_id=channel_id
                )
                await client.send_message(
                    chat_id=config.telegram.log_channel_id,
                    text=log_text,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Error sending removed channel log: {e}")

        await db.channels.delete_one({"channel_id": channel_id, "added_by": callback.from_user.id, "bot_id": client.me.id})
    
    await callback.answer(i18n.get("user_channel_removed", lang=lang, default="Canal retiré avec succès."), show_alert=True)
    
    # Refresh channels list
    callback.matches = None
    await my_channels_callback(client, callback)

@Client.on_callback_query(filters.regex(r"^ustat_(-?\d+)(?:_(\d+))?$"))
async def user_channel_stats_callback(client: Client, callback: CallbackQuery):
    channel_id = int(callback.matches[0].group(1))
    days = 7
    if callback.matches[0].group(2):
        days = int(callback.matches[0].group(2))
        
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    ch = await db.channels.find_one({"channel_id": channel_id, "added_by": callback.from_user.id, "bot_id": client.me.id})
    if not ch:
        return await callback.answer(i18n.get("error_channel_not_found", lang=lang, default="Canal introuvable."), show_alert=True)
        
    try:
        total_members = await client.get_chat_members_count(channel_id)
        await db.channels.update_one({"_id": ch["_id"]}, {"$set": {"members_count": total_members}})
    except Exception:
        total_members = ch.get("members_count", 0)
        
    bot_joins = 0
    promo_link = ch.get("promo_link")
    if promo_link:
        try:
            invite_obj = await client.get_chat_invite_link(channel_id, promo_link)
            bot_joins = invite_obj.member_count or 0
        except Exception:
            pass
            
    history = ch.get("history", [])
    
    import pendulum
    now = pendulum.now()
    
    def get_diff(days_ago):
        target_date = now.subtract(days=days_ago).format("YYYY-MM-DD")
        for h in reversed(history):
            if h["date"] <= target_date:
                return h
        return None
        
    day_1 = get_diff(1)
    day_7 = get_diff(7)
    day_30 = get_diff(30)
    
    def format_diff(past_obj):
        if not past_obj: return "N/A"
        diff = total_members - past_obj["total"]
        bot_diff = bot_joins - past_obj.get("bot_joins", 0)
        return i18n.get("msg_growth_format", lang=lang, diff=diff, bot_diff=bot_diff)
        
    d1_str = format_diff(day_1)
    d7_str = format_diff(day_7)
    d30_str = format_diff(day_30)
    
    text = i18n.get("msg_user_stats_growth_header", lang=lang, title=ch.get('title', i18n.get("msg_none", lang=lang)), total=total_members, bot_joins=bot_joins) + "\n\n"
    text += i18n.get("msg_user_stats_growth_24h", lang=lang, val=d1_str) + "\n"
    text += i18n.get("msg_user_stats_growth_7d", lang=lang, val=d7_str) + "\n"
    text += i18n.get("msg_user_stats_growth_30d", lang=lang, val=d30_str) + "\n\n"
    text += i18n.get("msg_user_stats_growth_note", lang=lang)
        
    reply_markup = menu_manager.get_menu("user_stats_ranges", lang=lang, channel_id=channel_id)
    
    loading_msg = i18n.get("msg_generating_graph", lang=lang, default="Génération du graphique en cours...")
    try:
        if callback.message.photo:
            await callback.edit_message_caption(caption=loading_msg)
        else:
            await callback.edit_message_text(loading_msg)
    except Exception:
        pass
    
    from ..utils.plotter import generate_growth_chart
    # We will generate a chart and reply with sending a photo with text!
    chart_io = generate_growth_chart(history, days, lang)
    
    try:
        if callback.message.photo:
            # We must edit media
            from pyrogram.types import InputMediaPhoto
            await callback.edit_message_media(InputMediaPhoto(chart_io, caption=text), reply_markup=reply_markup)
        else:
            # We must delete current msg and send photo
            await callback.message.delete()
            await callback.message.reply_photo(chart_io, caption=text, reply_markup=reply_markup)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error drawing chart: {e}")
        # fallback
        try:
            await callback.edit_message_text(text, reply_markup=reply_markup)
        except:
            pass

@Client.on_callback_query(filters.regex(r"^uedit_(-?\d+)$"))
async def user_edit_channel_callback(client: Client, callback: CallbackQuery):
    channel_id = int(callback.matches[0].group(1))
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    text = i18n.get("prompt_user_edit_choice", lang=lang, default="<b>Que souhaitez-vous modifier ?</b>")
    reply_markup = menu_manager.get_menu("user_edit_options", lang=lang, channel_id=channel_id)
    
    try:
        await callback.edit_message_text(text, reply_markup=reply_markup)
    except:
        pass

@Client.on_callback_query(filters.regex(r"^ucat_(-?\d+)$"))
async def user_set_category_prompt_callback(client: Client, callback: CallbackQuery):
    channel_id = int(callback.matches[0].group(1))
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    text = i18n.get("prompt_select_category", lang=lang, default="Veuillez sélectionner une catégorie :")
    reply_markup = menu_manager.get_menu("categories", lang=lang, channel_id=channel_id, is_admin=False)
    
    try:
        await callback.edit_message_text(text, reply_markup=reply_markup)
    except:
        pass

@Client.on_callback_query(filters.regex(r"^uset_cat_(.*)_(-?\d+)$"))
async def user_set_category_callback(client: Client, callback: CallbackQuery):
    cat = callback.matches[0].group(1)
    channel_id = int(callback.matches[0].group(2))
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    # Verify ownership
    ch = await db.channels.find_one({"channel_id": channel_id, "added_by": callback.from_user.id, "bot_id": client.me.id})
    if not ch:
        return await callback.answer(i18n.get("error_channel_not_found", lang=lang), show_alert=True)
        
    await db.channels.update_one({"channel_id": channel_id}, {"$set": {"category": cat}})
    await callback.answer(i18n.get("msg_user_channel_updated", lang=lang), show_alert=True)
    await show_user_channel_info(client, callback, channel_id)

@Client.on_callback_query(filters.regex(r"^ulang_(-?\d+)$"))
async def user_set_language_prompt_callback(client: Client, callback: CallbackQuery):
    channel_id = int(callback.matches[0].group(1))
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    text = i18n.get("msg_select_lang", lang=lang, default="Veuillez sélectionner la langue du canal :")
    reply_markup = menu_manager.get_menu("user_select_lang", lang=lang, channel_id=channel_id)
    
    try:
        await callback.edit_message_text(text, reply_markup=reply_markup)
    except:
        pass

@Client.on_callback_query(filters.regex(r"^uslang_(.*)_(-?\d+)$"))
async def user_set_language_callback(client: Client, callback: CallbackQuery):
    new_lang = callback.matches[0].group(1)
    channel_id = int(callback.matches[0].group(2))
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    
    # Verify ownership
    ch = await db.channels.find_one({"channel_id": channel_id, "added_by": callback.from_user.id, "bot_id": client.me.id})
    if not ch:
        return await callback.answer(i18n.get("error_channel_not_found", lang=lang), show_alert=True)
        
    await db.channels.update_one({"channel_id": channel_id}, {"$set": {"language": new_lang}})
    await callback.answer(i18n.get("msg_user_channel_updated", lang=lang), show_alert=True)
    await show_user_channel_info(client, callback, channel_id)

@Client.on_callback_query(filters.regex(r"^(promote|stats|rules)$"))
async def user_features_placeholder(client: Client, callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id, client.me.id)
    lang = user.language if user else "fr"
    await callback.answer(i18n.get("menu_wip", lang=lang, default="Fonctionnalité en cours de développement... 🚧"), show_alert=True)
