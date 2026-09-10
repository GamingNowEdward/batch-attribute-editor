"""Base classes for value editors and channel widgets.

Design:

* :class:`ChannelWidget` - the input control for **a single channel** (one number field /
  check box / combo box). It knows how to turn a :class:`ChannelSpec` into a widget, and
  how to read, set and validate its value.
* :class:`ValueEditor` - the editor for **one attribute**, composed of several channel
  widgets.

This way "adding a new attribute type" only requires registering a new channel widget;
the layout and signal logic are fully reused.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.types import AttributeDefinition, ChannelSpec
from ui.qt import QtCore, QtWidgets, Signal

ChannelKey = Tuple[Optional[int], Optional[int]]


class ChannelWidget(QtWidgets.QWidget):
    """Input control for a single channel.

    The check box switch (``checkable``) is used for compound attributes: the user can tick
    only the channels they want to write, avoiding the accident of "only R should change but
    G/B get written as well". Single-channel attributes do not show a check box, so no
    visual noise is added.
    """

    changed = Signal()

    def __init__(self, channel: ChannelSpec, checkable: bool = False,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.channel = channel
        self._checkable = checkable
        self._checkbox: Optional[QtWidgets.QCheckBox] = None
        self._label: Optional[QtWidgets.QLabel] = None
        self._input: Optional[QtWidgets.QWidget] = None
        self._error = ""

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 1, 0, 1)
        self._layout.setSpacing(6)

        if checkable:
            self._checkbox = QtWidgets.QCheckBox()
            self._checkbox.setChecked(True)
            self._checkbox.setToolTip("These channels are written")
            self._checkbox.toggled.connect(lambda _: self.changed.emit())
            self._layout.addWidget(self._checkbox)

        self._label = QtWidgets.QLabel(channel.display_label)
        self._label.setMinimumWidth(56)
        self._layout.addWidget(self._label)

        self._build_input()
        self._layout.addStretch(1)

    # ------------------------------------------------------------ subclass interface

    def _build_input(self) -> None:
        """Build the input control (implemented by subclasses)."""
        raise NotImplementedError

    def value(self) -> Any:
        """Current value (implemented by subclasses)."""
        raise NotImplementedError

    def set_value(self, value: Any) -> None:
        """Set the current value (implemented by subclasses)."""
        raise NotImplementedError

    # ------------------------------------------------------------ shared behaviour

    @property
    def key(self) -> ChannelKey:
        return self.channel.key

    def is_enabled_channel(self) -> bool:
        """Whether this channel takes part in the write."""
        return True if self._checkbox is None else self._checkbox.isChecked()

    def set_enabled_channel(self, enabled: bool) -> None:
        if self._checkbox is not None:
            self._checkbox.setChecked(enabled)

    def commit_edit(self) -> None:
        """Commit a pending edit in the input control (no-op by default).

        Numeric spin boxes defer their value until Enter / focus-out; they override
        this so a value the user typed can never be lost when a button is clicked
        before the edit was committed.
        """

    def range_hint(self) -> str:
        """Hint for the value range Maya declares (a hint only, never a forced clamp)."""
        channel = self.channel
        if channel.has_min and channel.has_max:
            return f"{_format_number(channel.min_value)} ~ {_format_number(channel.max_value)}"
        if channel.has_min:
            return f"≥ {_format_number(channel.min_value)}"
        if channel.has_max:
            return f"≤ {_format_number(channel.max_value)}"
        return ""

    def unit_hint(self) -> str:
        """Unit hint (angle / distance / time and so on)."""
        from core.types import AttributeKind

        return {
            AttributeKind.ANGLE: "Degrees",
            AttributeKind.DISTANCE: "Centimeters",
            AttributeKind.TIME: "Frames",
        }.get(self.channel.kind, "")

    def _apply_tooltip(self) -> None:
        parts = [f"{self.channel.kind.display_name}"]
        unit = self.unit_hint()
        if unit:
            parts.append(f"Unit: {unit}")
        hint = self.range_hint()
        if hint:
            parts.append(f"Maya range: {hint}")
        self.setToolTip(" · ".join(parts))

    def _notify(self) -> None:
        self.changed.emit()

    def mark_invalid(self, invalid: bool, message: str = "") -> None:
        """Mark whether the input is invalid (used for integer validation and so on)."""
        self._error = message if invalid else ""
        if self._input is not None:
            self._input.setProperty("invalid", "true" if invalid else "false")
            style = self._input.style()
            if style is not None:
                style.unpolish(self._input)
                style.polish(self._input)
        if self._label is not None:
            self._label.setToolTip(message or "")


def _format_number(value: Optional[float]) -> str:
    """Compact display for a number."""
    if value is None:
        return "?"
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


class ValueEditor(QtWidgets.QWidget):
    """Value editor for a single attribute.

    Created by :class:`~ui.editors.factory.ValueEditorFactory`
    according to the attribute type; it is only responsible for layout, collecting values
    and validation.
    """

    changed = Signal()

    def __init__(self, definition: AttributeDefinition, channels: Sequence[ChannelSpec],
                 samples: Optional[Dict[ChannelKey, Any]] = None,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.definition = definition
        self.channels = tuple(channels)
        self._widgets: Dict[ChannelKey, ChannelWidget] = {}
        self._body = QtWidgets.QVBoxLayout(self)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(2)

        self._build_channels(samples or {})

    # ------------------------------------------------------------ construction

    def _build_channels(self, samples: Dict[ChannelKey, Any]) -> None:
        """Create a control for every channel."""
        multi_channel = len(self.channels) > 1
        for channel in self.channels:
            widget = self.create_channel_widget(channel, checkable=multi_channel)
            self._widgets[channel.key] = widget
            widget.changed.connect(self._on_channel_changed)
            self._body.addWidget(widget)
            if channel.key in samples:
                try:
                    widget.set_value(samples[channel.key])
                except (TypeError, ValueError):
                    pass

    def create_channel_widget(self, channel: ChannelSpec,
                              checkable: bool = False) -> ChannelWidget:
        """Create a channel widget (subclasses may override this, e.g. for colour channels)."""
        from ui.editors.channel_widgets import create_channel_widget

        return create_channel_widget(channel, checkable=checkable, parent=self)

    def _on_channel_changed(self) -> None:
        self.changed.emit()

    # ------------------------------------------------------------ get / set values

    def commit(self) -> None:
        """Commit every pending channel edit (called before values() is read)."""
        for widget in self._widgets.values():
            widget.commit_edit()

    def values(self) -> Dict[ChannelKey, Any]:
        """Current editing result: only the **enabled** channels are included."""
        result: Dict[ChannelKey, Any] = {}
        for key, widget in self._widgets.items():
            if not widget.is_enabled_channel():
                continue
            try:
                result[key] = widget.value()
            except (TypeError, ValueError):
                continue
        return result

    def set_values(self, values: Dict[ChannelKey, Any]) -> None:
        """Set several values at once (with signals blocked to avoid a flood of refreshes)."""
        for key, widget in self._widgets.items():
            if key not in values:
                continue
            blocker = QtCore.QSignalBlocker(widget)
            try:
                widget.set_value(values[key])
            except (TypeError, ValueError):
                pass
            del blocker
        self.changed.emit()

    # ------------------------------------------------------------ validation

    def invalid_channels(self) -> List[str]:
        """List the labels of the channels whose current input is invalid."""
        problems: List[str] = []
        for widget in self._widgets.values():
            if not widget.is_enabled_channel():
                continue
            message = getattr(widget, "validation_error", lambda: "")()
            if message:
                problems.append(f"{widget.channel.display_label}: {message}")
        return problems

    def is_valid(self) -> bool:
        """Whether every enabled channel can be parsed into a legal value."""
        return not self.invalid_channels()

    def enabled_channel_count(self) -> int:
        """Number of channels taking part."""
        return sum(1 for widget in self._widgets.values() if widget.is_enabled_channel())

    def channel_widget(self, key: ChannelKey) -> Optional[ChannelWidget]:
        """Get a control by channel key (used by the colour editor)."""
        return self._widgets.get(key)
