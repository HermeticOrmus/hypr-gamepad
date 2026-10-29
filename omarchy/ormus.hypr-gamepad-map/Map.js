.pragma library
// Map.js: the pad map's words and choices. Plain functions, no QML, so the Node tests run this same
// file (tests/map.test.mjs).

// Where the map says the pad is, from the kind hypr-gamepad read for the focused window.
function kindPhrase(kind) {
    return ({ herdr: "inside herdr", browser: "in the browser", board: "on the Sun board",
              terminal: "in a terminal" })[kind] || "in this window"
}

// A row does something in this window when its action knows the window's kind, or any window, or
// the window is in a Hyprland group and the action works a group ("group": L1/R1 switch its tabs).
// The list is read by index, not with Array.isArray: a row handed through a Repeater's model is a
// list-like wrapper that Array.isArray says no to (it lit every row in a browser, 2026-10-29).
function applies(row, kind, grouped) {
    var kinds = row ? row.kinds : null
    if (!kinds || kinds.length === undefined) return true
    for (var i = 0; i < kinds.length; ++i) {
        if (kinds[i] === "*" || kinds[i] === kind || (grouped && kinds[i] === "group")) return true
    }
    return false
}

// What a row says in this window: its words for the window's kind, else for a group when the window
// is in one, else its own.
function labelFor(row, kind, grouped) {
    if (!row) return ""
    var labels = row.labels || {}
    if (labels[kind]) return labels[kind]
    if (grouped && labels.group) return labels.group
    return row.label
}

// A row opens its group (the group's name is drawn above it) when the row before is another group's.
function opensGroup(rows, i) {
    return i === 0 || !rows[i - 1] || rows[i - 1].group !== rows[i].group
}

// The two sides of the pad, the one in force first.
function layerOrder(layer) {
    return layer === "world" ? ["world", "base"] : ["base", "world"]
}

// How much the map shrinks to fit its screen: as drawn when it fits, else just small enough that the
// whole plate shows with `margin` above and below it. Nothing measured yet: as drawn.
function fitScale(height, room, margin) {
    if (!(height > 0) || !(room > 0)) return 1
    return Math.min(1, (room - 2 * margin) / height)
}
