import asyncio
import logging
from pyrogram import Client, enums
from ..config import config
from ..database.database import db
from .helpers import preload_peers, set_commands
from .scheduler import Scheduler

logger = logging.getLogger(__name__)

class CloneManager:
    def __init__(self):
        self.clones = {} # bot_id -> Client

    async def start_clone(self, bot_token: str, user_id: int):
        """Starts a new clone bot instance."""
        try:
            # Validate token and get bot info using a temporary client
            async with Client(
                "sessions/temp_clone",
                api_id=config.telegram.api_id,
                api_hash=config.telegram.api_hash,
                bot_token=bot_token,
                in_memory=True
            ) as temp_client:
                me = await temp_client.get_me()
            
            bot_id = me.id
            username = me.username

            if bot_id in self.clones:
                logger.info(f"Clone @{username} is already running.")
                return me

            # Initialize real client
            client = Client(
                f"sessions/clone_{bot_id}",
                api_id=config.telegram.api_id,
                api_hash=config.telegram.api_hash,
                bot_token=bot_token,
                plugins={"root": "bot.plugins"},
                parse_mode=enums.ParseMode.HTML,
                max_concurrent_transmissions=config.telegram.max_concurrent_transmissions
            )
            
            # Monkeypatch the client to identify it as a clone
            client.is_clone = True
            client.clone_owner_id = user_id
            
            await client.start()
            self.clones[bot_id] = client
            
            # Start background tasks for the clone
            await preload_peers(client, bot_id)
            await set_commands(client)
            scheduler = Scheduler(client)
            await scheduler.start()
            client.scheduler = scheduler # Store it if needed to stop later
            
            logger.info(f"Started clone bot @{username} (Owner: {user_id})")
            return me
            
        except Exception as e:
            logger.error(f"Error starting clone with token {bot_token[:10]}...: {e}")
            raise e

    async def start_all(self):
        """Starts all active clones from the database in parallel."""
        active_clones = await db.get_active_clones()
        logger.info(f"Found {len(active_clones)} active clones to start.")
        
        tasks = []
        for clone in active_clones:
            tasks.append(self.start_clone(clone.bot_token, clone.user_id))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    clone = active_clones[i]
                    logger.error(f"Failed to auto-start clone @{clone.username}: {res}")

    async def stop_all(self):
        """Stops all running clone bot instances in parallel."""
        if not self.clones:
            return
            
        tasks = []
        bot_ids = list(self.clones.keys())
        for bot_id in bot_ids:
            tasks.append(self.stop_clone(bot_id))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        self.clones.clear()
        logger.info("Stopped all clone bot instances.")

    async def stop_clone(self, bot_id: int):
        """Stops a specific clone bot instance."""
        if bot_id in self.clones:
            client = self.clones.pop(bot_id)
            if hasattr(client, "scheduler"):
                client.scheduler.stop()
            await client.stop()
            logger.info(f"Stopped clone bot ID {bot_id}")
            return True
        return False

clone_manager = CloneManager()
