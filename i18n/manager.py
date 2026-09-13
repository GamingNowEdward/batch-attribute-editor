"""Translation manager: the single source of truth for the active UI language.

Pure Python (no Qt / Maya dependency) so both the Core layer and the UI layer
can use it. The manager is intentionally small:

* a catalog per language (English is the reference language);
* :meth:`TranslationManager.translate` looks up the active language, then falls
  back to English, then returns the key itself - **a missing translation can
  never crash the tool**;
* ``{named}`` placeholders are filled with :meth:`str.format`; malformed
  templates fall back to the raw text instead of raising;
* :func:`plural` reuses the ``counts.<noun>.<one|other>`` catalog entries and
  keeps the historical English pluralisation as the last resort.

Switching the language calls the module-level :func:`set_language`, which the
UI turns into an immediate ``retranslate`` pass (no restart needed).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from i18n.en import TRANSLATIONS as _EN
from i18n.zh_cn import TRANSLATIONS as _ZH

#: Language used when no explicit choice exists (and the fallback language)
DEFAULT_LANGUAGE = "en"

#: Languages shipped with the tool
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("en", "zh_CN")

#: Accepted spellings -> canonical language code
_LANGUAGE_ALIASES = {
    "en": "en",
    "en_us": "en",
    "en_gb": "en",
    "zh": "zh_CN",
    "zh_cn": "zh_CN",
    "zh_hans": "zh_CN",
    "zh_sg": "zh_CN",
}


def normalize_language(language: Optional[str]) -> str:
    """Return the canonical code for *language* (unknown values fall back to English)."""
    if not language:
        return DEFAULT_LANGUAGE
    text = str(language).strip().lower().replace("-", "_")
    return _LANGUAGE_ALIASES.get(text, DEFAULT_LANGUAGE)


def _noun_key(noun: str) -> str:
    """Catalog key fragment for a pluralisable noun (``"root node"`` -> ``root_node``)."""
    return str(noun).strip().lower().replace(" ", "_")


class TranslationManager:
    """Catalog lookup with English fallback and safe formatting."""

    def __init__(self, language: str = DEFAULT_LANGUAGE,
                 catalogs: Optional[Dict[str, Dict[str, str]]] = None) -> None:
        self._catalogs: Dict[str, Dict[str, str]] = {
            "en": dict(_EN),
            "zh_CN": dict(_ZH),
        }
        if catalogs:
            for code, catalog in catalogs.items():
                self._catalogs[normalize_language(code)] = dict(catalog)
        self._language = normalize_language(language)

    # ------------------------------------------------------------ language

    @property
    def language(self) -> str:
        """The canonical code of the active language."""
        return self._language

    def set_language(self, language: str) -> bool:
        """Switch the active language; returns whether it actually changed.

        Unknown codes fall back to English, so even a corrupt persisted value
        cannot leave the tool without a usable language.
        """
        target = normalize_language(language)
        if target == self._language:
            return False
        self._language = target
        return True

    def catalog(self, language: Optional[str] = None) -> Dict[str, str]:
        """The catalog of *language* (the active one by default)."""
        code = normalize_language(language) if language else self._language
        return self._catalogs.get(code, {})

    # ------------------------------------------------------------ lookup

    def lookup(self, key: str, language: Optional[str] = None) -> Optional[str]:
        """Text for *key*: active language, then English, then None."""
        if language is None:
            text = self._catalogs.get(self._language, {}).get(key)
            if text is not None:
                return text
        else:
            text = self.catalog(language).get(key)
            if text is not None:
                return text
        return self._catalogs.get(DEFAULT_LANGUAGE, {}).get(key)

    def translate(self, key: str, **params) -> str:
        """Localised text for *key* with ``{named}`` placeholders filled in."""
        text = self.lookup(key)
        if text is None:
            return key
        if not params:
            return text
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            return text

    def plural(self, count: int, singular: str, plural_form: Optional[str] = None) -> str:
        """``<count> <noun>`` rendered with the active language's rules."""
        suffix = "one" if count == 1 else "other"
        text = self.lookup(f"counts.{_noun_key(singular)}.{suffix}")
        if text is not None:
            try:
                return text.format(count=count)
            except (KeyError, IndexError, ValueError):
                pass
        word = singular if count == 1 else (plural_form or f"{singular}s")
        return f"{count} {word}"

    # ------------------------------------------------------------ diagnostics

    def missing_keys(self, language: Optional[str] = None) -> set:
        """Reference keys absent from *language* (used by tests / checks)."""
        reference = self.catalog(DEFAULT_LANGUAGE)
        target = self.catalog(language)
        return {key for key in reference if key not in target}

    def extra_keys(self, language: Optional[str] = None) -> set:
        """Keys present in *language* but not in the English reference."""
        reference = self.catalog(DEFAULT_LANGUAGE)
        target = self.catalog(language)
        return {key for key in target if key not in reference}


#: Process-wide manager used by ``tr`` / ``plural`` / ``set_language``
_manager = TranslationManager()


def manager() -> TranslationManager:
    """The process-wide translation manager."""
    return _manager


def tr(key: str, **params) -> str:
    """Localised text for *key* in the active language."""
    return _manager.translate(key, **params)


def plural(count: int, singular: str, plural_form: Optional[str] = None) -> str:
    """Localised ``<count> <noun>`` (English fallback keeps the historical form)."""
    return _manager.plural(count, singular, plural_form)


def get_language() -> str:
    """Canonical code of the active language."""
    return _manager.language


def set_language(language: str) -> bool:
    """Switch the process-wide language; returns whether it changed."""
    return _manager.set_language(language)


__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "TranslationManager",
    "get_language",
    "manager",
    "normalize_language",
    "plural",
    "set_language",
    "tr",
]
