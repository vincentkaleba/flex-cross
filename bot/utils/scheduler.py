import asyncio
import logging
import pendulum
from ..database.database import db
from ..database.models import Post, Adscross, Channel, PaidPromo
from .promo_generator import PromoGenerator
from .i18n import i18n
from .helpers import preload_peers, send_promo_to_channel, get_next_pub_time, handle_channel_failure
from pyrogram import Client, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..config import config

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self, client: Client):
        self.client = client
        self.is_running = False
        self.last_stat_date_run = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        logger.info("Starting Background Scheduler...")
        # Run loop in background
        asyncio.create_task(self._loop())
        logger.info("Background Scheduler started successfully")

    def stop(self):
        self.is_running = False
        logger.info("Background Scheduler stopped")

    async def _loop(self):
        while self.is_running:
            try:
                await self._check_tasks()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            
            # Wait for the next minute (approximately)
            await asyncio.sleep(60)

    async def _check_tasks(self):
        bot_id = self.client.me.id
        settings = await db.get_settings(bot_id)
        # Default to UTC if not set
        tz = settings.fuseau_horaire or "UTC"
        try:
            now = pendulum.now(tz)
        except Exception:
            now = pendulum.now("UTC")
            tz = "UTC"
        
        # 1. Handle Auto-Deletion
        if settings.auto_delete_ads:
            now_utc = pendulum.now("UTC")
            await self._handle_auto_delete(bot_id, settings.delete_after_minutes, now_utc)
        
        # 2. Handle Scheduled Promotions
        await self._handle_scheduled_ads(bot_id, now)
        
        # 3. Record Daily Channel Stats
        await self._record_daily_stats(bot_id, now)

    async def _record_daily_stats(self, bot_id: int, now: pendulum.DateTime):
        current_date = now.format("YYYY-MM-DD")
        if self.last_stat_date_run == current_date:
            return
            
        self.last_stat_date_run = current_date
        logger.info(f"Taking daily snapshot of channel statistics for bot {bot_id} on {current_date}...")
        
        cursor = db.channels.find({"status": "active", "bot_id": bot_id})
        async for ch in cursor:
            chat_id = ch["channel_id"]
            promo_link = ch.get("promo_link", "")
            
            try:
                total_members = await self.client.get_chat_members_count(chat_id)
            except Exception:
                continue
                
            bot_joins = 0
            if promo_link:
                try:
                    invite_obj = await self.client.get_chat_invite_link(chat_id, promo_link)
                    bot_joins = invite_obj.member_count or 0
                except Exception:
                    pass
            
            stat_entry = {
                "date": current_date,
                "total": total_members,
                "bot_joins": bot_joins
            }
            
            await db.channels.update_one(
                {"_id": ch["_id"], "bot_id": bot_id},
                {"$push": {"history": stat_entry},
                 "$set": {"members_count": total_members}}
            )
            
        # Global stats snapshot
        users_count = await db.users.count_documents({"bot_id": bot_id})
        channels_count = await db.channels.count_documents({"bot_id": bot_id})
        ads_count = await db.adscross.count_documents({"bot_id": bot_id})
        posts_count = await db.posts.count_documents({"bot_id": bot_id})
        
        await db.db["stats_history"].update_one(
            {"date": current_date, "bot_id": bot_id},
            {"$set": {
                "date": current_date,
                "bot_id": bot_id,
                "total_users": users_count,
                "total_channels": channels_count,
                "total_ads": ads_count,
                "total_posts": posts_count
            }},
            upsert=True
        )

    async def _handle_auto_delete(self, bot_id: int, minutes: int, now_utc: pendulum.DateTime):
        active_posts = await db.get_active_posts(bot_id)
        affected_ads = set()
        for post in active_posts:
            sent_at = pendulum.instance(post.sent_at)
            if sent_at.tzinfo is None:
                sent_at = sent_at.set(tz="UTC")
            
            # Compare UTC to UTC
            diff_min = now_utc.diff(sent_at).in_minutes()
            
            if diff_min >= minutes:
                try:
                    await self.client.delete_messages(post.channel_id, post.message_id)
                    logger.info(f"Auto-deleted message {post.message_id} (Age: {diff_min}m) in channel {post.channel_id}")
                except Exception as e:
                    logger.warning(f"Could not delete message {post.message_id} in {post.channel_id}: {e}")
                    # If message was already deleted, it's a failure (owner cheated)
                    from pyrogram.errors import MessageIdInvalid, MessageNotModified
                    if isinstance(e, (MessageIdInvalid, MessageNotModified)):
                        await handle_channel_failure(self.client, post.channel_id)
                
                await db.mark_post_deleted(post.ad_id, post.channel_id, post.message_id, bot_id)
                affected_ads.add(post.ad_id)
                
        # Update reports for ads that had deletions
        for ad_id in affected_ads:
            try:
                await self._update_broadcast_report(ad_id, bot_id)
            except Exception as e:
                logger.error(f"Error updating report for ad {ad_id}: {e}")

    async def _update_broadcast_report(self, ad_id: str, bot_id: int):
        """Edits the existing report message with updated stats after deletion."""
        ad_doc = await db.adscross.find_one({"_id": ad_id, "bot_id": bot_id})
        if not ad_doc:
            from bson import ObjectId
            try: ad_doc = await db.adscross.find_one({"_id": ObjectId(ad_id), "bot_id": bot_id})
            except: return
            
        if not ad_doc or not ad_doc.get("report_message_id"):
            return
            
        ad = Adscross.from_dict(ad_doc)
        chat_id = ad.report_chat_id
        msg_id = ad.report_message_id
        
        # Get count of successful posts (both active and deleted) for this ad
        # Actually, let's just use the current stats from the DB
        posts_cursor = db.posts.find({"ad_id": ad_id, "bot_id": bot_id})
        success = await db.posts.count_documents({"ad_id": ad_id, "bot_id": bot_id})
        failed = 0 # We don't track failures in the DB yet, so 0 or use a fixed one
        
        settings = await db.get_settings(bot_id)
        tz = settings.fuseau_horaire or "UTC"
        
        # User language for the report
        user = await db.get_user(chat_id, bot_id)
        lang = user.language if user else "fr"
        
        next_pub = get_next_pub_time(ad.schedule_times, ad.schedule_days, tz)
        
        # After deletion, "Scheduled Deletion" is effectively "Done"
        # We can just say "N/A" or "Terminée"
        delete_status = "N/A" if lang == "en" else "Terminée ✅"
        
        report_text = i18n.get("msg_broadcast_report", lang=lang, success=success, failed=failed, delete_time=delete_status, next_time=next_pub)
        
        buttons = [
            [InlineKeyboardButton(i18n.get("btn_resend", lang=lang, skip_emojis=True), callback_data=f"sel_send_{ad.ad_id}")],
            [InlineKeyboardButton(i18n.get("btn_delete_posts", lang=lang, skip_emojis=True), callback_data=f"del_brd_{ad.ad_id}")],
            [InlineKeyboardButton(i18n.get("btn_cancel_broadcast", lang=lang, skip_emojis=True), callback_data="start")]
        ]
        
        try:
            await self.client.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=report_text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.warning(f"Failed to edit report message {msg_id}: {e}")

    async def _handle_scheduled_ads(self, bot_id: int, now: pendulum.DateTime):
        current_time_str = now.format("HH:mm")
        # Pendulum: 0 (Monday) to 6 (Sunday). JSON might use same or different.
        current_day = now.day_of_week
        
        scheduled_ads = await db.get_scheduled_ads(bot_id)
        for ad in scheduled_ads:
            if current_time_str in ad.schedule_times and current_day in ad.schedule_days:
                # Avoid double-send if just sent manually
                if ad.last_sent_at:
                    last_sent = pendulum.instance(ad.last_sent_at)
                    if now.diff(last_sent).in_minutes() < 1:
                        continue
                
                logger.info(f"Executing scheduled ad: {ad.ad_id}")
                await self._execute_promo(bot_id, ad)

    async def _execute_promo(self, bot_id: int, ad: Adscross):
        """Logic to send the promotion to all target channels using PromoGenerator."""
        from datetime import datetime
        await db.adscross.update_one({"_id": ad.ad_id, "bot_id": bot_id}, {"$set": {"last_sent_at": datetime.now()}})
        
        settings = await db.get_settings(bot_id)
        
        # Determine parse mode
        parse_mode = None
        if settings.parse_mode == "html":
            parse_mode = enums.ParseMode.HTML
        elif settings.parse_mode == "markdown":
            parse_mode = enums.ParseMode.MARKDOWN
            
        # 1. Fetch all active channels as Channel objects
        cursor = db.channels.find({"is_active": True, "bot_id": bot_id}) 
        all_channels = [Channel.from_dict(doc) async for doc in cursor]
        
        # 2. Fetch all active Paid Promos (Sharing global ones bot_id=main_bot_id)
        cursor_paid = db.db.paid_promos.find({"is_active": True, "$or": [{"bot_id": bot_id}, {"bot_id": config.telegram.main_bot_id}]})
        paid_promos = [PaidPromo.from_dict(doc) async for doc in cursor_paid]
        
        bot_username = self.client.me.username if self.client.me else None
        
        all_channels_dict = {ch.channel_id: ch for ch in all_channels}
        target_ch_objects = all_channels
        
        chunk_size = settings.max_buttons if settings.max_buttons > 0 else 50
        chunks = [target_ch_objects[i:i + chunk_size] for i in range(0, len(target_ch_objects), chunk_size)]
        
        success = 0
        failed = 0
        
        for chunk in chunks:
            # Generate content and markup for THIS specific chunk
            promo_data = PromoGenerator.generate_promo(
                bot_username=bot_username,
                ad=ad,
                channels=target_ch_objects,
                settings=settings,
                paid_promos=paid_promos,
                is_clone=getattr(self.client, "is_clone", False)
            )

            full_text = promo_data["text"]
            reply_markup = promo_data["reply_markup"]

            # Send this specific mega to ONLY the channels in this chunk
            for ch in chunk:
                try:
                    msg = await send_promo_to_channel(
                        client=self.client,
                        chat_id=ch.channel_id,
                        text=full_text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                        ad=ad
                    )
                    
                    # Success: Reset failures
                    await db.reset_channel_failures(ch.channel_id, bot_id)
                    
                    # Register post for auto-deletion
                    post = Post(ad_id=str(ad.ad_id), channel_id=ch.channel_id, message_id=msg.id, bot_id=bot_id)
                    await db.add_post(post)
                    success += 1
                    logger.info(f"Promo {ad.ad_id} sent to channel {ch.channel_id}")
                except Exception as e:
                    logger.error(f"Failed to send promo to {ch.channel_id}: {e}")
                    failed += 1
                    # Report failure and potentially ban
                    await handle_channel_failure(self.client, ch.channel_id, bot_id)

        # 3. Notify Admins
        try:
            # Fetch all admins
            cursor_admins = db.users.find({"is_admin": True, "bot_id": bot_id})
            admin_ids = [doc.get("user_id") async for doc in cursor_admins]
            if config.telegram.owner_id not in admin_ids:
                admin_ids.append(config.telegram.owner_id)
                
            tz = settings.fuseau_horaire or "UTC"
            next_pub = get_next_pub_time(ad.schedule_times, ad.schedule_days, tz)
            delete_time = pendulum.now(tz).add(minutes=settings.delete_after_minutes).format("HH:mm") if settings.auto_delete_ads else "N/A"
            
            for admin_id in admin_ids:
                user = await db.get_user(admin_id, bot_id)
                lang = user.language if user else "fr"
                
                # Report Buttons
                buttons = [
                    [InlineKeyboardButton(i18n.get("btn_resend", lang=lang, skip_emojis=True), callback_data=f"sel_send_{ad.ad_id}")],
                    [InlineKeyboardButton(i18n.get("btn_delete_posts", lang=lang, skip_emojis=True), callback_data=f"del_brd_{ad.ad_id}")],
                    [InlineKeyboardButton(i18n.get("btn_cancel_broadcast", lang=lang, skip_emojis=True), callback_data="start")]
                ]
                
                report_title = "🚨 <b>NOTIFICATION PROGRAMMÉE</b>\n\n" if lang == "fr" else "🚨 <b>SCHEDULED NOTIFICATION</b>\n\n"
                report_text = report_title + i18n.get("msg_broadcast_report", lang=lang, success=success, failed=failed, delete_time=delete_time, next_time=next_pub)
                
                try:
                    await self.client.send_message(admin_id, report_text, reply_markup=InlineKeyboardMarkup(buttons))
                except: pass
        except Exception as e:
            logger.error(f"Error notifying admins after scheduled promo: {e}")
