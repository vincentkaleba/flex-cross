from ..config import config
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..database.models import AppSettings
from .i18n import i18n

class Menu:
    def format_number(self, n):
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:.1f}B".replace(".0", "")
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M".replace(".0", "")
        if n >= 1_000:
            return f"{n/1_000:.1f}K".replace(".0", "")
        return str(n)

    def btn_row(self, label_key, value, callback_prefix, lang, unit=""):
        label = i18n.get(label_key, lang=lang, skip_emojis=True)
        if isinstance(value, bool):
            val_str = "✅" if value else "❌"
        else:
            val_str = self.format_number(value) if isinstance(value, int) and value > 999 else str(value)
            if unit: val_str += f" {unit}"
        
        return InlineKeyboardButton(f"{label} {val_str}", callback_data=callback_prefix)

    def get_menu(self, menu_type: str, lang: str = "fr", **kwargs) -> InlineKeyboardMarkup:
        buttons = []
        
        if menu_type == "start":
            bot_username = kwargs.get("bot_username", "AdsBot")
            import urllib.parse
            share_text = urllib.parse.quote(i18n.get('share_text', lang=lang, skip_emojis=True, promo_name=f"@{bot_username}"))
            share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}&text={share_text}"
            
            is_clone = kwargs.get("is_clone", False)
            buttons = [
                [InlineKeyboardButton(i18n.get("btn_add_channel", lang=lang, skip_emojis=True), callback_data="add_channel")],
                [InlineKeyboardButton(i18n.get("btn_my_channel", lang=lang, skip_emojis=True), callback_data="my_channels")]
            ]
            
            if not is_clone:
                buttons.append([InlineKeyboardButton(i18n.get("btn_create_clone", lang=lang, skip_emojis=True), callback_data="create_clone")])
            else:
                # On a clone, redirect to main bot
                main_bot = config.telegram.main_bot_username or "FlexAds_robot" # Fallback if not set
                buttons.append([InlineKeyboardButton(i18n.get("btn_create_clone", lang=lang, skip_emojis=True), url=f"https://t.me/{main_bot}")])

            if kwargs.get("has_clones", False) and not is_clone:
                buttons.append([InlineKeyboardButton(i18n.get("btn_manage_my_clones", lang=lang, skip_emojis=True), callback_data="manage_my_clones")])
            
            buttons.append([
                InlineKeyboardButton(i18n.get("btn_share", lang=lang, skip_emojis=True), url=share_url),
                InlineKeyboardButton(i18n.get("btn_help", lang=lang, skip_emojis=True), callback_data="help")
            ])
            buttons.append([
                InlineKeyboardButton(i18n.get("btn_guide", lang=lang, skip_emojis=True), callback_data="guide"),
                InlineKeyboardButton(i18n.get("btn_language", lang=lang, skip_emojis=True), callback_data="change_lang")
            ])
            
        elif menu_type == "language":
            buttons = [
                [InlineKeyboardButton("🇫🇷 Français", callback_data="set_lang_fr"),
                 InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
                [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")]
            ]
            
        elif menu_type == "user_my_channels":
            channels = kwargs.get("channels", [])
            page = kwargs.get("page", 0)
            total_pages = kwargs.get("total_pages", 1)
            
            buttons = []
            for ch in channels:
                title = ch.get("title", "Canal Sans Nom")
                buttons.append([InlineKeyboardButton(f"📢 {title}", callback_data=f"uchannel_{ch['channel_id']}")])
            
            nav_row = []
            if page > 0:
                nav_row.append(InlineKeyboardButton("◀️", callback_data=f"my_channels_{page-1}"))
            if total_pages > 1:
                nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("▶️", callback_data=f"my_channels_{page+1}"))
                
            if nav_row:
                buttons.append(nav_row)
                
            buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")])
            
        elif menu_type == "user_channel_info":
            channel_id = kwargs.get("channel_id")
            buttons = [
                [InlineKeyboardButton(i18n.get("user_btn_edit", lang=lang, skip_emojis=True), callback_data=f"uedit_{channel_id}")],
                [InlineKeyboardButton(i18n.get("user_btn_stats", lang=lang, skip_emojis=True), callback_data=f"ustat_{channel_id}_7")],
                [InlineKeyboardButton(i18n.get("user_btn_remove", lang=lang, skip_emojis=True), callback_data=f"udel_{channel_id}")],
                [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="my_channels_0")]
            ]
            
        elif menu_type == "user_stats_ranges":
            channel_id = kwargs.get("channel_id")
            buttons = [
                [InlineKeyboardButton(i18n.get("btn_7_days", lang=lang, skip_emojis=True), callback_data=f"ustat_{channel_id}_7"),
                 InlineKeyboardButton(i18n.get("btn_30_days", lang=lang, skip_emojis=True), callback_data=f"ustat_{channel_id}_30")],
                [InlineKeyboardButton(i18n.get("btn_all_time_graph", lang=lang, skip_emojis=True), callback_data=f"ustat_{channel_id}_0")],
                [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data=f"uchannel_{channel_id}")]
            ]
            
        elif menu_type == "user_confirm_remove":
            channel_id = kwargs.get("channel_id")
            buttons = [
                [InlineKeyboardButton(i18n.get("user_btn_confirm_remove", lang=lang, skip_emojis=True, default="Oui, Retirer"), callback_data=f"uconfirm_{channel_id}")],
                [InlineKeyboardButton(i18n.get("btn_cancel", lang=lang, skip_emojis=True), callback_data=f"uchannel_{channel_id}")]
            ]
        
        elif menu_type == "admin":
            is_clone = kwargs.get("is_clone", False)
            buttons = [
                [InlineKeyboardButton(i18n.get("admin_manage_users", lang=lang, skip_emojis=True), callback_data="manage_users")],
                [InlineKeyboardButton(i18n.get("admin_ban", lang=lang, skip_emojis=True), callback_data="ban_channel"),
                 InlineKeyboardButton(i18n.get("admin_unban", lang=lang, skip_emojis=True), callback_data="unban_channel")],
                [InlineKeyboardButton(i18n.get("admin_show_channel", lang=lang, skip_emojis=True), callback_data="channel_info"),
                 InlineKeyboardButton(i18n.get("admin_list", lang=lang, skip_emojis=True), callback_data="manage_list")],
                [InlineKeyboardButton(i18n.get("admin_create_post", lang=lang, skip_emojis=True), callback_data="create_post"),
                 InlineKeyboardButton(i18n.get("admin_preview", lang=lang, skip_emojis=True), callback_data="preview_promo")],
                [InlineKeyboardButton(i18n.get("admin_settings", lang=lang, skip_emojis=True), callback_data="settings"),
                 InlineKeyboardButton(i18n.get("btn_language", lang=lang, skip_emojis=True), callback_data="change_lang")],
                [InlineKeyboardButton(i18n.get("admin_send_promo", lang=lang, skip_emojis=True), callback_data="send_promo"),
                 InlineKeyboardButton(i18n.get("admin_delete_promotion", lang=lang, skip_emojis=True), callback_data="delete_promo")],
            ]
            
            if not is_clone:
                buttons.append([
                    InlineKeyboardButton(i18n.get("admin_send_paid_promo", lang=lang, skip_emojis=True), callback_data="send_paid_promo"),
                    InlineKeyboardButton(i18n.get("admin_delete_paid_promo", lang=lang, skip_emojis=True), callback_data="delete_paid_promo")
                ])
                buttons.append([InlineKeyboardButton(i18n.get("btn_manage_all_clones", lang=lang, skip_emojis=True), callback_data="manage_all_clones")])
            else:
                # On a clone, show redirect to main bot for admin too
                main_bot = config.telegram.main_bot_username or "FlexAds_robot"
                buttons.append([InlineKeyboardButton(i18n.get("btn_create_clone", lang=lang, skip_emojis=True), url=f"https://t.me/{main_bot}")])
                
            buttons.append([InlineKeyboardButton(i18n.get("btn_continue_as_user", lang=lang, skip_emojis=True), callback_data="user_mode")])
            
        elif menu_type == "manage_users":
            buttons = [
                [InlineKeyboardButton(i18n.get("admin_add_admin", lang=lang, skip_emojis=True), callback_data="add_admin"),
                 InlineKeyboardButton(i18n.get("admin_revoke_admin", lang=lang, skip_emojis=True), callback_data="revoke_admin")],
                [InlineKeyboardButton(i18n.get("admin_ban_user", lang=lang, skip_emojis=True), callback_data="ban_user"),
                 InlineKeyboardButton(i18n.get("admin_unban_user", lang=lang, skip_emojis=True), callback_data="unban_user")],
                [InlineKeyboardButton(i18n.get("admin_list_admins", lang=lang, skip_emojis=True), callback_data="list_admins"),
                 InlineKeyboardButton(i18n.get("admin_list_users", lang=lang, skip_emojis=True), callback_data="list_users")],
                [InlineKeyboardButton(i18n.get("admin_update_subs", lang=lang, skip_emojis=True), callback_data="update_subs"),
                 InlineKeyboardButton(i18n.get("admin_stats_btn", lang=lang, skip_emojis=True), callback_data="stats")],
                [InlineKeyboardButton(i18n.get("admin_mail", lang=lang, skip_emojis=True), callback_data="broadcast"),
                 InlineKeyboardButton(i18n.get("admin_announce", lang=lang, skip_emojis=True), callback_data="announce")],
                [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")]
            ]
            
        elif menu_type == "broadcast_targets":
            buttons = [
                [InlineKeyboardButton(i18n.get("admin_bc_all", lang=lang, skip_emojis=True), callback_data="bc_all"),
                 InlineKeyboardButton(i18n.get("admin_bc_active", lang=lang, skip_emojis=True), callback_data="bc_active")],
                [InlineKeyboardButton(i18n.get("admin_bc_admins", lang=lang, skip_emojis=True), callback_data="bc_admins"),
                 InlineKeyboardButton(i18n.get("admin_bc_channels", lang=lang, skip_emojis=True), callback_data="bc_channels")],
                [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="manage_users")]
            ]
            
        elif menu_type == "categories":
            channel_id = kwargs.get("channel_id")
            is_admin = kwargs.get("is_admin", True)
            prefix = "set_cat_" if is_admin else "uset_cat_"
            cat_keys = ["crypto", "humor", "news", "gaming", "movies", "series", "anime", "business", "music", "sport", "tech", "art", "food", "fashion", "books", "other"]
            buttons = []
            for i in range(0, len(cat_keys), 2):
                row = []
                key1 = cat_keys[i]
                row.append(InlineKeyboardButton(i18n.get(f"cat_{key1}", lang=lang, skip_emojis=True), callback_data=f"{prefix}{key1}_{channel_id}"))
                if i+1 < len(cat_keys):
                    key2 = cat_keys[i+1]
                    row.append(InlineKeyboardButton(i18n.get(f"cat_{key2}", lang=lang, skip_emojis=True), callback_data=f"{prefix}{key2}_{channel_id}"))
                buttons.append(row)
            
            back_data = "cancel_setting" if is_admin else f"uedit_{channel_id}"
            buttons.append([InlineKeyboardButton(i18n.get("btn_cancel", lang=lang, skip_emojis=True), callback_data=back_data)])
            
        elif menu_type == "settings":
            settings: AppSettings = kwargs.get("settings")
            if not settings:
                return None
                
            # Full width rows for long text
            btn_header = f"{i18n.get('btn_set_header', lang=lang, skip_emojis=True)} {'✅' if settings.message_header else '❌'}"
            buttons.append([InlineKeyboardButton(btn_header, callback_data="set_header")])
            
            btn_footer = f"{i18n.get('btn_set_footer', lang=lang, skip_emojis=True)} {'✅' if settings.message_footer else '❌'}"
            buttons.append([InlineKeyboardButton(btn_footer, callback_data="set_footer")])
            
            # Format and Zone
            format_val = i18n.get(f"format_{settings.parse_mode}", lang=lang, skip_emojis=True)
            btn_format = f"{i18n.get('btn_set_format', lang=lang, skip_emojis=True)} {format_val}"
            buttons.append([
                InlineKeyboardButton(btn_format, callback_data="set_format"),
                self.btn_row("btn_set_tz", settings.fuseau_horaire, "set_tz", lang)
            ])
            
            # Members Min/Max
            buttons.append([
                self.btn_row("btn_minimum_member", settings.min_members, "set_min_mem", lang),
                self.btn_row("btn_maxi_member", settings.max_members, "set_max_mem", lang)
            ])
            
            # Auto delete
            buttons.append([
                self.btn_row("btn_auto_delete", settings.auto_delete_ads, "set_auto_del", lang)
            ])
            
            # Delete after and Schedule
            sched_preview = ", ".join(settings._schedule[:2]) + ("..." if len(settings._schedule) > 2 else "") if hasattr(settings, "_schedule") and settings._schedule else i18n.get("msg_none", lang=lang)
            btn_schedule = f"{i18n.get('btn_set_schedule', lang=lang, skip_emojis=True)} {sched_preview}"
            buttons.append([
                self.btn_row("btn_delete_after", settings.delete_after_minutes, "set_del_after", lang, "min"),
                InlineKeyboardButton(btn_schedule, callback_data="set_schedule")
            ])
            
            # UI Limits
            buttons.append([
                self.btn_row("btn_cross_prefixd", settings.button_prefix, "set_prefix", lang),
                self.btn_row("btn_max_pir_cross", settings.max_buttons, "set_max_btns", lang)
            ])
            
            buttons.append([
                self.btn_row("btn_max_pir_line", settings.max_columns, "set_max_line", lang), # Aligned to max_columns
                self.btn_row("btn_max_row", settings.max_rows, "set_max_row", lang)
            ])
            
            buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data="start")])
            
        elif menu_type == "user_edit_options":
            channel_id = kwargs.get("channel_id")
            buttons = [
                [InlineKeyboardButton(i18n.get("user_btn_change_category", lang=lang, skip_emojis=True), callback_data=f"ucat_{channel_id}")],
                [InlineKeyboardButton(i18n.get("user_btn_change_language", lang=lang, skip_emojis=True), callback_data=f"ulang_{channel_id}")],
                [InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data=f"uchannel_{channel_id}")]
            ]
            
        elif menu_type == "manage_clones":
            import math
            clones = kwargs.get("clones", [])
            is_admin_mode = kwargs.get("is_admin_mode", False)
            page = kwargs.get("page", 0)
            
            limit = 10
            total_clones = len(clones)
            total_pages = math.ceil(total_clones / limit) if total_clones > 0 else 1
            
            start_idx = page * limit
            end_idx = start_idx + limit
            clones_page = clones[start_idx:end_idx]
            
            buttons = []
            for clone in clones_page:
                buttons.append([InlineKeyboardButton(f"@{clone.username}", callback_data=f"clone_info_{clone.bot_id}_{'adm' if is_admin_mode else 'usr'}")])
            
            nav_row = []
            if page > 0:
                nav_row.append(InlineKeyboardButton("◀️", callback_data=f"manage_{'all' if is_admin_mode else 'my'}_clones_{page-1}"))
            if total_pages > 1:
                nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("▶️", callback_data=f"manage_{'all' if is_admin_mode else 'my'}_clones_{page+1}"))
                
            if nav_row:
                buttons.append(nav_row)
            
            back_data = "start"
            buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data=back_data)])
            
        elif menu_type == "clone_details":
            bot_id = kwargs.get("bot_id")
            is_admin_mode = kwargs.get("is_admin_mode", False)
            from ..utils.clone_manager import clone_manager
            is_running = bot_id in clone_manager.clones
            
            if is_running:
                buttons.append([InlineKeyboardButton(i18n.get("btn_stop_clone", lang=lang, skip_emojis=True), callback_data=f"stop_clone_{bot_id}_{'adm' if is_admin_mode else 'usr'}")])
            else:
                buttons.append([InlineKeyboardButton("▶️ Redémarrer", callback_data=f"start_clone_{bot_id}_{'adm' if is_admin_mode else 'usr'}")])
                
            buttons.append([InlineKeyboardButton(i18n.get("btn_delete_clone", lang=lang, skip_emojis=True), callback_data=f"delete_clone_{bot_id}_{'adm' if is_admin_mode else 'usr'}")])
            
            back_data = "manage_all_clones" if is_admin_mode else "manage_my_clones"
            buttons.append([InlineKeyboardButton(i18n.get("btn_back", lang=lang, skip_emojis=True), callback_data=back_data)])


        return InlineKeyboardMarkup(buttons)