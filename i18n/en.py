"""English translations (reference language).

Every user-visible string of the tool lives here; the English text is kept
**byte-identical to the original literals** so that switching to English
reproduces the historical behaviour exactly (existing tests assert on these
strings).

Rules:

* Maya data (node / attribute / plug names, enum field names, type labels,
  exception text) is never translated and therefore never appears here.
* Technical metadata lines (``type=... api=...``) are not translated either.
* Dynamic values are ``{named}`` placeholders filled by
  :meth:`i18n.manager.TranslationManager.translate`.
"""

from __future__ import annotations

TRANSLATIONS = {
    # ------------------------------------------------------------------ window
    "window.title": "Batch Attribute Editor",
    "language.label": "Language:",
    "language.english": "English",
    "language.chinese": "中文",
    # ------------------------------------------------------------------- scope
    "scope.title": "Scope · Search Range",
    "scope.option.selection_and_descendants": "Selection + all descendants (incl. shapes)",
    "scope.option.selection_only": "Selection only",
    "scope.refresh_selection": "Refresh Selection",
    "scope.refresh_tooltip": "Read the current selection again and clear the scan cache",
    "scope.no_selection": "No nodes selected",
    # ------------------------------------------------------------------ search
    "search.title": "Attribute Search",
    "search.placeholder": "Attribute name, e.g. visibility / color / custom",
    "search.mode.contains": "Contains",
    "search.mode.exact": "Exact",
    "search.mode.prefix": "Prefix",
    "search.mode.fuzzy": "Fuzzy",
    "search.mode.contains.tooltip": (
        "Matches anywhere in the attribute name (long or short), case-insensitive"
    ),
    "search.mode.exact.tooltip": (
        "Matches only when the whole name equals the search text"
    ),
    "search.mode.prefix.tooltip": (
        "Matches from the start of the name; a stricter subset of Contains"
    ),
    "search.mode.fuzzy.tooltip": (
        "Subsequence match: the typed characters appear in order (vsblt → visibility)"
    ),
    # ----------------------------------------------------------------- filters
    "filter.writable_only": "Writable only",
    "filter.writable_only.tooltip": "Hide attributes Maya reports as read-only",
    "filter.keyable_only": "Keyable only",
    "filter.keyable_only.tooltip": (
        "Keep attributes that can be keyframed "
        "(keyable or shown in the Channel Box)"
    ),
    "filter.user_defined_only": "User defined only",
    "filter.user_defined_only.tooltip": "Keep only User Defined attributes",
    "filter.hide_unsupported": "Hide unsupported",
    "filter.hide_unsupported.tooltip": (
        "Hide matrix / message and other non-editable types"
    ),
    "filter.hide_compound_children": "Hide compound children",
    "filter.hide_compound_children.tooltip": (
        "Hide children such as translateX and keep only the parent attribute"
    ),
    "filter.hide_locked": "Hide locked",
    "filter.hide_locked.tooltip": (
        "Requires per-node validation — slower on large scenes"
    ),
    "filter.hide_connected": "Hide connected",
    "filter.hide_connected.tooltip": (
        "Requires per-node validation — slower on large scenes"
    ),
    # ----------------------------------------------------------------- results
    "results.title": "Results",
    "results.nothing_searched": "Nothing searched yet",
    "results.empty_no_nodes": "No nodes scanned yet — select nodes in the viewport",
    "results.empty_no_match": "No attribute matches (scanned {count} nodes)",
    # ------------------------------------------------------------------- table
    "table.attribute": "Attribute",
    "table.type": "Type",
    "table.nodes": "Nodes",
    "table.other_types": "Other types",
    "table.tooltip.long_name": "Long name: {name}",
    "table.tooltip.short_name": "Short name: {name}",
    "table.tooltip.type": "Type: {type}",
    "table.tooltip.nodes": "Nodes involved: {count}",
    "table.tooltip.other_types": (
        "Nodes with the same name but a different type: {types}"
    ),
    # ----------------------------------------------------------------- details
    "details.title": "Attribute Details",
    "details.field.name": "Name:",
    "details.field.type": "Type:",
    "details.field.matched": "Matched:",
    "details.field.writable": "Writable:",
    "details.field.locked": "Locked:",
    "details.field.connected": "Connected:",
    "details.field.missing": "Missing:",
    "details.field.type_mismatch": "Type mismatch:",
    "details.field.other_type_nodes": "Other-type nodes:",
    "details.validating": "Validating…",
    "common.none": "none",
    # ------------------------------------------------------------------- value
    "value.title": "Value",
    "value.select_hint": "Select an attribute above to edit it",
    "value.not_editable": (
        "{type} type is not editable yet (recognition and inspection only)"
    ),
    "value.no_channels": "This attribute has no editable channels on the current nodes",
    "value.no_channels_editor": "This attribute has no editable channels",
    "value.editor_failed": "Could not create an editor for this attribute",
    "value.read_failed": "Could not read the current value",
    "value.hint.type_nodes": "{type}, {count} nodes",
    "value.hint.channels": "{count} channels",
    "value.hint.units": "Values use Maya working units (degrees / centimetres / frames)",
    "value.hint.no_samples": "No current value could be read, please fill it in manually",
    "value.hint.other_types": (
        "{count} more nodes have this attribute name with a different type "
        "and will be skipped automatically"
    ),
    # --------------------------------------------------------------- technical
    "technical.title": "Technical Details",
    "technical.placeholder": "Technical details (select an attribute)",
    # ----------------------------------------------------------------- preview
    "preview.title": "Preview · Apply",
    "preview.set_value_hint": 'Set a value, then click "Preview"',
    "preview.values_changed": 'Values changed — click "Preview" again',
    "preview.select_attribute": "Select an attribute to edit first",
    "preview.no_channels_enabled": "No channels are enabled",
    "preview.nothing_to_write": "Nothing to write",
    "preview.no_nodes_modified": "No nodes can be modified:\n{detail}",
    "preview.check_filters": "check your filters and scope",
    "preview.require_preview": "A preview is required before applying",
    "preview.undo_hint": "Recorded as a single Undo (Ctrl+Z reverts the whole batch)",
    "preview.nodes_placeholder": "Nodes that will be modified will be listed here",
    "preview.preview_tooltip": (
        "Check which nodes will change and which will be skipped (does not write to the scene)"
    ),
    "preview.apply_tooltip": (
        "A preview is required before applying; the whole batch is a single Undo"
    ),
    "preview.change_line": "{label}: {old} → {new}",
    "preview.some_channels_skipped": "Some channels skipped: {reasons}",
    "preview.skip_count": "{count} {label}",
    "preview.describe.main": "Will modify {nodes} ({channels}), skip {skipped}",
    "preview.describe.partial": ", {nodes} with partially skipped channels",
    "preview.describe.skip_reasons": "\nSkip reasons: {reasons}",
    "preview.describe.other_types": (
        "\n{nodes} with the same attribute name but a different type (excluded)"
    ),
    "preview.skipped_fallback": "skipped",
    "preview.detail.will_modify": "── Will modify ──",
    "preview.detail.skipped": "── Skipped ──",
    # ------------------------------------------------------------------- apply
    "apply.describe.succeeded": "Succeeded:{count}",
    "apply.describe.skipped": "  Skipped:{count}",
    "apply.describe.failed": "  Failed:{count}",
    "apply.describe.touched": "  ({nodes} touched)",
    "apply.describe.elapsed": "  Elapsed {ms} ms",
    # -------------------------------------------------- buttons / report / log
    "button.preview": "Preview",
    "button.apply": "Apply",
    "button.clear": "Clear",
    "button.color_picker": "Color Picker…",
    "button.load_current": "Load Current Value",
    "report.title": "Report · Log",
    "report.placeholder": "Applied changes will be audited here",
    "report.no_operations": "(no operations yet)",
    "report.detail_prefix": "detail:",
    "log.audit_header": "── {attribute} · {value} · {time} · {counts} ──",
    "log.count_changed": "{count} changed",
    "log.count_skipped": "{count} skipped",
    "log.count_failed": "{count} failed",
    "log.node_missing_skipped": "Node no longer exists, skipped",
    "log.not_writable_skipped": "Attribute not writable, skipped",
    "log.undo_open_failed": "Could not open Undo Chunk: {error}",
    "log.undo_close_failed": "Failed to close Undo Chunk: {error}",
    # ------------------------------------------------------------------ status
    "status.ok": "Writable",
    "status.node_missing": "Node no longer exists",
    "status.missing": "Attribute missing",
    "status.type_mismatch": "Type mismatch",
    "status.not_readable": "Not readable",
    "status.not_writable": "Not writable",
    "status.locked": "Locked",
    "status.connected": "Connected",
    "status.channel_missing": "Array element missing",
    "status.unsupported": "Unsupported type",
    "status.type_mismatch_detail": "{status} (node has {type})",
    "status.selection_failed": "Reading the selection failed: {error}",
    "status.operation_failed": "Operation failed: {error}",
    "status.validation_failed": "Validation failed: {error}",
    # --------------------------------------------------------------- summaries
    "summary.matched": "Matched {count}",
    "summary.writable": "Writable {count}",
    "summary.skipped": "Skipped {count}",
    "summary.status_count": "{label} {count}",
    "search.result.describe": (
        "Matched {attributes} / {instances} (scanned {nodes}, {ms} ms)"
    ),
    "traversal.intermediates": "({value})",
    "selection.empty": "No nodes selected — select something in the viewport",
    "selection.covered": ", {count} de-duplicated (covered by another root)",
    "selection.ignored": ", {count} ignored",
    "session.not_selected": "not selected",
    "cache.describe": (
        "Cache: attribute tables for {nodes}, {definitions} (generation {generation})"
    ),
    # ------------------------------------------------------------------ editor
    "editor.channels_written": "These channels are written",
    "editor.tooltip.unit": "Unit: {unit}",
    "editor.tooltip.maya_range": "Maya range: {range}",
    "unit.degrees": "Degrees",
    "unit.centimeters": "Centimeters",
    "unit.frames": "Frames",
    "editor.integer.empty": "cannot be empty",
    "editor.integer.required": "an integer is required",
    "editor.color.preview_tooltip": "Current color preview",
    "editor.color.load_tooltip": (
        "Read the current color of the first available node into the editor"
    ),
    "dialog.choose_color": "Choose a color",
    # ------------------------------------------------------------------ errors
    "error.boolean_parse": "Cannot interpret {value} as a boolean",
    "error.integer_required": "Integer required, got {value}",
    "error.boolean_as_number": "A boolean cannot be used as a numeric value",
    "error.numeric_required": "Numeric value required, got {value}",
    "error.unsupported_type": "Unsupported attribute type: {type}",
    # ------------------------------------------------------------------ counts
    "counts.node.one": "1 node",
    "counts.node.other": "{count} nodes",
    "counts.channel.one": "1 channel",
    "counts.channel.other": "{count} channels",
    "counts.root_node.one": "1 root node",
    "counts.root_node.other": "{count} root nodes",
    "counts.attribute.one": "1 attribute",
    "counts.attribute.other": "{count} attributes",
    "counts.attribute_instance.one": "1 attribute instance",
    "counts.attribute_instance.other": "{count} attribute instances",
    "counts.transform.one": "1 transform",
    "counts.transform.other": "{count} transforms",
    "counts.shape.one": "1 shape",
    "counts.shape.other": "{count} shapes",
    "counts.intermediate.one": "1 intermediate",
    "counts.intermediate.other": "{count} intermediates",
    "counts.dg_node.one": "1 DG node",
    "counts.dg_node.other": "{count} DG nodes",
    "counts.type_definition.one": "1 type definition",
    "counts.type_definition.other": "{count} type definitions",
    "counts.more_change.one": "1 more change",
    "counts.more_change.other": "{count} more changes",
    "counts.more_skipped_node.one": "1 more skipped node",
    "counts.more_skipped_node.other": "{count} more skipped nodes",
}
