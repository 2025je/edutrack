import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "discardChangesDialog"
    property var theme
    signal discardConfirmed()

    modal: true
    title: "Cambios sin guardar"
    standardButtons: Dialog.NoButton
    width: Math.min(440, parent ? parent.width - 32 : 440)
    anchors.centerIn: Overlay.overlay

    contentItem: ColumnLayout {
        spacing: 16

        Label {
            Layout.fillWidth: true
            text: "Tienes cambios que todavía no se han guardado. "
                  + "¿Quieres descartarlos?"
            color: root.theme.primaryText
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.fillWidth: true

            Item {
                Layout.fillWidth: true
            }

            Button {
                objectName: "continueEditingButton"
                text: "Seguir editando"
                onClicked: root.close()
            }

            Button {
                objectName: "discardChangesButton"
                text: "Descartar cambios"
                highlighted: true
                onClicked: {
                    root.close()
                    root.discardConfirmed()
                }
            }
        }
    }
}
