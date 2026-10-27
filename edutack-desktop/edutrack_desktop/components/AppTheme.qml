import QtQuick
import QtQuick.Controls.Material

QtObject {
    property bool darkMode: false

    readonly property int controlsTheme: darkMode ? Material.Dark : Material.Light
    readonly property color background: darkMode ? "#111827" : "#f3f6fa"
    readonly property color surface: darkMode ? "#1f2937" : "#ffffff"
    readonly property color raisedSurface: darkMode ? "#273449" : "#f8fafc"
    readonly property color outline: darkMode ? "#3d4a5e" : "#e1e8f0"
    readonly property color divider: darkMode ? "#3d4a5e" : "#e7edf3"
    readonly property color primaryText: darkMode ? "#f3f4f6" : "#173b5e"
    readonly property color secondaryText: darkMode ? "#cbd5e1" : "#667085"
    readonly property color success: darkMode ? "#9be3ad" : "#176b3a"
    readonly property color successSurface: darkMode ? "#173a2b" : "#e8f5ee"
    readonly property color error: darkMode ? "#ffb4a9" : "#b42318"
    readonly property color errorSurface: darkMode ? "#432522" : "#fff0ee"
    readonly property color accentSurface: darkMode ? "#173c3a" : "#e3f3f0"
    readonly property color accent: darkMode ? "#72d3c3" : "#00796b"
    readonly property color primary: darkMode ? "#245d56" : "#173b5e"
    readonly property color headerSecondary: darkMode ? "#cbd5e1" : "#dce8f1"
    readonly property color headerText: "#ffffff"
    readonly property color exportButton: darkMode ? "#238f7d" : "#35b9a1"
    readonly property color exportButtonPressed: darkMode ? "#1c7869" : "#168f7b"
    readonly property color createButton: darkMode ? "#0f8a7b" : "#00897b"
    readonly property color createButtonPressed: darkMode ? "#0c7569" : "#00695c"
}
