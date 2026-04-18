import asyncio
import logging
from pyrogram import Client, filters, enums
from ..database.database import db
from ..utils.media_manager import download_channel_photo
from ..config import config

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("sync"))
async def sync_channels_command(client: Client, message):
    """
    Admin command to synchronize all channels with Telegram (fetch about/photo).
    Also syncs sponsor (paid_promos) photos.
    """
    from ..utils.helpers import is_admin_or_owner
    bot_id = client.me.id
    user = await db.get_user(message.from_user.id, bot_id)
    if not is_admin_or_owner(client, message.from_user.id, user):
        return
    
    status_msg = await message.reply_text("🔄 Début de la synchronisation des canaux...")
    
    channels_cursor = db.channels.find({"bot_id": client.me.id})
    total = await db.channels.count_documents({"bot_id": client.me.id})
    updated = 0
    errors = 0
    
    async for chan_doc in channels_cursor:
        channel_id = chan_doc.get("channel_id")
        try:
            chat = await client.get_chat(channel_id)
            about = getattr(chat, "description", "") or ""
            photo_filename = await download_channel_photo(client, chat)
            
            await db.channels.update_one(
                {"channel_id": channel_id, "bot_id": client.me.id},
                {"$set": {"about": about, "photo": photo_filename}}
            )
            updated += 1
            if updated % 5 == 0:
                await status_msg.edit_text(f"🔄 Synchronisation en cours... ({updated}/{total})")
                
        except Exception as e:
            logger.error(f"Error syncing channel {channel_id}: {e}")
            errors += 1
            
        await asyncio.sleep(1) # Avoid flood limits

    # --- Sync sponsor (paid_promos) photos ---
    await status_msg.edit_text(f"✅ Canaux synchronisés ({updated}/{total})\n\n🔄 Synchronisation des sponsors...")
    sponsor_updated = 0
    sponsor_errors = 0

    sponsor_cursor = db.paid_promos.find({})
    async for promo in sponsor_cursor:
        promo_url = promo.get("url", "")
        promo_username = None
        if "t.me/" in promo_url:
            parts = promo_url.rstrip("/").split("t.me/")
            if len(parts) > 1 and not parts[1].startswith("+"):
                promo_username = parts[1].split("/")[0].lstrip("@")

        if not promo_username:
            continue

        try:
            chat = await client.get_chat(f"@{promo_username}")
            photo_filename = await download_channel_photo(client, chat)
            members = 0
            try:
                members = await client.get_chat_members_count(chat.id)
            except Exception:
                pass

            await db.paid_promos.update_one(
                {"promo_id": promo.get("promo_id")},
                {"$set": {"photo": photo_filename, "members_count": members}}
            )
            sponsor_updated += 1
        except Exception as e:
            logger.error(f"Error syncing sponsor @{promo_username}: {e}")
            sponsor_errors += 1

        await asyncio.sleep(1)

    await status_msg.edit_text(
        f"✅ Synchronisation complète !\n\n"
        f"📡 Canaux : {updated} mis à jour, {errors} erreurs\n"
        f"⭐ Sponsors : {sponsor_updated} mis à jour, {sponsor_errors} erreurs"
    )


async def sync_sponsor_photos_background(client: Client):
    """
    Background task: quietly fetch missing sponsor photos on bot startup.
    Only fetches photos that are not yet stored (photo field absent or empty).
    """
    await asyncio.sleep(10)  # Let the bot fully start first
    logger.info("Starting background sync of sponsor photos...")
    sponsor_cursor = db.paid_promos.find({"$or": [{"photo": {"$exists": False}}, {"photo": ""}]})
    async for promo in sponsor_cursor:
        promo_url = promo.get("url", "")
        promo_username = None
        if "t.me/" in promo_url:
            parts = promo_url.rstrip("/").split("t.me/")
            if len(parts) > 1 and not parts[1].startswith("+"):
                promo_username = parts[1].split("/")[0].lstrip("@")

        if not promo_username:
            continue

        try:
            chat = await client.get_chat(f"@{promo_username}")
            photo_filename = await download_channel_photo(client, chat)
            members = 0
            try:
                members = await client.get_chat_members_count(chat.id)
            except Exception:
                pass

            await db.paid_promos.update_one(
                {"promo_id": promo.get("promo_id")},
                {"$set": {"photo": photo_filename, "members_count": members}}
            )
            logger.info(f"Synced sponsor photo for @{promo_username}")
        except Exception as e:
            logger.warning(f"Could not sync sponsor photo for @{promo_username}: {e}")

        await asyncio.sleep(2)

    logger.info("Background sponsor photo sync complete.")
