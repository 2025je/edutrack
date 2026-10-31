pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "backupsPage"
    property var backendObject
    property var windowController
    property var theme
    property string operationMessage: ""
    property string pendingRestorePath: ""
    property bool pageReady: false

    color: theme.surface
    border.color: theme.outline

    function formatModifiedAt(value) {
        var date = new Date(value)
        if (!value || isNaN(date.getTime()))
            return "Fecha desconocida"
        return Qt.formatDateTime(date, "dd/MM/yyyy HH:mm")
    }

    function formatSize(bytes) {
        var value = Number(bytes || 0)
        if (value < 1024)
            return value + " B"
        if (value < 1024 * 1024)
            return (value / 1024).toFixed(1) + " KB"
        return (value / (1024 * 1024)).toFixed(1) + " MB"
    }

    Dialog {
        id: restoreConfirmation
        title: "Restaurar respaldo"
        modal: true
        standardButtons: Dialog.NoButton
        anchors.centerIn: parent
        width: Math.min(440, root.width - 40)
        background: Rectangle {
            color: root.theme.surface
            border.color: root.theme.outline
        }

        contentItem: ColumnLayout {
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: "Se reemplazarán los datos de la sede abierta por el contenido del respaldo seleccionado."
                color: root.theme.primaryText
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: "Antes de restaurar se verificará el archivo y se creará un punto de recuperación de la base actual."
                color: root.theme.secondaryText
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: root.pendingRestorePath
                color: root.theme.secondaryText
                elide: Text.ElideMiddle
                wrapMode: Text.Wrap
            }
        }

        footer: RowLayout {
            Item { Layout.fillWidth: true }
            Button {
                text: "Cancelar"
                onClicked: restoreConfirmation.reject()
            }
            Button {
                text: "Restaurar"
                highlighted: true
                onClicked: restoreConfirmation.accept()
            }
        }

        onAccepted: {
            if (!root.backendObject.restoreBackup(root.pendingRestorePath))
                root.operationMessage = root.backendObject.errorMessage
            root.pendingRestorePath = ""
        }
        onRejected: root.pendingRestorePath = ""
    }

    Connections {
        target: root.backendObject

        function onBackupDirectoryChanged() {
            root.operationMessage = ""
            if (root.visible && root.backendObject.hasWorkspace
                    && !root.backendObject.isBusy)
                root.backendObject.refreshBackups()
        }

        function onBackupOperationFinished(operation, succeeded, result, error) {
            if (!succeeded) {
                root.operationMessage = error
                if (operation !== "backup_list")
                    root.backendObject.refreshBackups()
                return
            }
            if (operation === "backup_list") {
                if (root.operationMessage.length === 0)
                    root.operationMessage = "Lista de respaldos actualizada."
            } else if (operation === "backup_create") {
                root.operationMessage = "Respaldo verificado: " + result.path
                root.backendObject.refreshBackups()
            } else if (operation === "backup_restore") {
                root.operationMessage = "Restauración completada. Punto de recuperación: "
                        + result.recovery_backup
                root.backendObject.refreshBackups()
            }
        }
    }

    Component.onCompleted: {
        pageReady = true
        backendObject.refreshBackups()
    }
    onVisibleChanged: {
        if (pageReady && visible && backendObject.hasWorkspace
                && !backendObject.isBusy)
            backendObject.refreshBackups()
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: 20
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Label {
                    text: "Respaldos y recuperación"
                    color: root.theme.primaryText
                    font.family: "Roboto"
                    font.pixelSize: 24
                    font.bold: true
                }
                Label {
                    Layout.fillWidth: true
                    text: "Los respaldos se guardan junto a la base de datos, en la carpeta backups. Cada copia se verifica y nunca sobrescribe otra."
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                }
                Label {
                    Layout.fillWidth: true
                    text: root.backendObject.backupDirectory
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                    font.pixelSize: 11
                    wrapMode: Text.WrapAnywhere
                }
            }

            RowLayout {
                Layout.fillWidth: true

                Button {
                    text: "Crear respaldo"
                    enabled: !root.backendObject.isBusy
                    highlighted: true
                    onClicked: {
                        root.operationMessage = ""
                        if (!root.backendObject.createBackup())
                            root.operationMessage = root.backendObject.errorMessage
                    }
                }
                Button {
                    text: "Actualizar lista"
                    enabled: !root.backendObject.isBusy
                    onClicked: {
                        root.operationMessage = ""
                        if (!root.backendObject.refreshBackups())
                            root.operationMessage = root.backendObject.errorMessage
                    }
                }
                Item { Layout.fillWidth: true }
                BusyIndicator {
                    running: root.backendObject.isBusy
                    visible: running
                    implicitWidth: 32
                    implicitHeight: 32
                }
                Label {
                    visible: root.backendObject.isBusy
                    text: root.backendObject.activityMessage
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                    font.pixelSize: 11
                }
            }

            Label {
                Layout.fillWidth: true
                visible: root.operationMessage.length > 0
                text: root.operationMessage
                color: root.theme.accent
                font.family: "Roboto"
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                visible: root.backendObject.backupItems.length === 0
                         && !root.backendObject.isBusy
                text: "Todavía no hay respaldos en esta sede."
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 13
            }

            Repeater {
                model: root.backendObject.backupItems

                delegate: Rectangle {
                    id: backupRow
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: backupRowLayout.implicitHeight + 24
                    radius: 8
                    color: root.theme.raisedSurface
                    border.color: backupRow.modelData.valid
                                  ? root.theme.outline : root.theme.error

                    RowLayout {
                        id: backupRowLayout
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 12

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3

                            Label {
                                Layout.fillWidth: true
                                text: backupRow.modelData.name
                                color: root.theme.primaryText
                                font.family: "Roboto"
                                font.pixelSize: 13
                                font.bold: true
                                elide: Text.ElideMiddle
                            }
                            Label {
                                Layout.fillWidth: true
                                text: "Modificado: "
                                      + root.formatModifiedAt(
                                            backupRow.modelData.modified_at
                                        )
                                      + " · "
                                      + root.formatSize(backupRow.modelData.size_bytes)
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                text: backupRow.modelData.valid
                                      ? (backupRow.modelData.compatible
                                         ? "Integridad verificada · sede compatible"
                                         : backupRow.modelData.message)
                                      : backupRow.modelData.message
                                color: backupRow.modelData.valid
                                       && backupRow.modelData.compatible
                                       ? root.theme.success : root.theme.error
                                font.family: "Roboto"
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                        }

                        Button {
                            text: "Restaurar"
                            enabled: backupRow.modelData.valid
                                     && backupRow.modelData.compatible
                                     && !root.backendObject.isBusy
                            onClicked: {
                                root.pendingRestorePath = backupRow.modelData.path
                                restoreConfirmation.open()
                            }
                        }
                    }
                }
            }
        }
    }
}
