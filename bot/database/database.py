from motor.motor_asyncio import AsyncIOMotorClient
from ..config import config
from .models import User, Channel, Adscross, Post, AppSettings, CloneBot
from typing import Optional, List

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(config.database.uri)
        self.db = self.client[config.database.database_name]
        self.users = self.db["users"]
        self.channels = self.db["channels"]
        self.adscross = self.db["adscross"]
        self.posts = self.db["posts"]
        self.settings = self.db["settings"]
        self.paid_promos = self.db["paid_promos"]

    # User operations
    async def get_user(self, user_id: int, bot_id: int = 0) -> Optional[User]:
        data = await self.users.find_one({"user_id": user_id, "bot_id": bot_id})
        return User.from_dict(data) if data else None

    async def add_user(self, user: User):
        await self.users.update_one(
            {"user_id": user.user_id, "bot_id": user.bot_id},
            {"$set": user.to_dict()},
            upsert=True
        )

    # Channel operations
    async def get_channel(self, channel_id: int, bot_id: int = 0) -> Optional[Channel]:
        data = await self.channels.find_one({"channel_id": channel_id, "bot_id": bot_id})
        return Channel.from_dict(data) if data else None

    async def add_channel(self, channel: Channel):
        if await self.check_channel(channel.channel_id):
            return
        count = await self.user_channels_count(channel.owner_id)
        if count >= config.users.max_channels:
            return False
        await self.channels.update_one(
            {"channel_id": channel.channel_id, "bot_id": channel.bot_id},
            {"$set": channel.to_dict()},
            upsert=True
        )
        return True

    async def get_owner_channels(self, owner_id: int, bot_id: int = 0) -> List[Channel]:
        cursor = self.channels.find({"owner_id": owner_id, "bot_id": bot_id})
        return [Channel.from_dict(doc) async for doc in cursor]
    
    async def check_channel(self, channel_id: int, bot_id: int = 0) -> bool:
        channel = await self.get_channel(channel_id, bot_id)
        if channel:
            return True
        return False
    
    async def user_channels_count(self, owner_id: int, bot_id: int = 0) -> int:
        return await self.channels.count_documents({"owner_id": owner_id, "bot_id": bot_id})

    async def report_channel_failure(self, channel_id: int, bot_id: int = 0):
        await self.channels.update_one(
            {"channel_id": channel_id, "bot_id": bot_id},
            {"$inc": {"failure_count": 1}}
        )
        return await self.get_channel(channel_id, bot_id)

    async def reset_channel_failures(self, channel_id: int, bot_id: int = 0):
        await self.channels.update_one(
            {"channel_id": channel_id, "bot_id": bot_id},
            {"$set": {"failure_count": 0}}
        )

    async def ban_channel(self, channel_id: int, bot_id: int = 0):
        await self.channels.update_one(
            {"channel_id": channel_id, "bot_id": bot_id},
            {"$set": {"is_active": False, "is_banned": True}}
        )

    async def unban_channel(self, channel_id: int, bot_id: int = 0):
        await self.channels.update_one(
            {"channel_id": channel_id, "bot_id": bot_id},
            {"$set": {"is_banned": False, "is_active": True, "failure_count": 0}}
        )

    async def get_all_active_channels(self, bot_id: int = 0) -> List[Channel]:
        cursor = self.channels.find({"is_active": True, "is_banned": {"$ne": True}, "bot_id": bot_id})
        return [Channel.from_dict(doc) async for doc in cursor]

    # Post operations
    async def add_post(self, post: Post):
        await self.posts.insert_one(post.to_dict())

    async def get_ad_posts(self, ad_id: str, bot_id: int = 0) -> List[Post]:
        cursor = self.posts.find({"ad_id": ad_id, "bot_id": bot_id})
        return [Post.from_dict(doc) async for doc in cursor]

    async def get_active_posts(self, bot_id: int = 0) -> List[Post]:
        cursor = self.posts.find({"status": "active", "bot_id": bot_id})
        return [Post.from_dict(doc) async for doc in cursor]

    async def mark_post_deleted(self, ad_id: str, channel_id: int, message_id: int, bot_id: int = 0):
        await self.posts.update_one(
            {"ad_id": ad_id, "channel_id": channel_id, "message_id": message_id, "bot_id": bot_id},
            {"$set": {"status": "deleted"}}
        )

    # Adscross operations
    async def create_ad(self, ad: Adscross) -> str:
        result = await self.adscross.insert_one(ad.to_dict())
        return str(result.inserted_id)

    async def get_ad(self, ad_id: str, bot_id: int = 0) -> Optional[Adscross]:
        from bson import ObjectId
        try:
            data = await self.adscross.find_one({"_id": ObjectId(ad_id), "bot_id": bot_id})
            return Adscross.from_dict(data) if data else None
        except Exception:
            return None

    async def get_scheduled_ads(self, bot_id: int = 0) -> List[Adscross]:
        cursor = self.adscross.find({"is_scheduled": True, "status": "active", "bot_id": bot_id})
        # We handle the time matching in Python for simplicity with timezone
        return [Adscross.from_dict(doc) async for doc in cursor]

    # Settings operations
    async def get_settings(self, bot_id: int = 0) -> AppSettings:
        # We use a string ID for settings to avoid confusion, namespaced by bot_id
        settings_id = f"settings_{bot_id}"
        data = await self.settings.find_one({"_id": settings_id})
        if not data:
            settings = AppSettings(bot_id=bot_id)
            await self.save_settings(settings)
            return settings
        return AppSettings.from_dict(data)

    async def save_settings(self, settings: AppSettings):
        settings_id = f"settings_{settings.bot_id}"
        data = settings.to_dict()
        await self.settings.update_one(
            {"_id": settings_id},
            {"$set": data},
            upsert=True
        )

    # Support operations
    async def create_ticket(self, user_id: int) -> str:
        from .models import SupportTicket
        ticket = SupportTicket(user_id=user_id)
        result = await self.db["support_tickets"].insert_one(ticket.to_dict())
        return str(result.inserted_id)

    async def get_active_ticket(self, user_id: int, bot_id: int = 0) -> Optional["SupportTicket"]:
        from .models import SupportTicket
        data = await self.db["support_tickets"].find_one({"user_id": user_id, "bot_id": bot_id, "status": {"$ne": "closed"}})
        return SupportTicket.from_dict(data) if data else None

    async def get_ticket(self, ticket_id: str) -> Optional["SupportTicket"]:
        from .models import SupportTicket
        from bson import ObjectId
        try:
            data = await self.db["support_tickets"].find_one({"_id": ObjectId(ticket_id)})
            return SupportTicket.from_dict(data) if data else None
        except: return None

    async def assign_ticket(self, ticket_id: str, admin_id: int):
        from bson import ObjectId
        await self.db["support_tickets"].update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": {"admin_id": admin_id, "status": "active"}}
        )

    async def close_ticket(self, ticket_id: str):
        from bson import ObjectId
        await self.db["support_tickets"].update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": {"status": "closed"}}
        )

    async def add_support_message(self, admin_id: int, admin_message_id: int, user_id: int, ticket_id: str):
        from .models import SupportMessage
        mapping = SupportMessage(admin_id, admin_message_id, user_id, ticket_id)
        await self.db["support_messages"].insert_one(mapping.to_dict())

    async def get_support_message(self, admin_id: int, admin_message_id: int) -> Optional["SupportMessage"]:
        from .models import SupportMessage
        data = await self.db["support_messages"].find_one({"admin_id": admin_id, "admin_message_id": admin_message_id})
        return SupportMessage.from_dict(data) if data else None

    async def get_admins(self, bot_id: int = 0) -> List[User]:
        cursor = self.users.find({"is_admin": True, "bot_id": bot_id})
        admins = [User.from_dict(doc) async for doc in cursor]
        # Always include global owner
        owner = await self.get_user(config.telegram.owner_id, bot_id)
        if owner and not any(a.user_id == owner.user_id for a in admins):
            admins.append(owner)
        
        # If it's a clone, also include its creator
        clone_data = await self.db["clones"].find_one({"bot_id": bot_id})
        if clone_data:
            clone_owner_id = clone_data.get("user_id")
            if clone_owner_id:
                clone_owner = await self.get_user(clone_owner_id, bot_id)
                if clone_owner and not any(a.user_id == clone_owner.user_id for a in admins):
                    admins.append(clone_owner)

        return admins

    # Clone operations
    async def add_clone(self, clone: CloneBot):
        await self.db["clones"].update_one(
            {"bot_id": clone.bot_id},
            {"$set": clone.to_dict()},
            upsert=True
        )

    async def get_clones(self, user_id: Optional[int] = None) -> List[CloneBot]:
        query = {"user_id": user_id} if user_id else {}
        cursor = self.db["clones"].find(query)
        return [CloneBot.from_dict(doc) async for doc in cursor]
    
    async def get_active_clones(self) -> List[CloneBot]:
        cursor = self.db["clones"].find({"is_active": True})
        return [CloneBot.from_dict(doc) async for doc in cursor]

    async def remove_clone(self, bot_id: int):
        await self.db["clones"].delete_one({"bot_id": bot_id})

db = Database()
