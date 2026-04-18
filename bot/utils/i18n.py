import json
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class i18nManager:
    """Centralized manager for multi-language strings."""
    
    def __init__(self, resources_path: Optional[str] = None, default_lang: str = "fr"):
        if resources_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.resources_path = os.path.join(base_dir, "resources", "strings")
            self.emojis_path = os.path.join(base_dir, "resources", "emojis.json")
        else:
            self.resources_path = resources_path
            self.emojis_path = os.path.join(os.path.dirname(resources_path), "emojis.json")
            
        self.default_lang = default_lang
        self._strings: Dict[str, Dict[str, str]] = {}
        self._emojis: Dict[str, str] = {}
        self._load_all_languages()
        self._load_emojis()

    def _load_all_languages(self) -> None:
        """Loads all JSON files from the resources directory."""
        if not os.path.exists(self.resources_path):
            os.makedirs(self.resources_path, exist_ok=True)
            return

        for filename in os.listdir(self.resources_path):
            if filename.endswith(".json"):
                lang_code = filename[:-5]
                file_path = os.path.join(self.resources_path, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self._strings[lang_code] = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"Error loading translation file {filename}: {e}")

    def _load_emojis(self) -> None:
        """Loads the emoji mapping from emojis.json."""
        if not os.path.exists(self.emojis_path):
            return

        try:
            with open(self.emojis_path, "r", encoding="utf-8") as f:
                self._emojis = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error loading emoji mapping: {e}")

    def replace_emojis(self, text: str) -> str:
        """Replaces standard emojis with their premium equivalents using placeholders to avoid collisions."""
        if not self._emojis:
            return text
            
        try:
            sorted_emojis = sorted(self._emojis.items(), key=lambda x: len(x[0]), reverse=True)
            
            placeholders = {}
            temp_text = text
            
            for i, (emoji, premium_html) in enumerate(sorted_emojis):
                if emoji in temp_text:
                    placeholder = f"__EMOJI_{i}__"
                    placeholders[placeholder] = premium_html
                    temp_text = temp_text.replace(emoji, placeholder)
            
            for placeholder, premium_html in placeholders.items():
                temp_text = temp_text.replace(placeholder, premium_html)
            
            if "<emoji" in temp_text or "<tg-emoji" in temp_text:
                logger.debug(f"Generated text with custom emojis: {temp_text}")
            return temp_text
        except Exception as e:
            logger.error(f"Error in replace_emojis: {e}")
            return text

    def get(self, key: str, lang: Optional[str] = None, skip_emojis: bool = False, **kwargs: Any) -> str:
        """
        Retrieves a string by key and language.
        
        Args:
            key: The translation key.
            lang: The target language code (e.g., 'en', 'fr').
            skip_emojis: If True, standard emojis won't be replaced with premium ones.
            **kwargs: Placeholders to format the string.
            
        Returns:
            The translated and formatted string.
        """
        lang = lang or self.default_lang
        
        lang_strings = self._strings.get(lang) or self._strings.get(self.default_lang) or {}
        
        text = lang_strings.get(key)
        
        if text is None:
            if lang != self.default_lang:
                text = self._strings.get(self.default_lang, {}).get(key)
            
            if text is None:
                return f"{{missing_string: {key}}}"
        
        try:
            if not skip_emojis:
                text = self.replace_emojis(text)
            return text.format(**kwargs)
        except KeyError as e:
            return f"{{missing_placeholder: {str(e)} in {key}}}"
        except Exception:
            return text

# Global instance
i18n = i18nManager()
