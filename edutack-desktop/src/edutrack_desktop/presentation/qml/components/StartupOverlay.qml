import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Rectangle {
    id: startupScreen
    property var theme
    property var windowController
    property bool startupComplete: false
    property bool closePending: false
    signal closeRequested()
    anchors.fill: parent
    z: 1000
    visible: !startupComplete
    color: theme.background

    MouseArea {
        anchors.fill: parent
    }

    WindowCloseButton {
        objectName: "windowCloseDuringStartupButton"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 48
        anchors.rightMargin: 42
        windowController: startupScreen.windowController
        theme: startupScreen.theme
        onCloseRequested: startupScreen.closeRequested()
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
            text: startupScreen.closePending
                  ? "La aplicación se cerrará al finalizar la operación."
                  : "Cargando EduTrack..."
            color: theme.primaryText
            font.pixelSize: 18
        }
    }
}
