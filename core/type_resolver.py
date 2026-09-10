"""Real attribute type resolution (TypeResolver).

**Never guess the type from the return value of ``cmds.getAttr()``.** Every
decision is based on MObject metadata:

    MPlug -> MObject(attribute) -> MFnNumericAttribute / MFnUnitAttribute /
    MFnEnumAttribute / MFnTypedAttribute / MFnCompoundAttribute / MFnAttribute

API shapes confirmed by measurement (Maya 2024 / API 2.0, see docs/ARCHITECTURE.md
section 5):

* ``MFnAttribute.name`` / ``shortName`` / ``dynamic`` / ``keyable`` / ``writable`` /
  ``readable`` / ``hidden`` / ``storable`` / ``usedAsColor`` are all **properties**
  (not methods); to detect a "user defined attribute" use ``dynamic`` -- there is
  **no** ``userDefined``.
* ``MFnNumericAttribute.numericType()`` is a **method**; ``default`` /
  ``usedAsColor`` are properties.
* ``MFnUnitAttribute.unitType()`` is a **method**; ``default`` is a property;
  ``hasMin()/getMin()`` are methods and ``getMin()`` raises when there is no lower
  bound, so ``hasMin()`` has to be asked first.
* ``MFnEnumAttribute.fieldName(i)`` takes an **int**, ``fieldValue(s)`` takes a
  **str**.
* ``MFnTypedAttribute.attrType()`` is a **method**.
* ``MFnMatrixAttribute.matrixType`` **does not exist**; a matrix can only be
  identified through ``apiTypeStr``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from maya.api import OpenMaya as om2

from core.types import (
    AttributeDefinition,
    AttributeKind,
    ChannelSpec,
)
from utils import maya_utils

# ---------------------------------------------------------------------------
# Constant mapping: use the enum values Maya itself provides instead of
# hardcoding integers I guessed
# ---------------------------------------------------------------------------


def _numeric_kind_table() -> dict:
    """Authoritative mapping from ``MFnNumericData::Type`` to :class:`AttributeKind`.

    Built from the constants Maya exposes instead of hardcoded integers (enum
    values may differ between versions).
    """
    data = om2.MFnNumericData
    table = {}

    def register(names: Tuple[str, ...], kind: AttributeKind) -> None:
        for name in names:
            value = getattr(data, name, None)
            if isinstance(value, int):
                table[value] = kind

    register(("kBoolean",), AttributeKind.BOOL)
    register(("kByte", "kChar", "kShort", "kInt", "kLong"), AttributeKind.INT)
    register(("kFloat",), AttributeKind.FLOAT)
    register(("kDouble",), AttributeKind.DOUBLE)
    # Compound numeric types all map to VECTOR3, then get refined further by the
    # child count and by usedAsColor.
    register(("k2Float", "k2Double", "k3Float", "k3Double"), AttributeKind.VECTOR3)
    return table


_NUMERIC_KIND_TABLE = _numeric_kind_table()

# apiTypeStr of compound numeric types (the criterion for Float3 / Double3 / Color3)
_VECTOR_API_TYPES = ("kAttribute3Float", "kAttribute3Double", "kAttribute2Float", "kAttribute2Double")


def numeric_kind(numeric_type: int) -> AttributeKind:
    """Map ``numericType()`` to an attribute kind."""
    return _NUMERIC_KIND_TABLE.get(numeric_type, AttributeKind.UNKNOWN)


def _safe(function, default=None):
    """Call a Maya API that may raise, returning the default value on failure.

    Maya metadata queries raise RuntimeError/TypeError when "the attribute has no
    lower bound", "the plug is not a compound", etc. These are all normal
    situations and must not be allowed to interrupt the scan.
    """
    try:
        return function()
    except (RuntimeError, TypeError, ValueError):
        return default


class TypeResolver:
    """Identify the real attribute type from an MPlug."""

    # ------------------------------------------------------------ Public interface

    @classmethod
    def describe_plug(cls, plug: om2.MPlug) -> Optional[AttributeDefinition]:
        """Identify the attribute definition of a plug; None if the plug is invalid."""
        if maya_utils.plug_is_null(plug):
            return None
        attribute = _safe(plug.attribute)
        if attribute is None or attribute.isNull():
            return None
        return cls.describe_attribute(attribute, plug)

    @classmethod
    def describe_attribute(cls, attribute: om2.MObject,
                           plug: Optional[om2.MPlug] = None) -> AttributeDefinition:
        """Identify the definition of an attribute MObject."""
        fat = om2.MFnAttribute(attribute)
        name = _safe(lambda: fat.name, "") or ""
        short_name = _safe(lambda: fat.shortName, "") or name

        kind, unit_type, enum_fields, numeric_type = cls._classify(attribute, fat)

        definition = AttributeDefinition(
            name=name,
            short_name=short_name,
            kind=kind,
            api_type=attribute.apiTypeStr,
            numeric_type=numeric_type,
            unit_type=unit_type,
            enum_fields=enum_fields,
            is_dynamic=bool(_safe(lambda: fat.dynamic, False)),
            is_keyable=bool(_safe(lambda: fat.keyable, False)),
            is_writable=bool(_safe(lambda: fat.writable, True)),
            is_readable=bool(_safe(lambda: fat.readable, True)),
            is_hidden=bool(_safe(lambda: fat.hidden, False)),
            is_storable=bool(_safe(lambda: fat.storable, True)),
            is_color=bool(_safe(lambda: fat.usedAsColor, False)),
            is_multi=bool(_safe(lambda: plug.isArray, False)) if plug is not None else False,
            is_compound=bool(_safe(lambda: plug.isCompound, False)) if plug is not None else False,
        )

        cls._apply_bounds(definition, attribute)
        definition.default_repr = cls._default_repr(attribute, kind)

        if definition.is_compound and plug is not None:
            definition.children = cls._describe_children(plug)

        # Second confirmation of the color decision: it must be a 3-component
        # compound numeric + usedAsColor. Measured: lambert.color /
        # transform.overrideColorRGB are both apiTypeStr=kAttribute3Float,
        # usedAsColor=True, 3 child plugs.
        if (definition.kind is AttributeKind.VECTOR3 and definition.is_color
                and len(definition.children) == 3):
            definition.kind = AttributeKind.COLOR3

        return definition

    # ------------------------------------------------------------ Type classification

    @staticmethod
    def _classify(attribute: om2.MObject, fat: om2.MFnAttribute
                  ) -> Tuple[AttributeKind, Optional[int], Tuple[Tuple[str, int], ...], Optional[int]]:
        """Returns ``(kind, unit_type, enum_fields, numeric_type)``."""
        api_type = attribute.apiTypeStr

        # 1) Unit attributes (angle / distance / time) -- must take priority over
        #    the numeric check, because doubleAngle / doubleLinear / time are also
        #    numeric attributes.
        if attribute.hasFn(om2.MFn.kUnitAttribute):
            unit_attribute = om2.MFnUnitAttribute(attribute)
            unit_type = _safe(unit_attribute.unitType)
            unit_kind = {
                om2.MFnUnitAttribute.kAngle: AttributeKind.ANGLE,
                om2.MFnUnitAttribute.kDistance: AttributeKind.DISTANCE,
                om2.MFnUnitAttribute.kTime: AttributeKind.TIME,
            }.get(unit_type, AttributeKind.FLOAT)
            return unit_kind, unit_type, (), None

        # 2) Enum
        if attribute.hasFn(om2.MFn.kEnumAttribute):
            return AttributeKind.ENUM, None, TypeResolver._enum_fields(attribute), None

        # 3) Numeric (including compound numeric)
        if attribute.hasFn(om2.MFn.kNumericAttribute):
            numeric_attribute = om2.MFnNumericAttribute(attribute)
            numeric_type = _safe(numeric_attribute.numericType)
            if numeric_type is None:
                return AttributeKind.UNKNOWN, None, (), None
            kind = numeric_kind(numeric_type)
            # An apiTypeStr of kAttribute3Float / kAttribute3Double means it is
            # definitely a 3-component compound numeric
            if api_type in _VECTOR_API_TYPES:
                kind = AttributeKind.VECTOR3
            return kind, None, (), numeric_type

        # 4) Typed attributes such as string
        if attribute.hasFn(om2.MFn.kTypedAttribute):
            typed_attribute = om2.MFnTypedAttribute(attribute)
            data_type = _safe(typed_attribute.attrType)
            if data_type == om2.MFnData.kString:
                return AttributeKind.STRING, None, (), None
            return AttributeKind.UNKNOWN, None, (), None

        # 5) compound (generic compound attribute that is not a 3-component numeric)
        if attribute.hasFn(om2.MFn.kCompoundAttribute):
            return AttributeKind.COMPOUND, None, (), None

        # 6) Types that are not editable but should still be identified and displayed
        if api_type == "kMatrixAttribute":
            return AttributeKind.MATRIX, None, (), None
        if api_type == "kMessageAttribute":
            return AttributeKind.MESSAGE, None, (), None

        return AttributeKind.UNKNOWN, None, (), None

    @staticmethod
    def _enum_fields(attribute: om2.MObject) -> Tuple[Tuple[str, int], ...]:
        """List of enum fields as ``(name, value)``.

        ``fieldName`` takes an int and ``fieldValue`` takes a str -- mixing them
        raises TypeError (measured).
        """
        enum_attribute = om2.MFnEnumAttribute(attribute)
        minimum = _safe(enum_attribute.getMin)
        maximum = _safe(enum_attribute.getMax)
        if minimum is None or maximum is None:
            return ()
        fields: List[Tuple[str, int]] = []
        for index in range(int(minimum), int(maximum) + 1):
            name = _safe(lambda i=index: enum_attribute.fieldName(i))
            if name is None:
                continue
            # fieldName(int) -> name; the write itself uses the enum index.
            fields.append((str(name), index))
        return tuple(fields)

    @staticmethod
    def _describe_children(plug: om2.MPlug) -> Tuple[AttributeDefinition, ...]:
        """Recursively describe the child attributes of a compound (by index, never by
        concatenating names)."""
        children: List[AttributeDefinition] = []
        for child in maya_utils.child_plugs(plug):
            attribute = _safe(child.attribute)
            if attribute is None or attribute.isNull():
                continue
            children.append(TypeResolver.describe_attribute(attribute, child))
        return tuple(children)

    # ------------------------------------------------------------ Bounds and defaults

    @staticmethod
    def _apply_bounds(definition: AttributeDefinition, attribute: om2.MObject) -> None:
        """Read the hard range.

        Read only, and used only as a hint, **never for clamping** -- the
        requirement explicitly says the values must not be silently restricted.
        Measured: ``getMin()`` raises RuntimeError when there is no lower bound, so
        ``hasMin()`` has to be asked first.
        """
        if definition.kind in (AttributeKind.ANGLE, AttributeKind.DISTANCE, AttributeKind.TIME):
            unit_attribute = om2.MFnUnitAttribute(attribute)
            if bool(_safe(unit_attribute.hasMin, False)):
                definition.has_min = True
                definition.min_value = _unit_bound_to_float(
                    _safe(unit_attribute.getMin), definition.kind)
            if bool(_safe(unit_attribute.hasMax, False)):
                definition.has_max = True
                definition.max_value = _unit_bound_to_float(
                    _safe(unit_attribute.getMax), definition.kind)
            return

        if not attribute.hasFn(om2.MFn.kNumericAttribute):
            return

        numeric_attribute = om2.MFnNumericAttribute(attribute)
        if bool(_safe(numeric_attribute.hasMin, False)):
            definition.has_min = True
            value = _safe(numeric_attribute.getMin)
            definition.min_value = float(value) if isinstance(value, (int, float)) else None
        if bool(_safe(numeric_attribute.hasMax, False)):
            definition.has_max = True
            value = _safe(numeric_attribute.getMax)
            definition.max_value = float(value) if isinstance(value, (int, float)) else None

    @staticmethod
    def _default_repr(attribute: om2.MObject, kind: AttributeKind) -> str:
        """Readable representation of the default value (for display only)."""
        if kind is AttributeKind.ENUM:
            value = _safe(lambda: om2.MFnEnumAttribute(attribute).default)
            return "" if value is None else str(value)
        if kind in (AttributeKind.ANGLE, AttributeKind.DISTANCE, AttributeKind.TIME):
            value = _safe(lambda: om2.MFnUnitAttribute(attribute).default)
            converted = _unit_bound_to_float(value, kind)
            return "" if converted is None else _format_number(converted)
        if attribute.hasFn(om2.MFn.kNumericAttribute):
            value = _safe(lambda: om2.MFnNumericAttribute(attribute).default)
            if isinstance(value, (int, float)):
                return _format_number(float(value))
            if isinstance(value, (tuple, list)):
                return ", ".join(_format_number(float(v)) for v in value)
            return ""
        return ""


def _unit_bound_to_float(value, kind: AttributeKind) -> Optional[float]:
    """Convert MAngle / MDistance / MTime to a float in the current working unit.

    Expressed in degrees / centimeters / frames, matching Maya's default working
    units (``cmds.currentUnit``). This only affects the **bounds shown in the UI**;
    writes always use values expressed in Maya's working units.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, om2.MAngle):
        return float(value.asDegrees())
    if isinstance(value, om2.MDistance):
        return float(value.asCentimeters())
    if isinstance(value, om2.MTime):
        return float(value.value)
    if kind is AttributeKind.TIME:
        return float(getattr(value, "value", 0.0))
    return None


