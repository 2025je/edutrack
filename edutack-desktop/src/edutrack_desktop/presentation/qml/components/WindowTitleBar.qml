import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import QtQuick.Window
import "."

Rectangle {
    id: windowTitleBar
    property var windowController
    property var backendObject
    property var theme
    signal closeCampusRequested()
    signal darkModeToggleRequested()
    signal exportRequested()
    signal minimizeRequested()
    signal maximizeRequested()
    signal closeRequested()
    Layout.fillWidth: true
    Layout.preferredHeight: 88
    radius: 0
    color: Material.primary
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onPressed: windowController.startSystemMove()
        onDoubleClicked: maximizeRequested()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 20
        spacing: 18
        z: 1

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

        Button {
            id: minimizeWindowButton
            Layout.preferredWidth: 36
            Layout.preferredHeight: 36
            flat: true
            ToolTip.visible: hovered
            ToolTip.text: "Minimizar"
            background: Rectangle {
                radius: 0
                color: minimizeWindowButton.down
                       ? Qt.darker(Material.primary, 1.25)
                       : minimizeWindowButton.hovered
                         ? Qt.darker(Material.primary, 1.12)
                         : "transparent"
            }
            contentItem: Item {
                Rectangle {
                    width: 12
                    height: 1.5
                    anchors.centerIn: parent
                    color: theme.headerText
                }
            }
            onClicked: minimizeRequested()
        }

        Button {
            id: maximizeWindowButton
            Layout.preferredWidth: 36
            Layout.preferredHeight: 36
            flat: true
            ToolTip.visible: hovered
            ToolTip.text: windowController.visibility === Window.Maximized
                          ? "Restaurar" : "Maximizar"
            background: Rectangle {
                radius: 0
                color: maximizeWindowButton.down
                       ? Qt.darker(Material.primary, 1.25)
                       : maximizeWindowButton.hovered
                         ? Qt.darker(Material.primary, 1.12)
                         : "transparent"
            }
            contentItem: Item {
                Rectangle {
                    visible: windowController.visibility !== Window.Maximized
                    width: 12
                    height: 12
                    anchors.centerIn: parent
                    color: "transparent"
                    border.color: theme.headerText
                    border.width: 1.5
                }

                Item {
                    visible: windowController.visibility === Window.Maximized
                    width: 18
                    height: 18
                    anchors.centerIn: parent

                    Rectangle {
                        x: 2
                        y: 5
                        width: 11
                        height: 10
                        color: Material.primary
                        border.color: theme.headerText
                        border.width: 1.2
                    }

                    Rectangle {
                        x: 6
                        y: 3
                        width: 11
                        height: 10
                        color: Material.primary
                        border.color: theme.headerText
                        border.width: 1.2
                    }
                }
            }
            onClicked: maximizeRequested()
        }

        WindowCloseButton {
            windowController: windowTitleBar.windowController
            theme: windowTitleBar.theme
            onCloseRequested: windowTitleBar.closeRequested()
        }
    }
}
