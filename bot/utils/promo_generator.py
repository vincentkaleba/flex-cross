import logging
from typing import List, Dict, Any
from bot.database.models import Channel, AppSettings, PaidPromo, AdType, Adscross
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.utils.i18n import i18n

logger = logging.getLogger(__name__)

class PromoGenerator:
    """
    Utility class to generate promotional messages.
    Supports two formats:
    - Button: A grid of inline buttons linking to participating channels.
    - Folder: A message promoting a Telegram Folder link.
    """

    @staticmethod
    def generate_promo(
        bot_username: str,
        ad: Adscross,
        channels: List[Channel], 
        settings: AppSettings, 
        paid_promos: List[PaidPromo] = None,
        is_clone: bool = False
    ) -> Dict[str, Any]:
        """
        Generates the promotional message text and markup.
        Returns a dictionary containing 'text' and 'reply_markup'.
        """
        if paid_promos is None:
            paid_promos = []
        
        # Filter paid promos based on targeting
        paid_promos = PromoGenerator._filter_paid_promos(paid_promos, channels, is_clone)


        # Sort and filter channels
        sorted_channels = PromoGenerator._filter_and_sort_channels(channels, settings)

        if ad.ad_type == AdType.FOLDER:
            return PromoGenerator._generate_folder_format(ad, sorted_channels, settings, paid_promos, is_clone)
        elif ad.ad_type == AdType.TEXT:
            return PromoGenerator._generate_text_format(ad, sorted_channels, settings, paid_promos, is_clone)
        else:
            return PromoGenerator._generate_button_format(bot_username, ad, sorted_channels, settings, paid_promos, is_clone)

    @staticmethod
    def _filter_paid_promos(paid_promos: List[PaidPromo], channels: List[Channel], is_clone: bool = False) -> List[PaidPromo]:
        """Filters promos that match batch categories/languages, or are global."""
        if not paid_promos: return []
        batch_cats = set(getattr(ch, "category", "other") for ch in channels)
        batch_langs = set(getattr(ch, "language", "fr") for ch in channels)
        
        if is_clone:
            # For clones, we want to allow all global sponsors (from main bot) but maybe sort them
            # so that matching ones come first.
            matching = [p for p in paid_promos if (not p.categories or any(c in batch_cats for c in p.categories)) 
                        and (not p.languages or any(l in batch_langs for l in p.languages))]
            others = [p for p in paid_promos if p not in matching]
            return matching + others

        return [p for p in paid_promos if (not p.categories or any(c in batch_cats for c in p.categories)) 
                and (not p.languages or any(l in batch_langs for l in p.languages))]

    @staticmethod
    def _generate_text_format(ad: Adscross, channels: List[Channel], settings: AppSettings, paid_promos: List[PaidPromo], is_clone: bool = False) -> Dict[str, Any]:
        content = ad.content
        full_text = ""
        if settings.message_header:
            full_text += f"{i18n.replace_emojis(settings.message_header)}\n\n"
        
        # Group channels by category
        from collections import defaultdict
        groups = defaultdict(list)
        for ch in channels:
            cat = getattr(ch, "category", "other")
            if not cat: cat = "other"
            groups[cat].append(ch)
            
        channel_list_str = ""
        lang = "fr"
        
        for cat, chs in groups.items():
            cat_name = i18n.get(f"cat_{cat}", lang=lang, skip_emojis=True)
            if not cat_name or cat_name.startswith("cat_"):
                cat_name = cat.capitalize()
            
            channel_list_str += f"\n📁 <b>{cat_name}</b> :\n"
            for ch in chs:
                title = getattr(ch, "title", "Canal")
                link = getattr(ch, "link", "")
                if link:
                    prefix = settings.button_prefix or "•"
                    channel_list_str += f"{prefix} <a href='{link}'>{title}</a>\n"
                    
        if "{channels}" in content:
            full_text += i18n.replace_emojis(content.replace("{channels}", channel_list_str.strip()))
        else:
            full_text += i18n.replace_emojis(content) + "\n\n" + channel_list_str.strip()

        # Keyboard generation
        keyboard = []
        if ad.reply_markup:
            for row in ad.reply_markup.get("inline_keyboard", []):
                keyboard.append([InlineKeyboardButton(text=b.get("text"), url=b.get("url"), callback_data=b.get("callback_data")) for b in row])

        if paid_promos:
            if is_clone:
                row = []
                for promo in paid_promos[:2]:
                    row.append(InlineKeyboardButton(text=f"⭐ {promo.text}", url=promo.url))
                if row: keyboard.append(row)
            else:
                for promo in paid_promos:
                    keyboard.append([InlineKeyboardButton(text=f"⭐ {promo.text}", url=promo.url)])

        markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        if settings.message_footer:
            full_text += f"\n\n{i18n.replace_emojis(settings.message_footer)}"

        return {
            "text": full_text.strip(),
            "reply_markup": markup
        }

    @staticmethod
    def _filter_and_sort_channels(channels: List[Channel], settings: AppSettings = None) -> List[Channel]:
        """
        Sort channels by members count descending.
        """
        # Sort by members count descending
        return sorted(channels, key=lambda c: getattr(c, "members_count", 0), reverse=True)

    @staticmethod
    def _generate_button_format(bot_username: str, ad: Adscross, channels: List[Channel], settings: AppSettings, paid_promos: List[PaidPromo], is_clone: bool = False) -> Dict[str, Any]:
        content = ad.content
        full_text = ""
        if settings.message_header:
            full_text += f"{i18n.replace_emojis(settings.message_header)}\n\n"
        full_text += i18n.replace_emojis(content)
        if settings.message_footer:
            full_text += f"\n\n{i18n.replace_emojis(settings.message_footer)}"
        
        prefix = settings.button_prefix or ""
        max_rows = getattr(settings, "max_rows", 10)
        max_columns = getattr(settings, "max_columns", 5)
        max_buttons = getattr(settings, "max_buttons", 50)

        buttons = []
        for ch in channels[:max_buttons]:
            title = getattr(ch, "title", "Canal")
            link = getattr(ch, "link", "")
            if link:
                buttons.append(InlineKeyboardButton(f"{prefix} {title} {prefix}".strip(), url=link))
        
        keyboard_rows = []
        
        # 1. Add original buttons from ad
        if ad.reply_markup:
            for row in ad.reply_markup.get("inline_keyboard", []):
                keyboard_rows.append([InlineKeyboardButton(text=b.get("text"), url=b.get("url"), callback_data=b.get("callback_data")) for b in row])

        current_row = []
        rows_count = 0
        
        paid_idx = 0
        
        for btn in buttons:
            current_row.append(btn)
            if len(current_row) >= max_columns:
                keyboard_rows.append(current_row)
                current_row = []
                rows_count += 1
                
                if rows_count % max_rows == 0:
                    sep_text = "⭐ Sponsor ⭐"
                    sep_url = f"https://t.me/{bot_username}" if bot_username else "https://t.me/bott"
                    
                    if paid_promos and paid_idx < len(paid_promos):
                        sep_text = f"⭐ {paid_promos[paid_idx].text}"
                        sep_url = paid_promos[paid_idx].url
                        paid_idx += 1
                        
                    sep_btn = InlineKeyboardButton(sep_text, url=sep_url)
                    keyboard_rows.append([sep_btn])
                    
        if current_row:
            keyboard_rows.append(current_row)

        # Inject remaining paid promos as inline buttons at the bottom if any
        if paid_promos and paid_idx < len(paid_promos):
            for promo in paid_promos[paid_idx:]:
                keyboard_rows.append([InlineKeyboardButton(text=f"⭐ {promo.text}", url=promo.url)])

        reply_markup = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None

        return {
            "text": full_text.strip(),
            "reply_markup": reply_markup
        }

    @staticmethod
    def _generate_folder_format(ad: Adscross, channels: List[Channel], settings: AppSettings, paid_promos: List[PaidPromo], is_clone: bool = False) -> Dict[str, Any]:
        content = ad.content
        folder_link = ad.folder_link
        full_text = ""
        if settings.message_header:
            full_text += f"{i18n.replace_emojis(settings.message_header)}\n\n"
        
        if not folder_link and content:
            import re
            m = re.search(r'(https?://t\.me/\S+)', content)
            if m:
                folder_link = m.group(1).split('"')[0].split('<')[0] # Clean up HTML tags if any

        if not folder_link:
            folder_link = settings.folder_link
            
        if folder_link:
            full_text += f"📂 <b>Rejoignez notre dossier complet de chaînes !</b>\n\n"
        else:
            full_text += "⚠️ <b>Lien du dossier non défini.</b>\n\n"
            
        full_text += i18n.replace_emojis(content)

        lang = "fr" # Default to FR for generation
        
        # Keyboard generation
        keyboard = []
        if ad.reply_markup:
            for row in ad.reply_markup.get("inline_keyboard", []):
                keyboard.append([InlineKeyboardButton(text=b.get("text"), url=b.get("url"), callback_data=b.get("callback_data")) for b in row])

        if folder_link:
            btn_label = i18n.get("btn_join_folder", lang=lang, skip_emojis=True)
            keyboard.append([InlineKeyboardButton(text=btn_label, url=folder_link)])

        if paid_promos:
            if is_clone:
                row = []
                for promo in paid_promos[:2]:
                    row.append(InlineKeyboardButton(text=f"⭐ {promo.text}", url=promo.url))
                if row: keyboard.append(row)
            else:
                for promo in paid_promos:
                    keyboard.append([InlineKeyboardButton(text=f"⭐ {promo.text}", url=promo.url)])
        
        markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        if settings.message_footer:
            full_text += f"\n\n{i18n.replace_emojis(settings.message_footer)}"

        return {
            "text": full_text.strip(),
            "reply_markup": markup
        }
