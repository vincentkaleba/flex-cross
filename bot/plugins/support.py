from pyrogram import Client, filters, enums
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from ..database.database import db
from ..database.models import SupportTicket
from ..utils.i18n import i18n
from ..config import config
from pyrogram.errors import RPCError
import logging

logger = logging.getLogger(__name__)

@Client.on_callback_query(filters.regex("^start_support$"))
async def start_support_callback(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    bot_id = client.me.id
    user = await db.get_user(user_id, bot_id)
    lang = user.language if user else "fr"
    
    active_ticket = await db.db["support_tickets"].find_one({"user_id": user_id, "bot_id": bot_id, "status": {"$ne": "closed"}})
    if active_ticket:
        return await callback.answer(i18n.get("msg_support_already_active", lang=lang), show_alert=True)
        
    ticket = SupportTicket(user_id=user_id, bot_id=bot_id)
    result = await db.db["support_tickets"].insert_one(ticket.to_dict())
    ticket_id = str(result.inserted_id)
    
    close_markup = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.get("btn_close_ticket", lang=lang, skip_emojis=True), callback_data=f"close_ticket_{ticket_id}")]])
    await callback.message.edit_text(i18n.get("msg_support_intro", lang=lang), reply_markup=close_markup)
    
    admins = await db.get_admins(bot_id)
    name = f"{callback.from_user.first_name} {callback.from_user.last_name or ''}".strip()
    
    admin_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.get("btn_take_charge", lang="fr", skip_emojis=True), callback_data=f"take_charge_{ticket_id}")]
    ])
    
    for admin in admins:
        try:
            admin_lang = admin.language or "fr"
            text = i18n.get("msg_support_requested", lang=admin_lang, name=name, user_id=user_id, ticket_id=ticket_id)
            await client.send_message(admin.user_id, text, reply_markup=admin_markup)
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin.user_id} about support request: {e}")

@Client.on_callback_query(filters.regex(r"^take_charge_(.*)$"))
async def take_charge_callback(client: Client, callback: CallbackQuery):
    ticket_id = callback.matches[0].group(1)
    admin_id = callback.from_user.id
    
    ticket = await db.get_ticket(ticket_id)
    if not ticket or ticket.status != "open":
        return await callback.answer("Ticket déjà pris en charge ou fermé.", show_alert=True)
        
    await db.assign_ticket(ticket_id, admin_id)
    
    # Update admin message with Close button
    user_data = await client.get_users(ticket.user_id)
    user_name = f"{user_data.first_name} {user_data.last_name or ''}".strip()
    
    close_markup = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.get("btn_close_ticket", lang="fr", skip_emojis=True), callback_data=f"close_ticket_{ticket_id}")]])
    await callback.message.edit_text(i18n.get("msg_support_started", lang="fr", name=user_name), reply_markup=close_markup)
    
    # Notify user
    user_db = await db.get_user(ticket.user_id, client.me.id)
    user_lang = user_db.language if user_db else "fr"
    admin_name = f"{callback.from_user.first_name}"
    
    notif_user = i18n.get("msg_support_taken", lang=user_lang, admin_name=admin_name)
    try:
        await client.send_message(ticket.user_id, notif_user, reply_markup=close_markup)
    except Exception: pass

@Client.on_callback_query(filters.regex(r"^close_ticket_(.*)$"))
async def close_ticket_callback(client: Client, callback: CallbackQuery):
    ticket_id = callback.matches[0].group(1)
    ticket = await db.get_ticket(ticket_id)
    if not ticket or ticket.status == "closed":
        return await callback.answer("Ticket déjà fermé.", show_alert=True)
    
    await db.close_ticket(ticket_id)
    
    # Update current message
    await callback.message.edit_text(i18n.get("msg_ticket_closed", lang="fr")) # Generic close msg
    
    # Notify both parties if they are different from callback initiator
    if callback.from_user.id == ticket.user_id:
        # User closed it, notify admin if active
        if ticket.admin_id:
            try:
                await client.send_message(ticket.admin_id, i18n.get("msg_ticket_closed_admin", lang="fr", ticket_id=ticket_id))
            except Exception: pass
    else:
        # Admin closed it, notify user
        user_db = await db.get_user(ticket.user_id, client.me.id)
        user_lang = user_db.language if user_db else "fr"
        try:
            await client.send_message(ticket.user_id, i18n.get("msg_ticket_closed", lang=user_lang))
        except Exception: pass

@Client.on_message(filters.command("close") & filters.private)
async def close_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    bot_id = client.me.id
    
    ticket_data = await db.db["support_tickets"].find_one({"user_id": user_id, "bot_id": bot_id, "status": {"$ne": "closed"}})
    from ..database.models import SupportTicket
    ticket = SupportTicket.from_dict(ticket_data) if ticket_data else None
    if not ticket:
        if message.reply_to_message:
            mapping = await db.get_support_message(user_id, message.reply_to_message.id)
            if mapping:
                ticket = await db.get_ticket(mapping.ticket_id)
    
    if ticket:
        await db.close_ticket(ticket.ticket_id)
        try:
            await client.send_message(ticket.user_id, i18n.get("msg_ticket_closed", lang="fr"))
            if ticket.admin_id:
                await client.send_message(ticket.admin_id, i18n.get("msg_ticket_closed_admin", lang="fr", ticket_id=ticket.ticket_id))
        except Exception: pass
    else:
        await message.reply_text("Aucun ticket actif trouvé.")

@Client.on_message(filters.private & ~filters.command(["start", "help", "admin", "close"]))
async def support_messaging_handler(client: Client, message: Message):
    user_id = message.from_user.id
    bot_id = client.me.id
    
    ticket_data = await db.db["support_tickets"].find_one({"user_id": user_id, "bot_id": bot_id, "status": "active"})
    from ..database.models import SupportTicket
    ticket = SupportTicket.from_dict(ticket_data) if ticket_data else None
    if ticket and ticket.admin_id and ticket.status == "active":
        try:
            fwd = await message.forward(ticket.admin_id)
            await db.add_support_message(ticket.admin_id, fwd.id, user_id, ticket.ticket_id)
            return
        except Exception as e:
            logger.error(f"Error forwarding user message to admin: {e}")
            return

    if message.reply_to_message:
        admin_id = message.from_user.id
        mapping = await db.get_support_message(admin_id, message.reply_to_message.id)
        if mapping:
            try:
                await message.copy(mapping.user_id)
                return
            except Exception as e:
                logger.error(f"Error replying to user from admin: {e}")
                return
