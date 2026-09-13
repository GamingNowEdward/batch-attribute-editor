"""Language persistence.

Uses Qt's :class:`QSettings` (native format: the Windows registry on this
platform, so **no extra configuration file** and no hard-coded path is
introduced). The backend can be injected, which keeps the logic testable
without touching the real user settings.

Failures are swallowed on purpose: a locked registry must never prevent the
tool from starting - the caller simply keeps the default language.
"""

from __future__ import annotations

from typing import Any, Optional

from i18n import DEFAULT_LANGUAGE
from ui.qt import QtCore

#: QSettings scope; Maya itself stores per-tool preferences the same way
SETTINGS_ORGANIZATION = "BatchAttributeEditor"
SETTINGS_APPLICATION = "BatchAttributeEditor"

#: Key that stores the language code (``en`` / ``zh_CN``)
LANGUAGE_KEY = "language"


class LanguageSettings:
    """Read/write the persisted UI language."""

    def __init__(self, settings: Optional[Any] = None) -> None:
        """*settings* is a QSettings-like object (a fake is allowed in tests)."""
        self._settings = settings

    # ------------------------------------------------------------ backend

    def _backend(self):
        if self._settings is None:
            self._settings = QtCore.QSettings(
                SETTINGS_ORGANIZATION, SETTINGS_APPLICATION
            )
        return self._settings

    # ------------------------------------------------------------ public API

    def load(self) -> str:
        """Persisted language, or the default when unset / unreadable."""
        try:
            value = self._backend().value(LANGUAGE_KEY, DEFAULT_LANGUAGE)
        except Exception:  # noqa: BLE001 - a broken store must not block startup
            return DEFAULT_LANGUAGE
        text = "" if value is None else str(value).strip()
        return text or DEFAULT_LANGUAGE

    def save(self, language: str) -> None:
        """Persist *language*; never raises."""
        try:
            backend = self._backend()
            backend.setValue(LANGUAGE_KEY, str(language))
            sync = getattr(backend, "sync", None)
            if callable(sync):
                sync()
        except Exception:  # noqa: BLE001 - persistence is best effort
            pass


__all__ = [
    "LANGUAGE_KEY",
    "SETTINGS_APPLICATION",
    "SETTINGS_ORGANIZATION",
    "LanguageSettings",
]
