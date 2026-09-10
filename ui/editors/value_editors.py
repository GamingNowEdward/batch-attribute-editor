"""Editors generated per attribute type.

* :class:`ScalarValueEditor` - a single channel (Float / Integer / Boolean / String / Enum / unit)
* :class:`VectorValueEditor` - multi-channel values (Float3 / Double3 / Compound / Multi elements)
* :class:`ColorValueEditor` - Color3: R/G/B number inputs + colour picker

All three build on :class:`~ui.editors.base.ValueEditor`,
so reading values, validation and signal logic exist in only one implementation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.types import ChannelSpec
from ui.editors.base import ChannelKey, ValueEditor
from ui.qt import QtWidgets
from ui.styles import BORDER


class ScalarValueEditor(ValueEditor):
    """Single-channel editor."""

    def validation_error(self) -> str:
        problems = self.invalid_channels()
        return problems[0] if problems else ""


class VectorValueEditor(ValueEditor):
    """Multi-channel value editor (X/Y/Z, compound children, array elements).

    Each channel has its own check box, so "change one component but write all of them
    identically" cannot happen by accident.
    """

    def __init__(self, definition, channels, samples=None, parent=None) -> None:
        super().__init__(definition, channels, samples, parent)
        if not channels:
            hint = QtWidgets.QLabel("This attribute has no editable channels")
            hint.setObjectName("hintLabel")
            self._body.addWidget(hint)


class ColorValueEditor(ValueEditor):
    """Color3 editor: R/G/B numbers + colour picker.

    If the underlying Maya attribute allows values beyond 0-1 (HDR colours, for example),
    the input range here is **not** restricted, in line with requirement section 11.
    """

    def __init__(self, definition, channels, samples=None, parent=None) -> None:
        super().__init__(definition, channels, samples, parent)
        self._build_picker()
        self.changed.connect(self._update_swatch)
        self._update_swatch()

    def _build_picker(self) -> None:
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(6)

        self._swatch = QtWidgets.QLabel(self)
        self._swatch.setFixedSize(42, 18)
        self._swatch.setToolTip("Current color preview")
        row.addWidget(self._swatch)

        picker = QtWidgets.QPushButton("Color Picker…", self)
        picker.clicked.connect(self._pick_color)
        row.addWidget(picker)

        set_current = QtWidgets.QPushButton("Load Current Value", self)
        set_current.setToolTip("Read the current color of the first available node into the editor")
        set_current.clicked.connect(self._reload_from_scene)
        row.addWidget(set_current)

        row.addStretch(1)
        self._body.addLayout(row)
        self._reload_from_scene_callback = None

    # ------------------------------------------------------------ colour read/write

    def _rgb_widgets(self) -> List[Any]:
        """Fetch the R/G/B channel widgets ordered by child_index."""
        ordered = sorted(
            (channel for channel in self.channels if channel.child_index is not None),
            key=lambda channel: channel.child_index or 0,
        )
        widgets = []
        for channel in ordered:
            widget = self.channel_widget(channel.key)
            if widget is not None:
                widgets.append(widget)
        return widgets

    def current_rgb(self) -> Tuple[float, float, float]:
        """Current edited value."""
        values = [0.0, 0.0, 0.0]
        for index, widget in enumerate(self._rgb_widgets()[:3]):
            try:
                values[index] = float(widget.value())
            except (TypeError, ValueError):
                values[index] = 0.0
        return (values[0], values[1], values[2])

    def set_rgb(self, rgb) -> None:
        """Set values in R/G/B order."""
        for index, widget in enumerate(self._rgb_widgets()[:3]):
            if index < len(rgb):
                widget.set_value(float(rgb[index]))
        self._update_swatch()
        self.changed.emit()

    def _update_swatch(self) -> None:
        """Update the swatch (values beyond 0-1 are clipped for display only, not for real use)."""
        red, green, blue = self.current_rgb()
        clamped = [min(max(component, 0.0), 1.0) for component in (red, green, blue)]
        color = "rgb(%d, %d, %d)" % tuple(int(component * 255) for component in clamped)
        self._swatch.setStyleSheet(
            f"background-color: {color}; border: 1px solid {BORDER};"
        )
        self._swatch.setToolTip(f"R {red:g} / G {green:g} / B {blue:g}")

    def _reload_from_scene(self) -> None:
        """Read the current colour from the scene again (the actual read is done by a callback
        injected by the main window)."""
        if callable(self._reload_from_scene_callback):
            self._reload_from_scene_callback()

    def set_reload_callback(self, callback) -> None:
        """Inject the "load current value from the scene" callback."""
        self._reload_from_scene_callback = callback

    def _pick_color(self) -> None:
        """Call Maya's colour picker (preserving HDR / colour management behaviour)."""
        from maya import cmds

        try:
            accepted = cmds.colorEditor()
            if not accepted:
                return
            rgb = cmds.colorEditor(query=True, rgb=True)
        except (RuntimeError, TypeError):
            # When Maya's colour picker is unavailable, fall back to Qt's colour dialog
            rgb = self._pick_color_qt()
            if rgb is None:
                return
        self.set_rgb(rgb)

    def _pick_color_qt(self) -> Optional[Tuple[float, float, float]]:
        """Qt colour dialog fallback."""
        from ui.qt import QtGui

        red, green, blue = self.current_rgb()
        initial = QtGui.QColor.fromRgbF(
            min(max(red, 0.0), 1.0), min(max(green, 0.0), 1.0), min(max(blue, 0.0), 1.0)
        )
        color = QtWidgets.QColorDialog.getColor(initial, self, "Choose a color")
        if not color.isValid():
            return None
        return (color.redF(), color.greenF(), color.blueF())
