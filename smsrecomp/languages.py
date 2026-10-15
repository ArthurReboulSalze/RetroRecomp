"""Stable language IDs shared by converter preferences and generated games."""
LANGUAGES = ('en', 'fr', 'it', 'es', 'de', 'zh', 'ja', 'ru')
LANGUAGE_NAMES = ('English', 'Français', 'Italiano', 'Español', 'Deutsch', '中文（简体）', '日本語', 'Русский')


def language_code(value):
    code = str(value or '').replace('_', '-').lower().split('-')[0]
    return code if code in LANGUAGES else 'en'


def language_name(value):
    return LANGUAGE_NAMES[LANGUAGES.index(language_code(value))]
