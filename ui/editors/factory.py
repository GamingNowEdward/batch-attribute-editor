"""ValueEditorFactory: returns the editor matching the attribute's real type.

Adding a new attribute type takes only two steps:

1. give it an :class:`~core.types.EditorKind` in ``core.types``;
2. register the editor class for that kind here (or register a channel widget in
   channel_widgets).

No other part of the UI needs to change.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Type

from core.types import (
    AttributeDefinition,
    AttributeKind,
    ChannelSpec,
    EditorKind,
)
from ui.editors.base import ChannelKey, ValueEditor
from ui.editors.value_editors import (
    ColorValueEditor,
    ScalarValueEditor,
    VectorValueEditor,
)
from ui.qt import QtWidgets


class ValueEditorFactory:
    """Create value editors according to the attribute type."""

    #: EditorKind → editor class
    _registry: Dict[EditorKind, Type[ValueEditor]] = {
        EditorKind.FLOAT: ScalarValueEditor,
        EditorKind.INT: ScalarValueEditor,
        EditorKind.BOOL: ScalarValueEditor,
        EditorKind.STRING: ScalarValueEditor,
        EditorKind.ENUM: ScalarValueEditor,
        EditorKind.UNIT: ScalarValueEditor,
        EditorKind.VECTOR3: VectorValueEditor,
        EditorKind.COLOR3: ColorValueEditor,
    }

    @classmethod
    def register(cls, kind: EditorKind, editor_class: Type[ValueEditor]) -> None:
        """Register/override an editor kind."""
        cls._registry[kind] = editor_class

    @classmethod
    def editor_class_for(cls, definition: AttributeDefinition) -> Type[ValueEditor]:
        """Choose the editor class.

        A multi-channel attribute must use the multi-channel editor even when its type is
        scalar (a multi array, for example), otherwise the user cannot tell ``input[0]``
        apart from ``input[1]``.
        """
        if len(definition.children) > 3 and definition.kind is AttributeKind.COMPOUND:
            return VectorValueEditor
        return cls._registry.get(definition.editor_kind, ScalarValueEditor)

    @classmethod
    def create(cls, definition: AttributeDefinition, channels: Sequence[ChannelSpec],
               samples: Optional[Dict[ChannelKey, Any]] = None,
               parent: Optional[QtWidgets.QWidget] = None) -> Optional[ValueEditor]:
        """Create the editor; returns None when the attribute is not editable or has no channels."""
        if not channels:
            return None
        editor_class = cls.editor_class_for(definition)
        editor = editor_class(definition, channels, samples or {}, parent)
        return editor

    @classmethod
    def create_placeholder(cls, message: str,
                           parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QLabel:
        """Explanatory label shown when editing is not possible."""
        label = QtWidgets.QLabel(message, parent)
        label.setObjectName("hintLabel")
        label.setWordWrap(True)
        return label
