import pyromod
from pyrogram import Client, filters, enums
import sys
import os
import logging
from .config import config


# Configure logging early
logging.basicConfig(
    level=config.application.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Initialize Main Client
app = Client(
    f"sessions/{config.telegram.session_name}",
    api_id=config.telegram.api_id,
    api_hash=config.telegram.api_hash,
    bot_token=config.telegram.bot_token,
    plugins={"root":"bot.plugins"},
    parse_mode=enums.ParseMode.HTML,
    max_concurrent_transmissions=config.telegram.max_concurrent_transmissions
)

# Initialize Hub Client
hub_app = Client(
    f"sessions/{config.telegram.hub_session_name}",
    api_id=config.telegram.api_id,
    api_hash=config.telegram.api_hash,
    bot_token=config.telegram.hub_bot_token,
    plugins={"root":"bot.plugins"},
    parse_mode=enums.ParseMode.HTML,
    max_concurrent_transmissions=config.telegram.max_concurrent_transmissions
) if config.telegram.hub_bot_token else None