import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "../components"

Flickable {
    id: campusSetupFlick
    property var backendObject
    property var windowController
    property var theme
    property real statusBarHeight: 38
    property alias campusName: newCampusNameInput.text
    property alias campusAddress: newCampusAddressInput.text
    property string pendingCampusPath: ""
    property string pendingCampusName: ""
    signal importRequested()
    signal openLocalDatabaseRequested()
    signal createDatabaseRequested()
    anchors.fill: parent
    anchors.margins: 20
    anchors.bottomMargin: statusBarHeight + 32
    visible: !backendObject.hasWorkspace || windowController.creatingCampus
    clip: true
    contentWidth: width
    contentHeight: campusSetupContent.height
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AlwaysOn
        active: true
    }
    ColumnLayout {
        id: campusSetupContent
        width: Math.min(campusSetupFlick.width, 560)
        height: implicitHeight
        x: Math.max(0, (campusSetupFlick.width - width) / 2)
            spacing: 12
            Label {
                Layout.fillWidth: true
                text: windowController.creatingCampus
                      ? "Crear una sede nueva"
                      : "Prepara tu sede"
                horizontalAlignment: Text.AlignHCenter
                color: windowController.primaryTextColor
                font.pixelSize: 25
                font.bold: true
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: windowController.creatingCampus
                      ? "Ingresa los datos básicos y elige dónde guardar la base SQLite."
                      : "Elige una sede guardada, importa un paquete o crea una nueva sin conexión."
                horizontalAlignment: Text.AlignHCenter
                color: windowController.secondaryTextColor
                font.pixelSize: 15
                wrapMode: Text.Wrap
            }
            GridLayout {
                Layout.fillWidth: true
                visible: !windowController.creatingCampus
                columns: 2
                columnSpacing: 12
                rowSpacing: 12
                Button {
                    id: importCampusTile
                    Layout.fillWidth: true
                    Layout.preferredHeight: 108
                    text: "Importar paquete"
                    Material.foreground: windowController.primaryTextColor
                    contentItem: ColumnLayout {
                        spacing: 7
                        MaterialSymbol {
                            Layout.alignment: Qt.AlignHCenter
                            symbolName: "folder_open"
                            symbolSize: 28
                            symbolColor: windowController.accentTextColor
                        }
                        Label {
                            Layout.fillWidth: true
                            text: importCampusTile.text
                            horizontalAlignment: Text.AlignHCenter
                            color: windowController.primaryTextColor
                            font.bold: true
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "Desde un paquete EduTrack"
                            horizontalAlignment: Text.AlignHCenter
                            color: windowController.secondaryTextColor
                            font.pixelSize: 12
                        }
                    }
                    background: Rectangle {
                        radius: 12
                        color: importCampusTile.down
                               ? windowController.accentSurfaceColor
                               : importCampusTile.hovered
                                 ? windowController.nestedSurfaceColor
                                 : windowController.surfaceColor
                        border.color: importCampusTile.hovered
                                     ? windowController.accentTextColor
                                     : windowController.borderColor
                    }
                    onClicked: campusSetupFlick.importRequested()
                }
                Button {
                    id: openDatabaseTile
                    Layout.fillWidth: true
                    Layout.preferredHeight: 108
                    text: "Abrir base local"
                    Material.foreground: windowController.primaryTextColor
                    contentItem: ColumnLayout {
                        spacing: 7
                        MaterialSymbol {
                            Layout.alignment: Qt.AlignHCenter
                            symbolName: "folder_open"
                            symbolSize: 28
                            symbolColor: windowController.accentTextColor
                        }
                        Label {
                            Layout.fillWidth: true
                            text: openDatabaseTile.text
                            horizontalAlignment: Text.AlignHCenter
                            color: windowController.primaryTextColor
                            font.bold: true
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "Selecciona un archivo SQLite"
                            horizontalAlignment: Text.AlignHCenter
                            color: windowController.secondaryTextColor
                            font.pixelSize: 12
                        }
                    }
                    background: Rectangle {
                        radius: 12
                        color: openDatabaseTile.down
                               ? windowController.accentSurfaceColor
                               : openDatabaseTile.hovered
                                 ? windowController.nestedSurfaceColor
                                 : windowController.surfaceColor
                        border.color: openDatabaseTile.hovered
                                     ? windowController.accentTextColor
                                     : windowController.borderColor
                    }
                    onClicked: campusSetupFlick.openLocalDatabaseRequested()
                }
                Button {
                    id: createCampusTile
                    Layout.columnSpan: 2
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 280
                    Layout.preferredHeight: 88
                    text: "Crear una sede nueva"
                    Material.foreground: windowController.primaryTextColor
                    contentItem: RowLayout {
                        spacing: 12
                        MaterialSymbol {
                            symbolName: "add"
                            symbolSize: 28
                            symbolColor: windowController.accentTextColor
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Label {
                                Layout.fillWidth: true
                                text: createCampusTile.text
                                color: windowController.primaryTextColor
                                font.bold: true
                            }
                            Label {
                                Layout.fillWidth: true
                                text: "Configura una sede sin conexión"
                                color: windowController.secondaryTextColor
                                font.pixelSize: 12
                            }
                        }
                        MaterialSymbol {
                            symbolName: "chevron_right"
                            symbolSize: 20
                            symbolColor: windowController.secondaryTextColor
                        }
                    }
                    background: Rectangle {
                        radius: 12
                        color: createCampusTile.down
                               ? windowController.accentSurfaceColor
                               : createCampusTile.hovered
                                 ? windowController.nestedSurfaceColor
                                 : windowController.surfaceColor
                        border.color: createCampusTile.hovered
                                     ? windowController.accentTextColor
                                     : windowController.borderColor
                    }
                    onClicked: {
                        newCampusNameInput.text = ""
                        newCampusAddressInput.text = ""
                        windowController.creatingCampus = true
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                visible: !windowController.creatingCampus && backendObject.campuses.length > 0
                text: "Sedes guardadas"
                horizontalAlignment: Text.AlignHCenter
                color: windowController.primaryTextColor
                font.pixelSize: 16
                font.bold: true
            }
            GridView {
                id: savedCampusesGrid
                objectName: "savedCampusesGrid"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.ceil(backendObject.campuses.length / 2) * 96
                visible: !windowController.creatingCampus && backendObject.campuses.length > 0
                cellWidth: 280
                cellHeight: 96
                interactive: false
                model: backendObject.campuses
                delegate: Item {
                    id: savedCampusTile
                    required property var modelData
                    required property int index
                    width: savedCampusesGrid.cellWidth - 10
                    height: savedCampusesGrid.cellHeight - 8
                    objectName: "savedCampusTile_" + index

                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: openCampusButton.down || removeCampusButton.down
                               ? windowController.accentSurfaceColor
                               : openCampusButton.hovered
                                 || removeCampusButton.hovered
                                 ? windowController.nestedSurfaceColor
                                 : windowController.surfaceColor
                        border.color: openCampusButton.visualFocus
                                      || openCampusButton.hovered
                                      || removeCampusButton.hovered
                                      ? windowController.accentTextColor
                                      : windowController.borderColor
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 2

                        Button {
                            id: openCampusButton
                            objectName: "savedCampusOpenButton_"
                                          + savedCampusTile.index
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: savedCampusTile.modelData.campus_name
                            Material.foreground: windowController.primaryTextColor
                            background: Item {}
                            contentItem: RowLayout {
                                spacing: 10
                                MaterialSymbol {
                                    symbolName: "folder_open"
                                    symbolSize: 24
                                    symbolColor: windowController.accentTextColor
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: openCampusButton.text
                                    color: windowController.primaryTextColor
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                MaterialSymbol {
                                    symbolName: "chevron_right"
                                    symbolSize: 20
                                    symbolColor: windowController.secondaryTextColor
                                }
                            }
                            onClicked: {
                                if (backendObject.switchCampus(
                                        savedCampusTile.modelData.path
                                    )) {
                                    windowController.creatingCampus = false
                                }
                            }
                        }
                        ToolButton {
                            id: removeCampusButton
                            objectName: "savedCampusRemoveButton_"
                                          + savedCampusTile.index
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            Accessible.name: "Quitar "
                                             + savedCampusTile.modelData.campus_name
                                             + " de la lista"
                            ToolTip.visible: hovered
                            ToolTip.text: backendObject.activeDatabasePath
                                          === savedCampusTile.modelData.path
                                          ? "Cierra primero la sede activa"
                                          : "Quitar de la lista"
                            contentItem: MaterialSymbol {
                                symbolName: "close"
                                symbolSize: 18
                                symbolColor: windowController.secondaryTextColor
                            }
                            background: Rectangle {
                                radius: 8
                                color: removeCampusButton.down
                                       ? windowController.accentSurfaceColor
                                       : removeCampusButton.hovered
                                         ? windowController.nestedSurfaceColor
                                         : "transparent"
                            }
                            onClicked: {
                                var campusPath =
                                        savedCampusTile.modelData.path
                                if (backendObject.activeDatabasePath
                                        === campusPath) {
                                    backendObject.removeCampusFromList(
                                        campusPath
                                    )
                                    return
                                }
                                campusSetupFlick.pendingCampusPath =
                                        campusPath
                                campusSetupFlick.pendingCampusName =
                                        savedCampusTile.modelData.campus_name
                                removeCampusDialog.open()
                            }
                        }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                visible: windowController.creatingCampus
                color: windowController.dividerColor
            }
            UppercaseTextField {
                id: newCampusNameInput
                Layout.fillWidth: true
                visible: windowController.creatingCampus
                placeholderText: "Nombre de la sede"
                maximumLength: 120
            }
            UppercaseTextField {
                id: newCampusAddressInput
                Layout.fillWidth: true
                visible: windowController.creatingCampus
                placeholderText: "Dirección (opcional)"
                maximumLength: 200
            }
            IconTextButton {
                id: createWorkspaceButton
                Layout.alignment: Qt.AlignHCenter
                visible: windowController.creatingCampus
                text: "Elegir ubicación y crear sede"
                symbolName: "add"
                symbolColor: theme.headerText
                Material.foreground: theme.headerText
                highlighted: true
                background: Rectangle {
                    implicitWidth: 250
                    implicitHeight: 44
                    radius: 8
                    color: createWorkspaceButton.down
                           ? theme.createButtonPressed : theme.createButton
                }
                onClicked: campusSetupFlick.createDatabaseRequested()
            }
            Button {
                Layout.alignment: Qt.AlignHCenter
                visible: windowController.creatingCampus
                text: backendObject.hasWorkspace
                      ? "Volver a la sede abierta"
                      : "Volver a opciones"
                flat: true
                onClicked: windowController.creatingCampus = false
            }
    }

    Dialog {
        id: removeCampusDialog
        objectName: "removeCampusDialog"
        title: "Quitar sede guardada"
        modal: true
        standardButtons: Dialog.NoButton
        anchors.centerIn: parent
        background: Rectangle {
            radius: 0
            color: windowController.surfaceColor
            border.color: windowController.borderColor
        }
        Label {
            text: "La sede \"%1\" se quitará de la lista. Su base SQLite y sus datos locales se conservarán."
                  .arg(campusSetupFlick.pendingCampusName)
            wrapMode: Text.Wrap
            color: windowController.primaryTextColor
        }
        footer: RowLayout {
            spacing: 8
            Item {
                Layout.fillWidth: true
            }
            Button {
                objectName: "cancelRemoveCampusButton"
                text: "Cancelar"
                flat: true
                Material.foreground: windowController.secondaryTextColor
                onClicked: removeCampusDialog.reject()
            }
            Button {
                objectName: "confirmRemoveCampusButton"
                text: "Quitar de la lista"
                highlighted: true
                Material.foreground: theme.headerText
                onClicked: removeCampusDialog.accept()
            }
        }
        onAccepted: {
            backendObject.removeCampusFromList(
                campusSetupFlick.pendingCampusPath
            )
            campusSetupFlick.pendingCampusPath = ""
            campusSetupFlick.pendingCampusName = ""
        }
        onRejected: {
            campusSetupFlick.pendingCampusPath = ""
            campusSetupFlick.pendingCampusName = ""
        }
    }
}
