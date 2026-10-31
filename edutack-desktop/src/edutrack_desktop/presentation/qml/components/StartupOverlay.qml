import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: startupScreen
    property var theme
    property bool startupComplete: false
    anchors.fill: parent
    z: 1000
    visible: !startupComplete
    color: theme.background

    MouseArea {
        anchors.fill: parent
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 14
        BusyIndicator {
            Layout.alignment: Qt.AlignHCenter
            running: startupScreen.visible
        }
        Label {
            Layout.alignment: Qt.AlignHCenter
            text: "Cargando EduTrack..."
            color: theme.primaryText
            font.pixelSize: 18
        }
    }
}
