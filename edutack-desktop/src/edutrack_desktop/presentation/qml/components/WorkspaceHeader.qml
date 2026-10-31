import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "."

Rectangle {
    id: windowTitleBar
    property var windowController
    property var backendObject
    property var theme
    signal closeCampusRequested()
    signal darkModeToggleRequested()
    signal exportRequested()
    Layout.fillWidth: true
    Layout.preferredHeight: 88
    radius: 0
    color: Material.primary

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 20
        spacing: 18

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 3

                Label {
                    text: "EduTrack Desktop"
                    color: theme.headerText
                    font.pixelSize: 23
                    font.bold: true
                }
                Label {
                    Layout.fillWidth: true
                    text: backendObject.campusName
                    color: theme.headerSecondary
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }
        }
        Button {
            objectName: "closeCampusButton"
            text: "Cerrar sede"
            flat: true
            visible: backendObject.hasWorkspace
            Material.foreground: theme.headerText
            onClicked: closeCampusRequested()
        }
        IconTextButton {
            text: windowController.darkMode ? "Modo claro" : "Modo nocturno"
            symbolName: windowController.darkMode ? "light_mode" : "dark_mode"
            symbolColor: theme.headerText
            flat: true
            Material.foreground: theme.headerText
            onClicked: darkModeToggleRequested()
        }
        IconTextButton {
            id: exportButton
            text: backendObject.isNewCampus
                  ? "Exportar sede inicial"
                  : "Exportar sincronización"
            symbolName: "ios_share"
            symbolColor: theme.headerText
            Material.foreground: theme.headerText
            highlighted: true
            visible: backendObject.hasWorkspace
            enabled: backendObject.hasWorkspace
            background: Rectangle {
                implicitWidth: 190
                implicitHeight: 42
                radius: 8
                color: exportButton.down
                       ? theme.exportButtonPressed : theme.exportButton
            }
            onClicked: exportRequested()
        }

    }
}
