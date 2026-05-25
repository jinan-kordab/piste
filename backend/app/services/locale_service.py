# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Locale Service — Multilingual Verdict Labels & Search Region Configuration
===========================================================================
Provides locale-aware mappings for:
  - Verdict labels in the user's language
  - Search engine region parameters for locale-biased results
  - PolitiFact-aligned label translations

[C2] Multilingual as a cross-cutting architectural concern.
"""

from typing import Dict

# Locale → verdict label translations (PolitiFact 7-way)
VERDICT_LABELS_I18N: Dict[str, Dict[str, str]] = {
    "en": {
        "TRUE": "TRUE",
        "MOSTLY_TRUE": "MOSTLY TRUE",
        "HALF_TRUE": "HALF TRUE",
        "MOSTLY_FALSE": "MOSTLY FALSE",
        "FALSE": "FALSE",
        "PANTS_ON_FIRE": "PANTS ON FIRE",
        "UNVERIFIABLE": "UNVERIFIABLE",
    },
    "fr": {
        "TRUE": "VRAI",
        "MOSTLY_TRUE": "PLUTÔT VRAI",
        "HALF_TRUE": "MI-VRAI",
        "MOSTLY_FALSE": "PLUTÔT FAUX",
        "FALSE": "FAUX",
        "PANTS_ON_FIRE": "FAUX ABSOLU",
        "UNVERIFIABLE": "INVÉRIFIABLE",
    },
}

# Locale → search engine region configuration
# BOTH locales target CANADA (gl=ca, cr=countryCA):
#   fr → Quebec French-language sources
#   en → Canadian federal English-language sources
# US region removed — platform is Canada-only.
LOCALE_SEARCH_REGIONS: Dict[str, dict] = {
    "en": {
        "gl": "ca",         # Google region: CANADA
        "hl": "en",         # Interface language: English
        "lr": "lang_en",    # Search results language: English
        "cr": "countryCA",  # Country restriction: CANADA
        "desc": "Canada — Federal Elections (English)",
        "note": "English searches target Canadian federal sources: CBC News, Globe and Mail, Toronto Star, CTV News, Global News, National Post, Maclean's, The Canadian Press.",
    },
    "fr": {
        "gl": "ca",         # Google region: CANADA
        "hl": "fr",         # Interface language: French
        "lr": "lang_fr",    # Search results language: French
        "cr": "countryCA",  # Country restriction: CANADA
        "desc": "Canada / Québec — Élections provinciales (Français)",
        "note": "French searches target Quebec sources: Radio-Canada, La Presse, Le Devoir, TVA Nouvelles, Journal de Montréal, Journal de Québec, L'Actualité.",
    },
}

# Default locale
DEFAULT_LOCALE = "en"

# Supported locales — Canada-only: English + French
SUPPORTED_LOCALES = ["en", "fr"]


def get_verdict_label(verdict_key: str, locale: str = DEFAULT_LOCALE) -> str:
    """
    Get the localized verdict label for a given locale.

    Args:
        verdict_key: Internal verdict key (e.g., "MOSTLY_TRUE")
        locale: Language code (en, fr, es)

    Returns:
        Localized label string, falling back to English if not found.
    """
    locale_safe = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    labels = VERDICT_LABELS_I18N.get(locale_safe, VERDICT_LABELS_I18N[DEFAULT_LOCALE])
    return labels.get(verdict_key, verdict_key)


def get_search_region_params(locale: str = DEFAULT_LOCALE) -> dict:
    """
    Get search engine region parameters for locale-biased results.

    Used by BlindRetriever to configure provider-specific
    region parameters so French queries return French-language sources.
    """
    locale_safe = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    return LOCALE_SEARCH_REGIONS.get(locale_safe, LOCALE_SEARCH_REGIONS[DEFAULT_LOCALE])


def get_supported_locales() -> list[str]:
    """List all supported locale codes."""
    return SUPPORTED_LOCALES


def localize_verdict_distribution(
    distribution: Dict[str, float], locale: str = DEFAULT_LOCALE
) -> Dict[str, float]:
    """
    Convert a verdict distribution to use localized labels.

    Args:
        distribution: {"TRUE": 0.6, "MOSTLY_TRUE": 0.3, ...}
        locale: Target language code

    Returns:
        Distribution with localized label keys.
    """
    localized = {}
    for key, value in distribution.items():
        localized_label = get_verdict_label(key, locale)
        localized[localized_label] = value
    return localized
