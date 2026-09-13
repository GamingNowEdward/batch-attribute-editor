"""Channel widgets for each type.

Every :class:`~core.types.EditorKind` maps to one widget class,
dispatched through :func:`create_channel_widget`. Adding a type only means adding a class
here.

**No clamping on our own initiative**: only the hard range Maya itself declares becomes the
input range; attributes without a declared range use a very wide range so the user can
enter any legal value (requirement section 11: do not restrict underlying attributes that
allow values beyond 0-1).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type

from core.types import AttributeKind, ChannelSpec, EditorKind
from i18n import tr
from ui.editors.base import ChannelWidget
from ui.qt import QtGui, QtWidgets

#: Input range used when no range is declared (large enough to mean "no restriction")
_UNBOUNDED = 1.0e12


class FloatChannelWidget(ChannelWidget):
    """Floating-point input."""

    def _build_input(self) -> None:
        self._spin = QtWidgets.QDoubleSpinBox(self)
        self._spin.setDecimals(6)
        # Keystroke tracking must stay on: with it disabled, spin.value() keeps
        # returning the OLD value until Enter/focus-out, and a click on
        # Preview/Apply right after typing could apply the stale value (measured:
        # the typed value was silently dropped and the old value got written).
        self._spin.setKeyboardTracking(True)
        low = self.channel.min_value if (self.channel.has_min and self.channel.min_value is not None) else -_UNBOUNDED
        high = self.channel.max_value if (self.channel.has_max and self.channel.max_value is not None) else _UNBOUNDED
        if low > high:
            low, high = -_UNBOUNDED, _UNBOUNDED
        self._spin.setRange(low, high)
        self._spin.setSingleStep(0.1)
        self._spin.valueChanged.connect(lambda _: self._notify())
        self._input = self._spin
        self._layout.addWidget(self._spin)
        self._apply_tooltip()

    def value(self) -> Any:
        return float(self._spin.value())

    def set_value(self, value: Any) -> None:
        self._spin.setValue(float(value))

    def commit_edit(self) -> None:
        """Commit a pending edit so it can never be lost at read time."""
        self._spin.interpretText()

    def validation_error(self) -> str:
        return ""


class IntChannelWidget(ChannelWidget):
    """Integer input (with integer validation).

    Uses ``QLineEdit`` + explicit parsing instead of ``QSpinBox``: the requirement is that
    "input must go through integer validation", while a SpinBox silently falls back when
    the user types illegal text, which hides the error.
    """

    def _build_input(self) -> None:
        self._edit = QtWidgets.QLineEdit(self)
        self._edit.setValidator(_integer_validator(self))
        self._edit.textChanged.connect(lambda _: self._on_text())
        self._input = self._edit
        self._layout.addWidget(self._edit)
        self._apply_tooltip()

    def _on_text(self) -> None:
        invalid = bool(self.validation_error())
        self.mark_invalid(invalid, self.validation_error())
        self._notify()

    def value(self) -> Any:
        text = self._edit.text().strip()
        if not text:
            return 0
        return int(text, 10)

    def set_value(self, value: Any) -> None:
        if isinstance(value, float) and float(value).is_integer():
            value = int(value)
        self._edit.setText(str(value))

    def validation_error(self) -> str:
        text = self._edit.text().strip()
        if not text:
            return tr("editor.integer.empty")
        try:
            int(text, 10)
        except ValueError:
            return tr("editor.integer.required")
        return ""


class EnumChannelWidget(ChannelWidget):
    """Enumeration combo box: choose by name, written internally as Maya's enum index."""

    def _build_input(self) -> None:
        self._combo = QtWidgets.QComboBox(self)
        self._fields = self.channel.enum_fields or ()
        for name, _value in self._fields:
            self._combo.addItem(name)
        self._combo.currentIndexChanged.connect(lambda _: self._notify())
        self._input = self._combo
        self._layout.addWidget(self._combo)
        self._apply_tooltip()

    def value(self) -> Any:
        index = self._combo.currentIndex()
        if 0 <= index < len(self._fields):
            return int(self._fields[index][1])
        return index

    def set_value(self, value: Any) -> None:
        for position, (_name, enum_value) in enumerate(self._fields):
            if int(enum_value) == int(value):
                self._combo.setCurrentIndex(position)
                return
        # When the value is not in the field table (the enum was changed), fall back to
        # displaying by index
        if isinstance(value, int) and 0 <= value < self._combo.count():
            self._combo.setCurrentIndex(value)

    def validation_error(self) -> str:
        return ""


