import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Dialogs
import QtQuick.Layouts

Item {
    id: root
    property var backendObject
    property var windowController
    property var campusPage
    property var theme
    property string pendingPackagePath: ""
    property string pendingDatabasePath: ""
    property string pendingDatabaseAction: ""

    function openImportDialog() { openDialog.open() }
    function openCreateDatabaseDialog() {
        pendingDatabaseAction = "create"
        databasePathDialog.open()
    }
    function openLocalDatabaseDialog() { localDatabaseDialog.open() }
    function openExportDialog() { saveDialog.open() }
    function openCloseCampusDialog() { closeCampusDialog.open() }

    FileDialog {
        id: openDialog
        title: "Importar paquete de sede"
        fileMode: FileDialog.OpenFile
        acceptLabel: "Abrir"
        rejectLabel: "Cancelar"
        nameFilters: ["EduTrack (*.edutrack *.zip)", "Todos los archivos (*)"]
        onAccepted: {
            root.pendingPackagePath = selectedFile.toString()
            root.pendingDatabaseAction = "import"
            databasePathDialog.open()
        }
    }

    FileDialog {
        id: databasePathDialog
        title: root.pendingDatabaseAction === "create"
               ? "Guardar la base de datos de la nueva sede"
               : "Guardar la base de datos de la sede importada"
        fileMode: FileDialog.SaveFile
        acceptLabel: "Guardar"
        rejectLabel: "Cancelar"
        defaultSuffix: "sqlite3"
        nameFilters: ["Base de datos SQLite (*.sqlite3)"]
        onAccepted: {
            var databasePath = selectedFile.toString()
            var succeeded = false
            if (root.pendingDatabaseAction === "create") {
                succeeded = root.backendObject.createWorkspace(
                    root.campusPage.campusName,
                    root.campusPage.campusAddress,
                    databasePath
                )
            } else if (root.pendingDatabaseAction === "import") {
                if (root.backendObject.isRegisteredDatabase(databasePath)) {
                    root.pendingDatabasePath = databasePath
                    replaceImportDialog.open()
                } else {
                    succeeded = root.backendObject.openPackage(
                        root.pendingPackagePath,
                        databasePath
                    )
                }
            }
            if (succeeded) {
                root.windowController.creatingCampus = false
                root.pendingPackagePath = ""
                root.campusPage.campusName = ""
                root.campusPage.campusAddress = ""
            }
            root.pendingDatabaseAction = ""
        }
        onRejected: root.pendingDatabaseAction = ""
    }

    Dialog {
        id: replaceImportDialog
        title: "Actualizar los datos de esta sede"
        modal: true
        standardButtons: Dialog.NoButton
        anchors.centerIn: parent
        background: Rectangle {
            radius: 0
            color: root.windowController.surfaceColor
            border.color: root.windowController.borderColor
        }
        Label {
            text: "Se reemplazarán los datos locales de la sede elegida con el contenido del paquete. Continúa solo si ya importaste y confirmaste la sincronización en la web."
            wrapMode: Text.Wrap
        }
        footer: RowLayout {
            spacing: 8
            Item {
                Layout.fillWidth: true
            }
            Button {
                text: "No"
                flat: true
                Material.foreground: root.windowController.secondaryTextColor
                onClicked: replaceImportDialog.reject()
            }
            Button {
                text: "Sí"
                highlighted: true
                Material.foreground: root.theme.headerText
                onClicked: replaceImportDialog.accept()
            }
        }
        onAccepted: {
            if (root.backendObject.openPackage(
                    root.pendingPackagePath,
                    root.pendingDatabasePath,
                    true
                )) {
                root.windowController.creatingCampus = false
                root.campusPage.campusName = ""
                root.campusPage.campusAddress = ""
            }
            root.pendingPackagePath = ""
            root.pendingDatabasePath = ""
        }
        onRejected: {
            root.pendingPackagePath = ""
            root.pendingDatabasePath = ""
        }
    }

    Dialog {
        id: closeCampusDialog
        objectName: "closeCampusDialog"
        title: "Cerrar sede activa"
        modal: true
        standardButtons: Dialog.NoButton
        anchors.centerIn: parent
        onAboutToShow: modal = true
        onAboutToHide: modal = false
        background: Rectangle {
            radius: 0
            color: root.windowController.surfaceColor
            border.color: root.windowController.borderColor
        }
        Label {
            text: "La sede se cerrará en Desktop, pero su base de datos y sus datos se conservarán. Podrás volver a abrirla desde el selector de sedes."
            wrapMode: Text.Wrap
        }
        footer: RowLayout {
            spacing: 8
            Item {
                Layout.fillWidth: true
            }
            Button {
                objectName: "cancelCloseCampusButton"
                text: "No"
                flat: true
                Material.foreground: root.windowController.secondaryTextColor
                onClicked: closeCampusDialog.reject()
            }
            Button {
                objectName: "confirmCloseCampusButton"
                text: "Sí"
                highlighted: true
                Material.foreground: root.theme.headerText
                onClicked: {
                    closeCampusDialog.modal = false
                    closeCampusDialog.accept()
                }
            }
        }
        onAccepted: {
            if (root.backendObject.closeCampus())
                root.windowController.creatingCampus = false
        }
    }

    FileDialog {
        id: localDatabaseDialog
        title: "Abrir una base de datos de sede"
        fileMode: FileDialog.OpenFile
        acceptLabel: "Abrir"
        rejectLabel: "Cancelar"
        nameFilters: ["Base de datos SQLite (*.sqlite3 *.db)", "Todos los archivos (*)"]
        onAccepted: {
            if (root.backendObject.openLocalDatabase(selectedFile.toString()))
                root.windowController.creatingCampus = false
        }
    }

    FileDialog {
        id: saveDialog
        title: "Guardar archivo de sincronización"
        fileMode: FileDialog.SaveFile
        acceptLabel: "Guardar"
        rejectLabel: "Cancelar"
        defaultSuffix: "edutrack"
        nameFilters: ["EduTrack (*.edutrack)"]
        onAccepted: root.backendObject.exportPackageAsync(selectedFile.toString())
    }

}
