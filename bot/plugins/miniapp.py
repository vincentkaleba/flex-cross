from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from ..database.database import db
from ..config import config
from .. import app, hub_app

@Client.on_message(filters.command(["hub", "start"]) & filters.private, group=1)
async def hub_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check if the handler is being called by the Hub Bot
    is_hub_bot = hub_app and client.me.id == hub_app.me.id
    
    if message.text.startswith("/start") and not is_hub_bot:
        return
    
    if is_hub_bot:
        # Check if user is registered with the MAIN bot
        # We use app.me.id for the main bot's ID in the database
        main_bot_user = await db.get_user(user_id, app.me.id)
        
        if not main_bot_user:
            # User not registered, redirect to main bot
            main_bot_link = f"https://t.me/{config.telegram.main_bot_username}?start=hub"
            text = (
                "<b>⚠️ Accès Restreint</b>\n\n"
                "Pour utiliser le Flex Hub, vous devez d'abord vous enregistrer auprès de notre bot principal.\n\n"
                "Veuillez cliquer sur le bouton ci-dessous, démarrer le bot, puis revenir ici."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 S'enregistrer maintenant", url=main_bot_link)],
                [InlineKeyboardButton("🔄 J'ai fini, réessayer", callback_data="check_reg")]
            ])
            return await message.reply_text(text, reply_markup=keyboard)

    # If user is registered (or it's the main bot calling), show the hub
    hub_url = "https://hub.167.233.223.42.nip.io"
    
    text = (
        "<b>🚀 Flex Cross Hub - Professional</b>\n\n"
        "Bienvenue sur la plateforme numéro 1 pour découvrir les meilleurs canaux Telegram.\n\n"
        "✅ Accès autorisé\n"
        "📈 Statistiques en temps réel\n"
        "📂 Classement par catégories"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Ouvrir le Hub", web_app=WebAppInfo(url=hub_url))],
        [InlineKeyboardButton("📢 Support @FlexCross", url="https://t.me/FlexCrossBot")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("check_reg"))
async def check_reg_handler(client: Client, query):
    user_id = query.from_user.id
    main_bot_user = await db.get_user(user_id, app.me.id)
    
    if main_bot_user:
        await query.message.delete()
        # Call the hub handler again
        await hub_handler(client, query.message)
    else:
        await query.answer("❌ Vous n'êtes pas encore enregistré. Veuillez d'abord démarrer le bot principal.", show_alert=True)
