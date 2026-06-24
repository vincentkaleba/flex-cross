import os
import logging
from pyrogram import Client
from ..config import config

logger = logging.getLogger(__name__)

MEDIA_DIR = "/var/www/flex-hub/media"

async def download_channel_photo(client: Client, chat):
    """
    Downloads the small profile photo of a channel and returns the local filename.
    """
    if not chat.photo:
        return ""
    
    if not os.path.exists(MEDIA_DIR):
        try:
            os.makedirs(MEDIA_DIR, exist_ok=True)
        except Exception as e:
            logger.error(f"Error creating media directory: {e}")
            return ""

    # Use chat.id for a stable and unique filename
    filename = f"chat_{chat.id}.jpg"
    filepath = os.path.join(MEDIA_DIR, filename)
    
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            logger.error(f"Error removing old channel photo: {e}")
        
    try:
        await client.download_media(chat.photo.small_file_id, file_name=filepath)
        # Fix permissions for the new file
        os.chmod(filepath, 0o755)
        return filename
    except Exception as e:
        logger.error(f"Error downloading channel photo: {e}")
        return ""

def get_photo_url(filename):
    if not filename:
        return ""
    return f"https://hub.98-82-201-161.sslip.io/media/{filename}"
