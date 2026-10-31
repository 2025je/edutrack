import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Popup {
    id: root
    objectName: "databaseSavingOverlay"
    property var backendObject
    property var theme
    property bool forceVisible: false
    property bool watchBackendActivity: true
    property string forcedMessage: ""
    readonly property bool overlayActive: root.forceVisible
                                          || (root.watchBackendActivity
                                              && root.backendObject
                                              && root.backendObject.isBusy)

    modal: true
    dim: true
    Overlay.modal: Rectangle {
        color: "#B30B1420"
    }
    focus: true
    width: Overlay.overlay ? Overlay.overlay.width : 0
    height: Overlay.overlay ? Overlay.overlay.height : 0
    padding: 0
    anchors.centerIn: Overlay.overlay
    closePolicy: Popup.NoAutoClose
    visible: root.overlayActive

    background: Item {}

    contentItem: Item {
        Rectangle {
            width: 400
            height: 124
            anchors.centerIn: parent
            radius: 14
            color: root.theme.surface
            border.color: root.theme.accent
            border.width: 2

            RowLayout {
                anchors.fill: parent
                anchors.margins: 22
                spacing: 16

                BusyIndicator {
                    Layout.preferredWidth: 42
                    Layout.preferredHeight: 42
                    running: root.overlayActive
                }

                Label {
                    Layout.fillWidth: true
                    text: root.forceVisible
                          ? root.forcedMessage
                          : root.backendObject
                            ? root.backendObject.activityMessage
                            : ""
                    color: root.theme.primaryText
                    font.family: "Roboto"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                }
            }
        }
    }
}
