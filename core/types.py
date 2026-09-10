"""Attribute type data model (pure data, no dependency on the Maya API).

This layer holds no MObject / MPlug, so it can be cached, compared and serialized,
and it can also be unit tested outside mayapy.

The measured basis for type identification is in docs/ARCHITECTURE.md section 5; this
module only describes "what the identification result looks like", while "how it is
identified" lives in :mod:`core.type_resolver`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional, Tuple


class AttributeKind(enum.Enum):
    """Real data type of an attribute (from Maya metadata, never guessed from the value)."""

    FLOAT = "float"
    DOUBLE = "double"
    INT = "int"
    BOOL = "bool"
    STRING = "string"
    ENUM = "enum"
    ANGLE = "angle"
    DISTANCE = "distance"
    TIME = "time"
    VECTOR3 = "vector3"
    COLOR3 = "color3"
    COMPOUND = "compound"
    MATRIX = "matrix"
    MESSAGE = "message"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        """Type name shown in the UI."""
        return _KIND_DISPLAY_NAMES[self]

    @property
    def is_editable(self) -> bool:
        """Whether an editor is offered (not offered for matrix / message / unknown)."""
        return self not in (AttributeKind.MATRIX, AttributeKind.MESSAGE, AttributeKind.UNKNOWN)

    @property
    def is_numeric(self) -> bool:
        """Whether this is a single-value numeric type."""
        return self in (
            AttributeKind.FLOAT,
            AttributeKind.DOUBLE,
            AttributeKind.INT,
            AttributeKind.ANGLE,
            AttributeKind.DISTANCE,
            AttributeKind.TIME,
        )


_KIND_DISPLAY_NAMES = {
    AttributeKind.FLOAT: "Float",
    AttributeKind.DOUBLE: "Double",
    AttributeKind.INT: "Integer",
    AttributeKind.BOOL: "Boolean",
    AttributeKind.STRING: "String",
    AttributeKind.ENUM: "Enum",
    AttributeKind.ANGLE: "Angle",
    AttributeKind.DISTANCE: "Distance",
    AttributeKind.TIME: "Time",
    AttributeKind.VECTOR3: "Float3",
    AttributeKind.COLOR3: "Color3",
    AttributeKind.COMPOUND: "Compound",
    AttributeKind.MATRIX: "Matrix",
    AttributeKind.MESSAGE: "Message",
    AttributeKind.UNKNOWN: "Unknown",
}


class EditorKind(enum.Enum):
    """Editor kinds used by ValueEditorFactory."""

    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    STRING = "string"
    ENUM = "enum"
    VECTOR3 = "vector3"
    COLOR3 = "color3"
    UNIT = "unit"
    NONE = "none"


def editor_kind_for(kind: AttributeKind, unit_type: Optional[int] = None,
                    enum_fields: Tuple[Tuple[str, int], ...] = ()) -> EditorKind:
    """Map an attribute kind to an editor kind. A new type only needs a line here."""
    if kind is AttributeKind.BOOL:
        return EditorKind.BOOL
    if kind is AttributeKind.STRING:
        return EditorKind.STRING
    if kind is AttributeKind.ENUM:
        return EditorKind.ENUM if enum_fields else EditorKind.INT
    if kind is AttributeKind.INT:
        return EditorKind.INT
    if kind in (AttributeKind.FLOAT, AttributeKind.DOUBLE):
        return EditorKind.FLOAT
    if kind in (AttributeKind.ANGLE, AttributeKind.DISTANCE, AttributeKind.TIME):
        return EditorKind.UNIT
    if kind is AttributeKind.COLOR3:
        return EditorKind.COLOR3
    if kind in (AttributeKind.VECTOR3, AttributeKind.COMPOUND):
        return EditorKind.VECTOR3
    return EditorKind.NONE


@dataclass(frozen=True)
class ChannelSpec:
    """One **editable channel**.

    A single attribute may map to several channels: ``translate`` has X/Y/Z, and for
    an array attribute every existing logical index gets its own group of channels.
    A channel is the smallest unit for generating UI widgets and for mapping user
    input back to a concrete plug.

    * ``child_index`` -- corresponds to ``plug.child(i)``, used for compound child
      attributes. Measured: an index must be used rather than concatenated names,
      because the child names of a color attribute vary with the attribute
      (``colorR`` / ``overrideColorR`` / ``objectColorR``).
    * ``element_index`` -- corresponds to ``plug.elementByLogicalIndex(i)``, used for
      array elements.
    """

    label: str
    kind: AttributeKind
    child_index: Optional[int] = None
    element_index: Optional[int] = None
    unit_type: Optional[int] = None
    enum_fields: Tuple[Tuple[str, int], ...] = ()
    has_min: bool = False
    has_max: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    @property
    def key(self) -> Tuple[Optional[int], Optional[int]]:
        """Unique channel key: ``(element_index, child_index)``."""
        return (self.element_index, self.child_index)

    @property
    def display_label(self) -> str:
        """UI label. Array channels carry an index prefix so the user can tell them apart."""
        if self.element_index is None:
            return self.label
        return f"[{self.element_index}] {self.label}"

    @property
    def editor_kind(self) -> EditorKind:
        """Derive the editor kind from the channel type."""
        return editor_kind_for(self.kind, self.unit_type, self.enum_fields)


@dataclass
class AttributeDefinition:
    """The **definition** of an attribute: type, constraints, child structure.

    This is "the definition of a given attribute on a given node". An attribute with
    the same name may be of a different type on different nodes, so a definition is
    always used together with the node it came from and is never merged across
    types.
    """

    name: str
    short_name: str
    kind: AttributeKind
    api_type: str = ""
    numeric_type: Optional[int] = None
    unit_type: Optional[int] = None
    enum_fields: Tuple[Tuple[str, int], ...] = ()
    has_min: bool = False
    has_max: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default_repr: str = ""
    is_dynamic: bool = False
    is_keyable: bool = False
    is_channel_box: bool = False
    is_writable: bool = True
    is_readable: bool = True
    is_hidden: bool = False
    is_storable: bool = True
    is_multi: bool = False
    is_compound: bool = False
    is_compound_child: bool = False
    is_color: bool = False
    children: Tuple["AttributeDefinition", ...] = field(default_factory=tuple)

    # ---------------------------------------------------------------- Display

    @property
    def type_label(self) -> str:
        """Exact type label: distinguishes Float3 from Double3."""
        if self.kind is AttributeKind.VECTOR3:
            return "Double3" if self._is_double3 else "Float3"
        if self.kind is AttributeKind.COLOR3:
            return "Color3"
        if self.kind is AttributeKind.COMPOUND:
            return f"Compound({len(self.children)})" if self.children else "Compound"
        return self.kind.display_name

    @property
    def _is_double3(self) -> bool:
        """Whether this is of the double3 family (decided from apiTypeStr, not from the
        numeric_type integer value)."""
        return self.api_type in ("kAttribute3Double",)

    @property
    def supports_editing(self) -> bool:
        """Whether an editor can be generated for this attribute."""
        if not self.kind.is_editable:
            return False
        if self.kind is AttributeKind.COMPOUND and not self.children:
            return False
        return True

    @property
    def signature(self) -> Tuple[str, str, str, bool]:
        """Grouping signature: the same name with a different type lands in a different group."""
        return (self.name, self.kind.value, self.type_label, self.is_multi)

    @property
    def editor_kind(self) -> EditorKind:
        """The editor kind used for this attribute."""
        return editor_kind_for(self.kind, self.unit_type, self.enum_fields)

    def enum_labels(self) -> Tuple[str, ...]:
        """List of enum field names."""
        return tuple(name for name, _ in self.enum_fields)

    def describe(self) -> str:
        """Single-line type description, used for Technical Details."""
        parts = [f"type={self.type_label}", f"api={self.api_type}"]
        if self.numeric_type is not None:
            parts.append(f"numeric={self.numeric_type}")
        if self.unit_type is not None:
            parts.append(f"unit={self.unit_type}")
        if self.is_multi:
            parts.append("multi")
        if self.is_compound:
            parts.append("compound")
        if self.is_dynamic:
            parts.append("userDefined")
        if self.is_keyable:
            parts.append("keyable")
        if not self.is_writable:
            parts.append("readOnly")
        return " ".join(parts)
