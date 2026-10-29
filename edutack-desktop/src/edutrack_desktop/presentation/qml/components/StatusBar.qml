import QtQuick
import QtQuick.Controls

Rectangle {
    id: statusBar
    property var theme
    property string message: ""
    objectName: "statusBar"
    anchors.left: parent.left
    anchors.leftMargin: 16
    anchors.right: parent.right
    anchors.rightMargin: 16
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 16
    height: 38
    z: 1
    property bool successful: statusMessage.text.indexOf("correctamente") >= 0
                              || statusMessage.text.indexOf("guardado") >= 0
                              || statusMessage.text.indexOf("abierta.") >= 0
    color: statusMessage.text.length === 0
           ? theme.surface
           : successful ? theme.successSurface : theme.errorSurface
    border.color: theme.outline

    Label {
        id: statusMessage
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        text: message
        color: statusMessage.text.length === 0
               ? theme.secondaryText
               : statusBar.successful ? theme.success : theme.error
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        font.family: "Roboto"
        font.pixelSize: 13
    }
}