def _format_number(value: float) -> str:
    """Compact number formatting (avoids noise such as 0.30000000000000004)."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


# ---------------------------------------------------------------------------
# Channel construction
# ---------------------------------------------------------------------------


def build_channels(plug: Optional[om2.MPlug],
                   definition: AttributeDefinition) -> Tuple[ChannelSpec, ...]:
    """Build all editable channels of an attribute **on this node**.

    For an array attribute only the logical indices that **already exist** are
    enumerated (the first version neither creates nor deletes array elements).
    Different nodes may have different index sets, so aggregation takes the union,
    and nodes where an index is missing are skipped during Apply.
    """
    if plug is None or maya_utils.plug_is_null(plug):
        return _channels_for(definition, element_index=None)

    if definition.is_multi and bool(_safe(lambda: plug.isArray, False)):
        specs: List[ChannelSpec] = []
        for index in maya_utils.existing_element_indices(plug):
            element = _safe(lambda i=index: plug.elementByLogicalIndex(i))
            if element is None:
                continue
            specs.extend(_channels_for(definition, element_index=index, element=element))
        return tuple(specs)

    return _channels_for(definition, element_index=None, element=plug)


def _channels_for(definition: AttributeDefinition, element_index: Optional[int],
                  element: Optional[om2.MPlug] = None) -> Tuple[ChannelSpec, ...]:
    """A scalar produces a single channel; a compound produces one per child attribute."""
    if definition.is_compound and definition.children:
        labels = _child_labels(definition, element)
        specs: List[ChannelSpec] = []
        for index, child in enumerate(definition.children):
            specs.append(
                ChannelSpec(
                    label=labels[index],
                    kind=child.kind,
                    child_index=index,
                    element_index=element_index,
                    unit_type=child.unit_type,
                    enum_fields=child.enum_fields,
                    has_min=child.has_min,
                    has_max=child.has_max,
                    min_value=child.min_value,
                    max_value=child.max_value,
                )
            )
        return tuple(specs)

    return (
        ChannelSpec(
            label="Value",
            kind=definition.kind,
            child_index=None,
            element_index=element_index,
            unit_type=definition.unit_type,
            enum_fields=definition.enum_fields,
            has_min=definition.has_min,
            has_max=definition.has_max,
            min_value=definition.min_value,
            max_value=definition.max_value,
        ),
    )


def _child_labels(definition: AttributeDefinition, element: Optional[om2.MPlug]) -> Tuple[str, ...]:
    """Decide the labels of the compound child channels.

    * Color (Color3) -> ``R/G/B``
    * 3D vector (Float3/Double3) -> ``X/Y/Z``
    * Any other compound -> the child attribute name with the parent attribute name
      prefix stripped (``customVectorX`` -> ``X``); if the naming does not follow
      that convention the complete child attribute name is shown as-is, with no
      guessing.
    """
    count = len(definition.children)
    if definition.kind is AttributeKind.COLOR3 and count == 3:
        return ("R", "G", "B")
    if definition.kind is AttributeKind.VECTOR3 and count == 3:
        return ("X", "Y", "Z")

    labels: List[str] = []
    parent = definition.name or ""
    for child in definition.children:
        name = child.short_name or child.name
        if parent and name.startswith(parent) and len(name) > len(parent):
            stripped = name[len(parent):]
            name = stripped or name
        labels.append(name)
    return tuple(labels)


def resolve_channel_plug(plug: Optional[om2.MPlug],
                         channel: ChannelSpec) -> Optional[om2.MPlug]:
    """Map a :class:`ChannelSpec` back to the **real plug**.

    This is the core of "structure instead of strings": array elements go through
    ``elementByLogicalIndex``, compound child attributes go through ``child``, and
    concatenated names such as ``translateX`` / ``warr[3]`` are never used anywhere.

    If any step does not match structurally (not an array, not a compound, index out
    of range) it returns None, and the caller counts it as "missing / incompatible"
    and skips it.
    """
    if plug is None or maya_utils.plug_is_null(plug):
        return None

    resolved = plug
    if channel.element_index is not None:
        if not bool(_safe(lambda: resolved.isArray, False)):
            return None
        element = _safe(lambda: resolved.elementByLogicalIndex(channel.element_index))
        if element is None or maya_utils.plug_is_null(element):
            return None
        resolved = element

    if channel.child_index is not None:
        if not bool(_safe(lambda: resolved.isCompound, False)):
            return None
        count = _safe(resolved.numChildren, 0)
        if channel.child_index >= count:
            return None
        child = _safe(lambda: resolved.child(channel.child_index))
        if child is None or maya_utils.plug_is_null(child):
            return None
        resolved = child

    return resolved
