import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: closeButton
    objectName: "windowCloseButton"
    property var windowController
    property var theme
    signal closeRequested()

    Layout.preferredWidth: 36
    Layout.preferredHeight: 36
    flat: true
    ToolTip.visible: hovered
    ToolTip.text: "Cerrar ventana"
    background: Rectangle {
        radius: 0
        color: !closeButton.windowController
               ? "transparent"
               : closeButton.down || closeButton.hovered
                 ? closeButton.windowController.errorColor
                 : "transparent"
    }
    contentItem: Item {
        Rectangle {
            width: 15
            height: 1.5
            anchors.centerIn: parent
            rotation: 45
            color: !closeButton.windowController || !closeButton.theme
                   ? "transparent"
                   : closeButton.hovered
                   ? closeButton.windowController.darkMode
                     ? closeButton.theme.background : "#ffffff"
                   : closeButton.theme.headerText
        }

        Rectangle {
            width: 15
            height: 1.5
            anchors.centerIn: parent
            rotation: -45
            color: !closeButton.windowController || !closeButton.theme
                   ? "transparent"
                   : closeButton.hovered
                   ? closeButton.windowController.darkMode
                     ? closeButton.theme.background : "#ffffff"
                   : closeButton.theme.headerText
        }
    }
    onClicked: closeRequested()
}
