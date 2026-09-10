"""Dynamic value editor layer.

The UI never manipulates Maya nodes directly; the editors only produce a
"channel → value" mapping, and Core's :class:`~core.batch_setter.BatchSetter` is
responsible for writing it.
"""

from __future__ import annotations

from ui.editors.base import (
    ChannelKey,
    ChannelWidget,
    ValueEditor,
)
from ui.editors.channel_widgets import (
    BoolChannelWidget,
    EnumChannelWidget,
    FloatChannelWidget,
    IntChannelWidget,
    StringChannelWidget,
    UnitChannelWidget,
    create_channel_widget,
    register_channel_widget,
)
from ui.editors.factory import ValueEditorFactory
from ui.editors.value_editors import (
    ColorValueEditor,
    ScalarValueEditor,
    VectorValueEditor,
)

__all__ = [
    "BoolChannelWidget",
    "ChannelKey",
    "ChannelWidget",
    "ColorValueEditor",
    "EnumChannelWidget",
    "FloatChannelWidget",
    "IntChannelWidget",
    "ScalarValueEditor",
    "StringChannelWidget",
    "UnitChannelWidget",
    "ValueEditor",
    "ValueEditorFactory",
    "VectorValueEditor",
    "create_channel_widget",
    "register_channel_widget",
]
