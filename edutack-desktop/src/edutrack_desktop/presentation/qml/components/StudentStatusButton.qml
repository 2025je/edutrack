import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Button {
    id: root
    property bool active: false
    property var theme
    signal stateChangeRequested(bool isActive)
    property color stateColor: active ? root.theme.success : root.theme.secondaryText
    Layout.preferredWidth: 80
    Layout.minimumWidth: 80
    Layout.maximumWidth: 80
    Layout.preferredHeight: 34
    Layout.maximumHeight: 34
    text: active ? "Activo" : "Inactivo"
    font.family: "Roboto"
    font.pixelSize: 12
    flat: true
    Material.foreground: stateColor
    contentItem: Label {
        text: root.text
        color: root.stateColor
        font: root.font
        horizontalAlignment: Text.AlignRight
        verticalAlignment: Text.AlignVCenter
    }
    background: Item {}
    onClicked: root.stateChangeRequested(!root.active)
}
