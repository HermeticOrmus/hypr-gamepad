import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons
import qs.Ui
import "Map.js" as MapLogic

// The DualSense's map (hypr-gamepad: omarchy/ormus.hypr-gamepad-map). Holding Options shows what each
// control does in the focused window; a tap keeps it up until the next one. hypr-gamepad sends
// Hyprland events: "ormus.hypr-gamepad-map show <kind> <layer>" and "... hide". The rows come from
// `hypr-gamepad map --json`, the daemon's own table, so the map
// never says what the pad does not do. Visual only: no keyboard, an empty input region (as the OSD).
Item {
    id: root
    property var shell: null
    property var manifest: null
    readonly property string pluginId: "ormus.hypr-gamepad-map"

    property bool shown: false
    property string kind: "other"
    property bool grouped: false   // the window is in a Hyprland group: L1/R1 switch its tabs
    property string padLayer: "base"  // not "layer": every Item has a FINAL one
    property var doc: null
    property string problem: ""
    property var targetScreen: Quickshell.screens[0] || null
    // The golden touch: the side of the pad in force now, and nothing else on this view.
    readonly property color gold: "#FFD700"
    readonly property real pad: Style.space(28)
    readonly property real columnWidth: Style.space(420)
    readonly property real glyphWidth: Style.space(26)
    readonly property real nameWidth: Style.space(118)

    function pickScreen() {
        var name = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : ""
        var screens = Quickshell.screens
        for (var i = 0; i < screens.length; ++i) {
            if (screens[i].name === name) { targetScreen = screens[i]; return }
        }
        targetScreen = screens[0] || null
    }

    function show(k, l, g) {
        kind = String(k)
        grouped = g === true
        padLayer = l === "world" ? "world" : "base"
        if (!shown) pickScreen()
        shown = true
        if (!reader.running) reader.running = true  // the battery and the table, fresh each time
    }

    function hide() { shown = false }

    function hyprlandEvent(data) {
        var parts = String(data).split(" ")
        if (parts[0] !== pluginId) return
        if (parts[1] === "show" && parts.length === 5) show(parts[2], parts[3], parts[4] === "1")
        else if (parts[1] === "show" && parts.length === 4) show(parts[2], parts[3], false)
        else if (parts[1] === "hide" && parts.length === 2) hide()
    }

    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "custom") root.hyprlandEvent(event.data) }
    }

    Process {
        id: reader
        command: ["hypr-gamepad", "map", "--json"]
        stdout: StdioCollector { id: readOut; waitForEnd: true }
        onExited: function(code) {
            if (code !== 0) { root.problem = "hypr-gamepad map did not answer"; return }
            try {
                var doc = JSON.parse(readOut.text)
                if (!doc.layers || !Array.isArray(doc.layers.base)) throw new Error("no rows")
                root.doc = doc
                root.problem = ""
            } catch (e) { root.problem = "hypr-gamepad map gave no map" }
        }
    }

    // `omarchy-shell ormus.hypr-gamepad-map status`: what the map holds now (checks without a screen).
    IpcHandler {
        target: "ormus.hypr-gamepad-map"
        function status(): string {
            return JSON.stringify({ shown: root.shown, kind: root.kind, layer: root.padLayer, problem: root.problem,
                rows: root.doc ? root.doc.layers.base.length + root.doc.layers.world.length : 0 })
        }
        function show(kind: string, layer: string): void { root.show(kind, layer, false) }
        function hide(): void { root.hide() }
    }

    PanelWindow {
        id: panel
        screen: root.targetScreen
        visible: root.shown
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "ormus-hypr-gamepad-map"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region {}

        BorderSurface {
            id: plate
            anchors.centerIn: parent
            width: plate.borderLeft + root.pad * 3 + root.columnWidth * 2 + plate.borderRight
            height: plate.borderTop + root.pad + body.implicitHeight + root.pad + plate.borderBottom
            // A screen lower than the map (a laptop's 800) shrinks it about its centre, so all of it shows.
            scale: MapLogic.fitScale(plate.height, panel.height, root.pad)
            color: Util.alpha(Color.background, 0.97)
            // A quiet hairline, not the theme's popup border: a theme may make that border gold, and
            // the one gold here is the side of the pad in force.
            border.width: 1
            border.color: Util.alpha(Color.popups.text, 0.22)
            radius: Style.cornerRadius

            Column {
                id: body
                x: plate.borderLeft + root.pad
                y: plate.borderTop + root.pad
                width: root.columnWidth * 2 + root.pad
                spacing: Style.space(18)

                Item {
                    width: parent.width
                    height: title.implicitHeight
                    // Siblings, so the phrase and the battery can sit on the title's line.
                    Text {
                        id: title
                        text: "DualSense"
                        color: Color.popups.text
                        font.family: Style.font.family
                        font.pixelSize: Style.font.display
                    }
                    Text {
                        anchors.left: title.right
                        anchors.leftMargin: Style.space(12)
                        anchors.baseline: title.baseline
                        text: MapLogic.kindPhrase(root.kind)
                        color: Color.muted
                        font.family: Style.font.family
                        font.pixelSize: Style.font.heading
                    }
                    Text {
                        anchors.right: parent.right
                        anchors.baseline: title.baseline
                        text: root.problem || (root.doc && root.doc.battery ? "Battery " + root.doc.battery : "")
                        color: root.problem ? Color.urgent : Color.muted
                        font.family: Style.font.family
                        font.pixelSize: Style.font.title
                    }
                }

                Row {
                    spacing: root.pad
                    Repeater {
                        model: MapLogic.layerOrder(root.padLayer)
                        delegate: Column {
                            id: side
                            required property string modelData
                            readonly property bool inForce: modelData === root.padLayer
                            readonly property var rows: root.doc ? root.doc.layers[modelData] || [] : []
                            width: root.columnWidth
                            spacing: Style.space(3)
                            opacity: inForce ? 1.0 : 0.62

                            Text {
                                text: root.doc ? root.doc.layer_names[side.modelData] : ""
                                color: side.inForce ? root.gold : Color.popups.text
                                font.family: Style.font.family
                                font.pixelSize: Style.font.heading
                                bottomPadding: Style.space(4)
                            }
                            Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.popups.text, 0.18) }

                            Repeater {
                                model: side.rows
                                delegate: Column {
                                    id: line
                                    required property var modelData
                                    required property int index
                                    readonly property bool live: MapLogic.applies(modelData, root.kind, root.grouped)
                                    width: side.width

                                    Text {
                                        visible: MapLogic.opensGroup(side.rows, line.index)
                                        text: line.modelData.group
                                        color: Color.muted
                                        font.family: Style.font.family
                                        font.pixelSize: Style.font.body
                                        topPadding: line.index === 0 ? Style.space(6) : Style.space(12)
                                        bottomPadding: Style.space(2)
                                    }
                                    Row {
                                        opacity: line.live ? 1.0 : 0.34
                                        Text {
                                            width: root.glyphWidth
                                            text: line.modelData.glyph
                                            color: Color.popups.text
                                            font.family: Style.font.family
                                            font.pixelSize: Style.font.heading
                                        }
                                        Text {
                                            width: root.nameWidth
                                            text: line.modelData.name
                                            color: Color.muted
                                            font.family: Style.font.family
                                            font.pixelSize: Style.font.title
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            width: root.columnWidth - root.glyphWidth - root.nameWidth
                                            text: MapLogic.labelFor(line.modelData, root.kind, root.grouped)
                                            color: Color.popups.text
                                            font.family: Style.font.family
                                            font.pixelSize: Style.font.title
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Text {
                    text: "Hold Options for this map, tap it to keep it up. L2 shows the desktop side."
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                }
            }
        }
    }
}