class BoolChannelWidget(ChannelWidget):
    """Boolean check box."""

    def _build_input(self) -> None:
        self._check = QtWidgets.QCheckBox(self.channel.display_label, self)
        self._check.toggled.connect(lambda _: self._notify())
        self._input = self._check
        # The boolean control carries its own label, so hide the duplicate label on the left
        if self._label is not None:
            self._label.setVisible(False)
        self._layout.insertWidget(1 if self._checkbox is not None else 0, self._check)
        self._apply_tooltip()

    def value(self) -> Any:
        return bool(self._check.isChecked())

    def set_value(self, value: Any) -> None:
        self._check.setChecked(bool(value))

    def validation_error(self) -> str:
        return ""


class StringChannelWidget(ChannelWidget):
    """String input (never treated as a number)."""

    def _build_input(self) -> None:
        self._edit = QtWidgets.QLineEdit(self)
        self._edit.textChanged.connect(lambda _: self._notify())
        self._input = self._edit
        self._layout.addWidget(self._edit)
        self._apply_tooltip()

    def value(self) -> Any:
        return self._edit.text()

    def set_value(self, value: Any) -> None:
        self._edit.setText("" if value is None else str(value))

    def validation_error(self) -> str:
        return ""


class UnitChannelWidget(FloatChannelWidget):
    """Unit attributes (angle / distance / time).

    Displayed and entered in Maya's **working units** (angle in degrees, length in
    centimetres, time in frames), matching the units used by ``cmds.getAttr`` /
    ``cmds.setAttr``.
    """

    def _apply_tooltip(self) -> None:
        super()._apply_tooltip()
        unit = self.unit_hint()
        if unit and self._label is not None:
            self._label.setText(f"{self.channel.display_label} ({unit})")


def _integer_validator(parent) -> "QtWidgets.QLineEdit":
    """Integer validator (optional import; without it validation is skipped but parsing
    stays explicit)."""
    validator_class = getattr(QtGui, "QIntValidator", None)
    if validator_class is None:
        return None
    return validator_class(parent)


#: EditorKind → widget class
_WIDGET_REGISTRY: Dict[EditorKind, Type[ChannelWidget]] = {
    EditorKind.FLOAT: FloatChannelWidget,
    EditorKind.INT: IntChannelWidget,
    EditorKind.BOOL: BoolChannelWidget,
    EditorKind.STRING: StringChannelWidget,
    EditorKind.ENUM: EnumChannelWidget,
    EditorKind.UNIT: UnitChannelWidget,
    # Every colour and vector channel is a plain float input; the container-level
    # differences are handled by ValueEditor
    EditorKind.COLOR3: FloatChannelWidget,
    EditorKind.VECTOR3: FloatChannelWidget,
}


def register_channel_widget(kind: EditorKind, widget_class: Type[ChannelWidget]) -> None:
    """Register (or override) the channel widget for an editor kind."""
    _WIDGET_REGISTRY[kind] = widget_class


def create_channel_widget(channel: ChannelSpec, checkable: bool = False,
                          parent: Optional[QtWidgets.QWidget] = None) -> ChannelWidget:
    """Create a widget for the channel type."""
    kind = channel.editor_kind
    widget_class = _WIDGET_REGISTRY.get(kind)
    if widget_class is None:
        widget_class = _WIDGET_REGISTRY[EditorKind.FLOAT]
    return widget_class(channel, checkable=checkable, parent=parent)
