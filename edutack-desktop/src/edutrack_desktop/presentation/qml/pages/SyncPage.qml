pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "syncPage"
    property var backendObject
    property var windowController
    property var theme
    property var previewData: ({})
    property bool previewVisible: false
    property string operationMessage: ""
    readonly property var workspaceInfo: backendObject
                                         ? backendObject.syncWorkspaceInfo : ({})
    readonly property var previewItems: previewData.items || []
    color: theme.surface
    border.color: theme.outline

    function formatTimestamp(value) {
        if (!value)
            return "Sin registros"
        return String(value).replace("T", " ").replace("+00:00", " UTC")
    }

    FileDialog {
        id: exportDialog
        title: "Guardar paquete de sincronización"
        fileMode: FileDialog.SaveFile
        acceptLabel: "Guardar"
        rejectLabel: "Cancelar"
        currentFile: "edutrack-sincronizacion.edutrack"
        nameFilters: ["EduTrack (*.edutrack)"]
        onAccepted: {
            if (!root.backendObject.exportPackageAsync(selectedFile.toString()))
                root.operationMessage = root.backendObject.errorMessage
        }
    }

    FileDialog {
        id: importDialog
        title: "Seleccionar paquete actualizado de EduTrack Web"
        fileMode: FileDialog.OpenFile
        acceptLabel: "Validar paquete"
        rejectLabel: "Cancelar"
        nameFilters: ["EduTrack (*.edutrack *.zip)", "Todos los archivos (*)"]
        onAccepted: {
            root.previewVisible = false
            root.previewData = ({})
            root.operationMessage = "Validando el paquete seleccionado…"
            if (!root.backendObject.preparePackageImport(selectedFile.toString()))
                root.operationMessage = root.backendObject.errorMessage
        }
    }

    Connections {
        target: root.backendObject

        function onSyncPreviewFinished(succeeded, result, error) {
            if (!succeeded) {
                root.previewVisible = false
                root.operationMessage = error
                return
            }
            root.previewData = result
            root.previewVisible = true
            root.operationMessage = result.can_import
                    ? "Vista previa lista. La base local aún no se ha modificado."
                    : "Se detectaron conflictos. El paquete no se puede importar todavía."
        }

        function onSyncImportFinished(succeeded, result, error) {
            root.previewVisible = false
            root.previewData = ({})
            root.operationMessage = succeeded
                    ? "Importación confirmada. Respaldo: " + result.backup_path
                    : error
        }

        function onSyncExportFinished(succeeded, message) {
            root.operationMessage = message
        }
    }

    Component.onCompleted: backendObject.refreshSyncHistory()

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
                spacing: 3

                Label {
                    text: "Centro de sincronización"
                    color: root.theme.primaryText
                    font.family: "Roboto"
                    font.pixelSize: 24
                    font.bold: true
                }

                Label {
                    Layout.fillWidth: true
                    text: "Intercambio manual de paquetes con EduTrack Web. Exportar un archivo no significa que la sincronización esté completa."
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 126
                radius: 10
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: root.workspaceInfo.campus_name || "Sede local"
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 17
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        Label {
                            text: "Espacio: "
                                  + (root.workspaceInfo.workspace_id || "sin identificador")
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 12
                            elide: Text.ElideMiddle
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 4
                        columnSpacing: 12
                        rowSpacing: 5

                        Repeater {
                            model: [
                                { label: "Estudiantes", value: root.workspaceInfo.students || 0 },
                                { label: "Matrículas", value: root.workspaceInfo.enrollments || 0 },
                                { label: "Cursos", value: root.workspaceInfo.courses || 0 },
                                { label: "Promotores", value: root.workspaceInfo.promoters || 0 }
                            ]

                            delegate: ColumnLayout {
                                id: syncCountDelegate
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 1

                                Label {
                                    text: String(syncCountDelegate.modelData.value)
                                    color: root.theme.primaryText
                                    font.family: "Roboto"
                                    font.pixelSize: 18
                                    font.bold: true
                                }
                                Label {
                                    text: syncCountDelegate.modelData.label
                                    color: root.theme.secondaryText
                                    font.family: "Roboto"
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: "Última exportación: "
                                  + root.formatTimestamp(root.backendObject.lastSyncExportDate)
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "Última importación: "
                                  + root.formatTimestamp(root.backendObject.lastSyncImportDate)
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                radius: 10
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 18

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 7

                        Label {
                            text: "Exportar para EduTrack Web"
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 15
                            font.bold: true
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "Guarda un paquete local y cárgalo manualmente en EduTrack Web para iniciar el intercambio."
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                        Button {
                            text: "Preparar exportación"
                            highlighted: true
                            enabled: !root.backendObject.isBusy
                            onClicked: exportDialog.open()
                        }
                    }

                    Rectangle {
                        Layout.fillHeight: true
                        width: 1
                        color: root.theme.outline
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 7

                        Label {
                            text: "Importar paquete actualizado"
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 15
                            font.bold: true
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "Selecciona el paquete devuelto por la web. Se validará antes de mostrar los cambios."
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                        Button {
                            text: "Seleccionar paquete"
                            enabled: !root.backendObject.isBusy
                            onClicked: importDialog.open()
                        }
                    }
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

            Rectangle {
                Layout.fillWidth: true
                visible: root.previewVisible
                implicitHeight: previewLayout.implicitHeight + 24
                radius: 10
                color: root.theme.raisedSurface
                border.color: root.previewData.can_import
                              ? root.theme.outline : root.theme.error

                ColumnLayout {
                    id: previewLayout
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: "Vista previa · " + (root.previewData.campus_name || "")
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 16
                            font.bold: true
                        }
                        Label {
                            text: "Paquete " + (root.previewData.bundle_id || "")
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 11
                            elide: Text.ElideMiddle
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        text: "Nuevos: " + (root.previewData.new || 0)
                              + " · Actualizados: " + (root.previewData.updated || 0)
                              + " · Sin cambios: " + (root.previewData.unchanged || 0)
                              + " · Conflictos: " + (root.previewData.conflicts || 0)
                              + " · Requieren atención: " + (root.previewData.attention || 0)
                        color: root.theme.primaryText
                        font.family: "Roboto"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }

                    Label {
                        Layout.fillWidth: true
                        text: "Imágenes nuevas: " + (root.previewData.images_new || 0)
                              + " · Imágenes modificadas: "
                              + (root.previewData.images_changed || 0)
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 12
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: !root.previewData.can_import
                        text: "La importación está bloqueada para proteger los cambios locales. Resuelve los conflictos en EduTrack Web y vuelve a descargar el paquete."
                        color: root.theme.error
                        font.family: "Roboto"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(contentHeight, 150)
                        visible: root.previewItems.length > 0
                        clip: true
                        model: root.previewItems
                        delegate: RowLayout {
                            id: previewRow
                            required property var modelData
                            width: ListView.view.width
                            spacing: 8
                            Label {
                                Layout.preferredWidth: 100
                                text: previewRow.modelData.state + " · "
                                      + previewRow.modelData.kind
                                color: previewRow.modelData.state === "conflict"
                                       ? root.theme.error : root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 11
                            }
                            Label {
                                Layout.preferredWidth: 150
                                text: previewRow.modelData.label
                                color: root.theme.primaryText
                                font.family: "Roboto"
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                text: previewRow.modelData.message
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                        }
                    }

                    Label {
                        visible: (root.previewData.omitted_items || 0) > 0
                        text: "Se omitieron " + root.previewData.omitted_items
                              + " registros de la lista detallada."
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 11
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        Button {
                            text: "Cancelar"
                            enabled: !root.backendObject.isBusy
                            onClicked: {
                                root.backendObject.cancelPackageImport()
                                root.previewVisible = false
                                root.previewData = ({})
                                root.operationMessage = ""
                            }
                        }
                        Button {
                            text: "Confirmar importación"
                            highlighted: true
                            enabled: root.previewData.can_import
                                     && !root.backendObject.isBusy
                            onClicked: {
                                root.operationMessage = "Creando respaldo e importando…"
                                if (!root.backendObject.confirmPackageImport())
                                    root.operationMessage = root.backendObject.errorMessage
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 210
                radius: 10
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: "Historial de sincronización"
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 16
                            font.bold: true
                        }
                        Button {
                            text: "Actualizar"
                            enabled: !root.backendObject.isBusy
                            onClicked: root.backendObject.refreshSyncHistory()
                        }
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: root.backendObject.syncHistory
                        delegate: RowLayout {
                            id: historyRow
                            required property var modelData
                            width: ListView.view.width
                            spacing: 8
                            Label {
                                Layout.preferredWidth: 90
                                text: historyRow.modelData.operation === "import"
                                      ? "Importación" : "Exportación"
                                color: root.theme.primaryText
                                font.family: "Roboto"
                                font.pixelSize: 11
                            }
                            Label {
                                Layout.preferredWidth: 80
                                text: historyRow.modelData.status
                                color: historyRow.modelData.status === "success"
                                       ? root.theme.success : root.theme.error
                                font.family: "Roboto"
                                font.pixelSize: 11
                            }
                            Label {
                                Layout.fillWidth: true
                                text: root.formatTimestamp(historyRow.modelData.created_at)
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            Label {
                                Layout.preferredWidth: 140
                                text: JSON.stringify(
                                    historyRow.modelData.affected_counts || {}
                                )
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 10
                                elide: Text.ElideRight
                            }
                            Label {
                                Layout.preferredWidth: 150
                                text: "Paquete "
                                      + (historyRow.modelData.bundle_id || "sin ID")
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 10
                                elide: Text.ElideMiddle
                            }
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: root.backendObject.syncHistory.length === 0
                        text: "Todavía no hay operaciones registradas."
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 12
                    }
                }
            }
        }
    }
}
