#!/usr/bin/env python3
"""
Internationalization service for multi-language support
Loads and manages translation files for Arabic and English
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Global translations storage
translations: Dict[str, Dict[str, str]] = {}

def load_translations():
    """Load translation files"""
    global translations
    
    translations_dir = Path("translations")
    
    try:
        # Load Arabic translations
        ar_file = translations_dir / "ar.json"
        if ar_file.exists():
            with open(ar_file, 'r', encoding='utf-8') as f:
                translations['ar'] = json.load(f)
        else:
            logger.warning("Arabic translations file not found")
            translations['ar'] = {}
        
        # Load English translations
        en_file = translations_dir / "en.json"
        if en_file.exists():
            with open(en_file, 'r', encoding='utf-8') as f:
                translations['en'] = json.load(f)
        else:
            logger.warning("English translations file not found")
            translations['en'] = {}
        
        logger.info(f"Loaded translations for {len(translations)} languages")
        
    except Exception as e:
        logger.error(f"Error loading translations: {e}")
        # Initialize with empty dictionaries to prevent crashes
        translations = {'ar': {}, 'en': {}}

def get_text(key: str, language: str = "ar", **kwargs) -> str:
    """Get translated text by key and language"""
    if not translations:
        load_translations()
    
    # Get translation for the language or fall back to Arabic
    lang_dict = translations.get(language, {})
    
    # Get the text or fall back to Arabic, then to the key itself
    text = lang_dict.get(key)
    if text is None and language != "ar":
        text = translations.get("ar", {}).get(key)
    if text is None:
        text = f"[{key}]"  # Fallback to show missing translation
    
    # Format with provided arguments
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError) as e:
        logger.warning(f"Error formatting text '{key}' for language '{language}': {e}")
        return text

def get_user_language(language_code: str = None) -> str:
    """Get user's language code with fallback"""
    if language_code and language_code in translations:
        return language_code
    return "ar"  # Default to Arabic

def get_available_languages() -> list:
    """Get list of available languages"""
    if not translations:
        load_translations()
    return list(translations.keys())

def is_rtl_language(language_code: str) -> bool:
    """Check if language is right-to-left"""
    rtl_languages = ['ar', 'he', 'fa', 'ur']
    return language_code in rtl_languages

# Load translations on module import
load_translations()
