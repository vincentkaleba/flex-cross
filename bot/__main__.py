import logging
import asyncio
import sys
from .utils.clone_manager import clone_manager
import dns.resolver
from aiohttp import web
from . import app, hub_app
from .config import config
from pyrogram import idle
from .route import web_server
from .utils.i18n import i18n

logger = logging.getLogger(__name__)

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8"]  # Google DNS


async def run_bot():
    print("------------------------------------------------------")
   
    logger.info("Starting bot...")
    await app.start()
    
    if hub_app:
        await hub_app.start()
        hub_me = await hub_app.get_me()
        logger.info(f"Hub Bot started as @{hub_me.username} ({hub_me.id})")

    me = await app.get_me()
    config.telegram.main_bot_username = me.username
    logger.info(f"Main Bot started as @{me.username} ({me.id})")
    print(f"====== Bot started as @{app.me.username} ({app.me.id}) ======")
    
    from .utils.helpers import preload_peers, get_system_info, get_uptime, set_commands
    import time
    from datetime import datetime
    
    start_time = time.time()
    await preload_peers(app, app.me.id)
    await set_commands(app)

    from .utils.scheduler import Scheduler
    scheduler = Scheduler(app)
    await scheduler.start()

    try:
        if config.telegram.log_channel_id:
            # The channel is now preloaded in preload_peers
            await app.send_message(
                config.telegram.log_channel_id,
                i18n.get(
                    "start_logmsg", 
                    lang="fr", 
                    username=me.mention,
                    date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    uptime=get_uptime(start_time),
                    system=get_system_info()
                ),
            )

        if config.telegram.owner_id:
            try:
                await app.get_chat(config.telegram.owner_id)
                # await app.send_message(
                #     config.telegram.owner_id,
                #     i18n.get("start_logmsg", lang="fr", username=me.mention),
                # )
                print("-----------------------------------")
                print(f"send message to owner {config.telegram.owner_id} and log channel {config.telegram.log_channel_id}")
                print("-----------------------------------")
            except Exception as e:
                logger.error(
                    f"Note: Could not send start message to owner (ID invalid or bot not member): {e}"
                )
                print("-----------------------------------")
                print(f"Could not send start message to owner {config.telegram.owner_id} and log channel {config.telegram.log_channel_id}")
                print("-----------------------------------")
    except Exception as e:
        logger.error(
            f"Note: Could not send start message to log channel/owner (ID invalid or bot not member): {e}"
        )
        print("-----------------------------------")
        print(f"Could not send start message to owner {config.telegram.owner_id} and log channel {config.telegram.log_channel_id}")
        print("-----------------------------------")
    runner = None
    if config.application.webhook:
        runner = web.AppRunner(await web_server())
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", 8080).start()
        logger.info("Health check server started on port 8080")

    # Start all active clones
    await clone_manager.start_all()

    # Start background sync for sponsor photos safely
    from .plugins.admin_sync import sync_sponsor_photos_background
    loop = asyncio.get_event_loop()
    loop.create_task(sync_sponsor_photos_background(app))

    await idle()
    
    # Cleanup
    if runner:
        await runner.cleanup()
        
    await clone_manager.stop_all()
    if hub_app:
        await hub_app.stop()
    await app.stop()


if __name__ == "__main__":
    try:
        app.run(run_bot())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}")
