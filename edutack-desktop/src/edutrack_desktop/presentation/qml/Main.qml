import QtQuick
import QtQuick.Controls.Material
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: appWindow
    width: 1280
    height: 740
    minimumWidth: 980
    minimumHeight: 620
    visible: true
    title: "EduTrack Desktop"
    flags: Qt.Window | Qt.FramelessWindowHint
    property bool darkMode: false
    readonly property color pageBackgroundColor: appTheme.background
    readonly property color surfaceColor: appTheme.surface
    readonly property color nestedSurfaceColor: appTheme.raisedSurface
    readonly property color borderColor: appTheme.outline
    readonly property color dividerColor: appTheme.divider
    readonly property color primaryTextColor: appTheme.primaryText
    readonly property color secondaryTextColor: appTheme.secondaryText
    readonly property color successColor: appTheme.success
    readonly property color successSurfaceColor: appTheme.successSurface
    readonly property color errorColor: appTheme.error
    readonly property color errorSurfaceColor: appTheme.errorSurface
    readonly property color accentSurfaceColor: appTheme.accentSurface
    readonly property color accentTextColor: appTheme.accent
    color: appTheme.background
    Material.theme: appTheme.controlsTheme
    Material.primary: appTheme.primary
    Material.accent: Material.Teal
    property string pendingPackagePath: ""
    property string pendingDatabasePath: ""
    property string pendingDatabaseAction: ""
    property var desktopBackend: null
    property bool restoringSession: false
    property bool sessionTrackingEnabled: false
    property string sessionSnapshot: sessionTrackingEnabled
                                         ? JSON.stringify(collectSessionState()) : ""
    property bool creatingCampus: false
    property string selectedWorkspaceSection: "Resumen"
    property bool startupComplete: false
    property string editingStudentId: ""
    property int studentPageIndex: 0
    property int studentPageSize: 50
    property int matchingStudentCount: 0
    property var visibleStudentRows: []
    property string statusMessageText: ""

    AppTheme {
        id: appTheme
        darkMode: appWindow.darkMode
    }

    function activeCampusPath() {
        var index = backend.activeCampusIndex
        var campuses = backend.campuses
        return index >= 0 && index < campuses.length ? campuses[index].path : ""
    }

    function restoreSessionState() {
        var serialized = sessionStore.loadState()
        var state = {}
        if (serialized) {
            try {
                state = JSON.parse(serialized)
            } catch (error) {
                console.error("No se pudo restaurar el estado de sesión:", error)
            }
        } else if (sessionStore.errorMessage) {
            console.error("No se pudo leer el estado de sesión:", sessionStore.errorMessage)
        }
        if (!state || state.version !== 1)
            state = {}

        appWindow.restoringSession = true
        appWindow.darkMode = state.darkMode === true
        if (state.window && typeof state.window === "object") {
            if (isFinite(Number(state.window.width)))
                appWindow.width = Math.max(appWindow.minimumWidth, Number(state.window.width))
            if (isFinite(Number(state.window.height)))
                appWindow.height = Math.max(appWindow.minimumHeight, Number(state.window.height))
            if (isFinite(Number(state.window.x)))
                appWindow.x = Number(state.window.x)
            if (isFinite(Number(state.window.y)))
                appWindow.y = Number(state.window.y)
        }

        if (state.campusPath === appWindow.activeCampusPath()) {
            var campusForm = state.campusForm || {}
            newCampusNameInput.text = campusForm.name || ""
            newCampusAddressInput.text = campusForm.address || ""
            appWindow.creatingCampus = state.creatingCampus === true
        }

        appWindow.restoringSession = false
        appWindow.sessionTrackingEnabled = true
    }

    function collectSessionState() {
        return {
            version: 1,
            campusPath: appWindow.activeCampusPath(),
            darkMode: appWindow.darkMode,
            window: {
                x: appWindow.x,
                y: appWindow.y,
                width: appWindow.width,
                height: appWindow.height
            },
            creatingCampus: appWindow.creatingCampus,
            campusForm: {
                name: newCampusNameInput.text,
                address: newCampusAddressInput.text
            }
        }
    }

    function persistSessionState() {
        if (!sessionStore.saveState(JSON.stringify(appWindow.collectSessionState())))
            console.error("No se pudo guardar el estado de sesión:", sessionStore.errorMessage)
    }

    function showStatusMessage(message) {
        statusMessageTimer.stop()
        appWindow.statusMessageText = message || ""
        if (appWindow.statusMessageText.length > 0)
            statusMessageTimer.start()
    }

    function refreshStudentPage() {
        appWindow.matchingStudentCount = backend.matchingStudentCount(studentSearch.text)
        var pageCount = Math.max(
            1,
            Math.ceil(appWindow.matchingStudentCount / appWindow.studentPageSize)
        )
        appWindow.studentPageIndex = Math.min(
            appWindow.studentPageIndex,
            pageCount - 1
        )
        appWindow.visibleStudentRows = backend.studentPage(
            studentSearch.text,
            appWindow.studentPageIndex,
            appWindow.studentPageSize
        )
    }

    function centerWindowOnScreen() {
        appWindow.x = Math.round(
            Screen.virtualX + (Screen.width - appWindow.width) / 2
        )
        appWindow.y = Math.round(
            Screen.virtualY + (Screen.height - appWindow.height) / 2
        )
    }

    function toggleMaximized() {
        if (appWindow.visibility === Window.Maximized) {
            appWindow.visibility = Window.Windowed
            Qt.callLater(function() { appWindow.centerWindowOnScreen() })
            return
        }

        appWindow.centerWindowOnScreen()
        appWindow.visibility = Window.Maximized
    }

    Component.onCompleted: {
        appWindow.showStatusMessage(backend.errorMessage)
        startupTimer.start()
    }
    onClosing: appWindow.persistSessionState()
    onSessionSnapshotChanged: {
        if (appWindow.sessionTrackingEnabled && !appWindow.restoringSession)
            sessionSaveTimer.restart()
    }

    Connections {
        target: backend
        function onDataChanged() {
            appWindow.refreshStudentPage()
        }
        function onErrorChanged() {
            appWindow.showStatusMessage(backend.errorMessage)
        }
    }

    Timer {
        id: statusMessageTimer
        interval: 5000
        repeat: false
        onTriggered: appWindow.statusMessageText = ""
    }

    Timer {
        id: sessionSaveTimer
        objectName: "sessionSaveTimer"
        interval: 300
        repeat: false
        onTriggered: appWindow.persistSessionState()
    }

    Timer {
        id: startupTimer
        interval: 150
        repeat: false
        onTriggered: {
            appWindow.restoreSessionState()
            appWindow.refreshStudentPage()
            appWindow.startupComplete = true
        }
    }

    FileDialog {
        id: openDialog
        title: "Importar paquete de sede"
        fileMode: FileDialog.OpenFile
        nameFilters: ["EduTrack (*.edutrack *.zip)", "Todos los archivos (*)"]
        onAccepted: {
            appWindow.pendingPackagePath = selectedFile.toString()
            appWindow.pendingDatabaseAction = "import"
            databasePathDialog.open()
        }
    }

    FileDialog {
        id: databasePathDialog
        title: appWindow.pendingDatabaseAction === "create"
               ? "Guardar la base de datos de la nueva sede"
               : "Guardar la base de datos de la sede importada"
        fileMode: FileDialog.SaveFile
        currentFile: appWindow.pendingDatabaseAction === "create"
                     ? backend.suggestedDatabaseFileName(newCampusNameInput.text)
                     : "edutrack-sede-importada.sqlite3"
        nameFilters: ["Base de datos SQLite (*.sqlite3)"]
        onAccepted: {
            var databasePath = selectedFile.toString()
            var succeeded = false
            if (appWindow.pendingDatabaseAction === "create") {
                succeeded = backend.createWorkspace(
                    newCampusNameInput.text,
                    newCampusAddressInput.text,
                    databasePath
                )
            } else if (appWindow.pendingDatabaseAction === "import") {
                if (backend.isRegisteredDatabase(databasePath)) {
                    appWindow.pendingDatabasePath = databasePath
                    replaceImportDialog.open()
                } else {
                    succeeded = backend.openPackage(
                        appWindow.pendingPackagePath,
                        databasePath
                    )
                }
            }
            if (succeeded) {
                appWindow.creatingCampus = false
                appWindow.pendingPackagePath = ""
                newCampusNameInput.text = ""
                newCampusAddressInput.text = ""
            }
            appWindow.pendingDatabaseAction = ""
        }
        onRejected: appWindow.pendingDatabaseAction = ""
    }

    Dialog {
        id: replaceImportDialog
        title: "Actualizar los datos de esta sede"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        background: Rectangle {
            radius: 0
            color: appWindow.surfaceColor
            border.color: appWindow.borderColor
        }
        Label {
            text: "Se reemplazarán los datos locales de la sede elegida con el contenido del paquete. Continúa solo si ya importaste y confirmaste la sincronización en la web."
            wrapMode: Text.Wrap
        }
        onAccepted: {
            if (backend.openPackage(
                    appWindow.pendingPackagePath,
                    appWindow.pendingDatabasePath,
                    true
                )) {
                appWindow.creatingCampus = false
                newCampusNameInput.text = ""
                newCampusAddressInput.text = ""
            }
            appWindow.pendingPackagePath = ""
            appWindow.pendingDatabasePath = ""
        }
        onRejected: {
            appWindow.pendingPackagePath = ""
            appWindow.pendingDatabasePath = ""
        }
    }

    Dialog {
        id: closeCampusDialog
        title: "Cerrar sede activa"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        background: Rectangle {
            radius: 0
            color: appWindow.surfaceColor
            border.color: appWindow.borderColor
        }
        Label {
            text: "La sede se cerrará en Desktop, pero su base de datos y sus datos se conservarán. Podrás volver a abrirla desde el selector de sedes."
            wrapMode: Text.Wrap
        }
        onAccepted: {
            if (backend.closeCampus()) {
                appWindow.creatingCampus = false
            }
        }
    }

    FileDialog {
        id: localDatabaseDialog
        title: "Abrir una base de datos de sede"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Base de datos SQLite (*.sqlite3 *.db)", "Todos los archivos (*)"]
        onAccepted: {
            if (backend.openLocalDatabase(selectedFile.toString())) {
                appWindow.creatingCampus = false
            }
        }
    }

    FileDialog {
        id: saveDialog
        title: "Guardar archivo de sincronización"
        fileMode: FileDialog.SaveFile
        currentFile: backend.isNewCampus
                     ? "edutrack-sede-inicial.edutrack"
                     : "edutrack-sincronizacion.edutrack"
        nameFilters: ["EduTrack (*.edutrack)"]
        onAccepted: backend.exportPackage(selectedFile.toString())
    }

    Dialog {
        id: studentEditDialog
        title: "Editar estudiante"
        modal: true
        anchors.centerIn: parent
        width: Math.min(500, appWindow.width - 48)
        padding: 22
        spacing: 14

        background: Rectangle {
            radius: 0
            color: appWindow.surfaceColor
            border.color: appWindow.borderColor
        }

        contentItem: ColumnLayout {
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: studentEditDialog.title
                color: appWindow.primaryTextColor
                font.family: "Roboto"
                font.pixelSize: 20
                font.bold: true
            }

            TextField {
                id: editStudentLastName
                Layout.fillWidth: true
                placeholderText: "Apellidos"
                font.family: "Roboto"
            }

            TextField {
                id: editStudentFirstName
                Layout.fillWidth: true
                placeholderText: "Nombres"
                font.family: "Roboto"
            }

            TextField {
                id: editStudentDocument
                Layout.fillWidth: true
                placeholderText: "Documento (opcional)"
                font.family: "Roboto"
            }

            TextField {
                id: editStudentPhones
                Layout.fillWidth: true
                placeholderText: "Teléfonos, separados por comas"
                font.family: "Roboto"
            }
        }

        footer: RowLayout {
            spacing: 8

            Item {
                Layout.fillWidth: true
            }

            Button {
                text: "Cancelar"
                font.family: "Roboto"
                flat: true
                Material.foreground: appWindow.secondaryTextColor
                onClicked: studentEditDialog.reject()
            }

            Button {
                id: saveStudentButton
                text: "Guardar"
                font.family: "Roboto"
                highlighted: true
                Material.foreground: appWindow.headerText
                background: Rectangle {
                    radius: 8
                    color: saveStudentButton.down
                           ? appTheme.exportButtonPressed
                           : appTheme.exportButton
                }
                onClicked: studentEditDialog.accept()
            }
        }

        onAccepted: {
            backend.saveStudent(
                appWindow.editingStudentId,
                editStudentLastName.text,
                editStudentFirstName.text,
                editStudentDocument.text,
                editStudentPhones.text
            )
            appWindow.editingStudentId = ""
        }

        onRejected: appWindow.editingStudentId = ""
    }

    Rectangle {
        id: startupScreen
        anchors.fill: parent
        z: 1000
        visible: !appWindow.startupComplete
        color: appWindow.pageBackgroundColor

        MouseArea {
            anchors.fill: parent
        }

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 14
            BusyIndicator {
                Layout.alignment: Qt.AlignHCenter
                running: startupScreen.visible
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                text: "Cargando EduTrack..."
                color: appWindow.primaryTextColor
                font.pixelSize: 18
            }
        }
    }

    Item {
        id: windowResizeHandles
        anchors.fill: parent
        z: 2000
        enabled: appWindow.visibility === Window.Windowed

        MouseArea {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.topMargin: 8
            width: 6
            height: parent.height - 16
            cursorShape: Qt.SizeHorCursor
            onPressed: appWindow.startSystemResize(Qt.LeftEdge)
        }

        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: 8
            width: 6
            height: parent.height - 16
            cursorShape: Qt.SizeHorCursor
            onPressed: appWindow.startSystemResize(Qt.RightEdge)
        }

        MouseArea {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.right: parent.right
            anchors.rightMargin: 8
            height: 6
            cursorShape: Qt.SizeVerCursor
            onPressed: appWindow.startSystemResize(Qt.TopEdge)
        }

        MouseArea {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.right: parent.right
            anchors.rightMargin: 8
            height: 6
            cursorShape: Qt.SizeVerCursor
            onPressed: appWindow.startSystemResize(Qt.BottomEdge)
        }

        MouseArea {
            anchors.left: parent.left
            anchors.top: parent.top
            width: 8
            height: 8
            cursorShape: Qt.SizeFDiagCursor
            onPressed: appWindow.startSystemResize(Qt.TopEdge | Qt.LeftEdge)
        }

        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            width: 8
            height: 8
            cursorShape: Qt.SizeBDiagCursor
            onPressed: appWindow.startSystemResize(Qt.TopEdge | Qt.RightEdge)
        }

        MouseArea {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            width: 8
            height: 8
            cursorShape: Qt.SizeBDiagCursor
            onPressed: appWindow.startSystemResize(Qt.BottomEdge | Qt.LeftEdge)
        }

        MouseArea {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: 8
            height: 8
            cursorShape: Qt.SizeFDiagCursor
            onPressed: appWindow.startSystemResize(Qt.BottomEdge | Qt.RightEdge)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 16

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 88
            radius: 0
            color: Material.primary
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                onPressed: appWindow.startSystemMove()
                onDoubleClicked: appWindow.toggleMaximized()
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
                            color: appTheme.headerText
                            font.pixelSize: 23
                            font.bold: true
                        }
                        Label {
                            Layout.fillWidth: true
                            text: backend.campusName
                            color: appTheme.headerSecondary
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }
                }
                Button {
                    text: "Cerrar sede"
                    flat: true
                    visible: backend.hasWorkspace
                    Material.foreground: appTheme.headerText
                    onClicked: closeCampusDialog.open()
                }
                IconTextButton {
                    text: appWindow.darkMode ? "Modo claro" : "Modo nocturno"
                    symbolName: appWindow.darkMode ? "light_mode" : "dark_mode"
                    symbolColor: appTheme.headerText
                    flat: true
                    Material.foreground: appTheme.headerText
                    onClicked: appWindow.darkMode = !appWindow.darkMode
                }
                IconTextButton {
                    id: exportButton
                    text: backend.isNewCampus
                          ? "Exportar sede inicial"
                          : "Exportar sincronización"
                    symbolName: "ios_share"
                    symbolColor: appTheme.headerText
                    Material.foreground: appTheme.headerText
                    highlighted: true
                    visible: backend.hasWorkspace
                    enabled: backend.hasWorkspace
                    background: Rectangle {
                        implicitWidth: 190
                        implicitHeight: 42
                        radius: 8
                        color: exportButton.down
                               ? appTheme.exportButtonPressed : appTheme.exportButton
                    }
                    onClicked: saveDialog.open()
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
                            color: appTheme.headerText
                        }
                    }
                    onClicked: appWindow.visibility = Window.Minimized
                }

                Button {
                    id: maximizeWindowButton
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    flat: true
                    ToolTip.visible: hovered
                    ToolTip.text: appWindow.visibility === Window.Maximized
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
                            visible: appWindow.visibility !== Window.Maximized
                            width: 12
                            height: 12
                            anchors.centerIn: parent
                            color: "transparent"
                            border.color: appTheme.headerText
                            border.width: 1.5
                        }

                        Item {
                            visible: appWindow.visibility === Window.Maximized
                            width: 18
                            height: 18
                            anchors.centerIn: parent

                            Rectangle {
                                x: 2
                                y: 5
                                width: 11
                                height: 10
                                color: Material.primary
                                border.color: appTheme.headerText
                                border.width: 1.2
                            }

                            Rectangle {
                                x: 6
                                y: 3
                                width: 11
                                height: 10
                                color: Material.primary
                                border.color: appTheme.headerText
                                border.width: 1.2
                            }
                        }
                    }
                    onClicked: appWindow.toggleMaximized()
                }

                Button {
                    id: closeWindowButton
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    flat: true
                    ToolTip.visible: hovered
                    ToolTip.text: "Cerrar ventana"
                    background: Rectangle {
                        radius: 0
                        color: closeWindowButton.down
                               ? appWindow.errorColor
                               : closeWindowButton.hovered
                                 ? appWindow.errorColor
                                 : "transparent"
                    }
                    contentItem: Item {
                        Rectangle {
                            width: 15
                            height: 1.5
                            anchors.centerIn: parent
                            rotation: 45
                            color: closeWindowButton.hovered
                                   ? appWindow.darkMode ? appTheme.background : "#ffffff"
                                   : appTheme.headerText
                        }

                        Rectangle {
                            width: 15
                            height: 1.5
                            anchors.centerIn: parent
                            rotation: -45
                            color: closeWindowButton.hovered
                                   ? appWindow.darkMode ? appTheme.background : "#ffffff"
                                   : appTheme.headerText
                        }
                    }
                    onClicked: appWindow.close()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            property bool setupVisible: !backend.hasWorkspace || appWindow.creatingCampus
            radius: 0
            color: setupVisible ? appWindow.surfaceColor : "transparent"
            border.color: setupVisible ? appWindow.borderColor : "transparent"
            Flickable {
                id: campusSetupFlick
                anchors.fill: parent
                anchors.margins: 20
                anchors.bottomMargin: statusBar.height + 32
                visible: parent.setupVisible
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
                            text: appWindow.creatingCampus
                                  ? "Crear una sede nueva"
                                  : "Prepara tu sede"
                            horizontalAlignment: Text.AlignHCenter
                            color: appWindow.primaryTextColor
                            font.pixelSize: 25
                            font.bold: true
                            wrapMode: Text.Wrap
                        }
                        Label {
                            Layout.fillWidth: true
                            text: appWindow.creatingCampus
                                  ? "Ingresa los datos básicos y elige dónde guardar la base SQLite."
                                  : "Elige una sede guardada, importa un paquete o crea una nueva sin conexión."
                            horizontalAlignment: Text.AlignHCenter
                            color: appWindow.secondaryTextColor
                            font.pixelSize: 15
                            wrapMode: Text.Wrap
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            visible: !appWindow.creatingCampus
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 12
                            Button {
                                id: importCampusTile
                                Layout.fillWidth: true
                                Layout.preferredHeight: 108
                                text: "Importar paquete"
                                Material.foreground: appWindow.primaryTextColor
                                contentItem: ColumnLayout {
                                    spacing: 7
                                    MaterialSymbol {
                                        Layout.alignment: Qt.AlignHCenter
                                        symbolName: "folder_open"
                                        symbolSize: 28
                                        symbolColor: appWindow.accentTextColor
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: importCampusTile.text
                                        horizontalAlignment: Text.AlignHCenter
                                        color: appWindow.primaryTextColor
                                        font.bold: true
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: "Desde un paquete EduTrack"
                                        horizontalAlignment: Text.AlignHCenter
                                        color: appWindow.secondaryTextColor
                                        font.pixelSize: 12
                                    }
                                }
                                background: Rectangle {
                                    radius: 12
                                    color: importCampusTile.down
                                           ? appWindow.accentSurfaceColor
                                           : importCampusTile.hovered
                                             ? appWindow.nestedSurfaceColor
                                             : appWindow.surfaceColor
                                    border.color: importCampusTile.hovered
                                                 ? appWindow.accentTextColor
                                                 : appWindow.borderColor
                                }
                                onClicked: openDialog.open()
                            }
                            Button {
                                id: openDatabaseTile
                                Layout.fillWidth: true
                                Layout.preferredHeight: 108
                                text: "Abrir base local"
                                Material.foreground: appWindow.primaryTextColor
                                contentItem: ColumnLayout {
                                    spacing: 7
                                    MaterialSymbol {
                                        Layout.alignment: Qt.AlignHCenter
                                        symbolName: "folder_open"
                                        symbolSize: 28
                                        symbolColor: appWindow.accentTextColor
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: openDatabaseTile.text
                                        horizontalAlignment: Text.AlignHCenter
                                        color: appWindow.primaryTextColor
                                        font.bold: true
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: "Selecciona un archivo SQLite"
                                        horizontalAlignment: Text.AlignHCenter
                                        color: appWindow.secondaryTextColor
                                        font.pixelSize: 12
                                    }
                                }
                                background: Rectangle {
                                    radius: 12
                                    color: openDatabaseTile.down
                                           ? appWindow.accentSurfaceColor
                                           : openDatabaseTile.hovered
                                             ? appWindow.nestedSurfaceColor
                                             : appWindow.surfaceColor
                                    border.color: openDatabaseTile.hovered
                                                 ? appWindow.accentTextColor
                                                 : appWindow.borderColor
                                }
                                onClicked: localDatabaseDialog.open()
                            }
                            Button {
                                id: createCampusTile
                                Layout.columnSpan: 2
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 280
                                Layout.preferredHeight: 88
                                text: "Crear una sede nueva"
                                Material.foreground: appWindow.primaryTextColor
                                contentItem: RowLayout {
                                    spacing: 12
                                    MaterialSymbol {
                                        symbolName: "add"
                                        symbolSize: 28
                                        symbolColor: appWindow.accentTextColor
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Label {
                                            Layout.fillWidth: true
                                            text: createCampusTile.text
                                            color: appWindow.primaryTextColor
                                            font.bold: true
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: "Configura una sede sin conexión"
                                            color: appWindow.secondaryTextColor
                                            font.pixelSize: 12
                                        }
                                    }
                                    MaterialSymbol {
                                        symbolName: "chevron_right"
                                        symbolSize: 20
                                        symbolColor: appWindow.secondaryTextColor
                                    }
                                }
                                background: Rectangle {
                                    radius: 12
                                    color: createCampusTile.down
                                           ? appWindow.accentSurfaceColor
                                           : createCampusTile.hovered
                                             ? appWindow.nestedSurfaceColor
                                             : appWindow.surfaceColor
                                    border.color: createCampusTile.hovered
                                                 ? appWindow.accentTextColor
                                                 : appWindow.borderColor
                                }
                                onClicked: {
                                    newCampusNameInput.text = ""
                                    newCampusAddressInput.text = ""
                                    appWindow.creatingCampus = true
                                }
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: !appWindow.creatingCampus && backend.campuses.length > 0
                            text: "Sedes guardadas"
                            horizontalAlignment: Text.AlignHCenter
                            color: appWindow.primaryTextColor
                            font.pixelSize: 16
                            font.bold: true
                        }
                        GridView {
                            id: savedCampusesGrid
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.ceil(backend.campuses.length / 2) * 96
                            visible: !appWindow.creatingCampus && backend.campuses.length > 0
                            cellWidth: 280
                            cellHeight: 96
                            interactive: false
                            model: backend.campuses
                            delegate: Button {
                                id: savedCampusTile
                                width: savedCampusesGrid.cellWidth - 10
                                height: savedCampusesGrid.cellHeight - 8
                                text: modelData.campus_name
                                Material.foreground: appWindow.primaryTextColor
                                contentItem: RowLayout {
                                    spacing: 10
                                    MaterialSymbol {
                                        symbolName: "folder_open"
                                        symbolSize: 24
                                        symbolColor: appWindow.accentTextColor
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: savedCampusTile.text
                                        color: appWindow.primaryTextColor
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }
                                    MaterialSymbol {
                                        symbolName: "chevron_right"
                                        symbolSize: 20
                                        symbolColor: appWindow.secondaryTextColor
                                    }
                                }
                                background: Rectangle {
                                    radius: 12
                                    color: savedCampusTile.down
                                           ? appWindow.accentSurfaceColor
                                           : savedCampusTile.hovered
                                             ? appWindow.nestedSurfaceColor
                                             : appWindow.surfaceColor
                                    border.color: savedCampusTile.hovered
                                                 ? appWindow.accentTextColor
                                                 : appWindow.borderColor
                                }
                                onClicked: {
                                    if (backend.switchCampus(modelData.path))
                                        appWindow.creatingCampus = false
                                }
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            visible: appWindow.creatingCampus
                            color: appWindow.dividerColor
                        }
                        UppercaseTextField {
                            id: newCampusNameInput
                            Layout.fillWidth: true
                            visible: appWindow.creatingCampus
                            placeholderText: "Nombre de la sede"
                            maximumLength: 120
                        }
                        UppercaseTextField {
                            id: newCampusAddressInput
                            Layout.fillWidth: true
                            visible: appWindow.creatingCampus
                            placeholderText: "Dirección (opcional)"
                            maximumLength: 200
                        }
                        IconTextButton {
                            id: createWorkspaceButton
                            Layout.alignment: Qt.AlignHCenter
                            visible: appWindow.creatingCampus
                            text: "Elegir ubicación y crear sede"
                            symbolName: "add"
                            symbolColor: appTheme.headerText
                            Material.foreground: appTheme.headerText
                            highlighted: true
                            background: Rectangle {
                                implicitWidth: 250
                                implicitHeight: 44
                                radius: 8
                                color: createWorkspaceButton.down
                                       ? appTheme.createButtonPressed : appTheme.createButton
                            }
                            onClicked: {
                                appWindow.pendingDatabaseAction = "create"
                                databasePathDialog.open()
                            }
                        }
                        Button {
                            Layout.alignment: Qt.AlignHCenter
                            visible: appWindow.creatingCampus
                            text: backend.hasWorkspace
                                  ? "Volver a la sede abierta"
                                  : "Volver a opciones"
                            flat: true
                            onClicked: appWindow.creatingCampus = false
                        }
                }
            }

            RowLayout {
                id: workspaceNavigation
                anchors.fill: parent
                anchors.margins: 16
                anchors.bottomMargin: statusBar.height + 32
                spacing: 16
                visible: backend.hasWorkspace && !appWindow.creatingCampus

                Rectangle {
                    id: workspaceSidebar
                    Layout.preferredWidth: 152
                    Layout.fillHeight: true
                    radius: 0
                    color: appWindow.surfaceColor
                    border.color: appWindow.borderColor
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8

                        Repeater {
                            model: [
                                { label: "Matrículas", symbol: "assignment" },
                                { label: "Estudiantes", symbol: "groups" },
                                { label: "Cursos", symbol: "menu_book" },
                                { label: "Resumen", symbol: "event" }
                            ]

                            delegate: Button {
                                id: sectionButton
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(
                                    80,
                                    Math.min(112, (workspaceNavigation.height - 44) / 4)
                                )
                                property bool selected: appWindow.selectedWorkspaceSection
                                                        === modelData.label
                                Material.foreground: appWindow.primaryTextColor
                                contentItem: ColumnLayout {
                                    spacing: 6
                                    MaterialSymbol {
                                        Layout.alignment: Qt.AlignHCenter
                                        symbolName: sectionButton.modelData.symbol
                                        symbolSize: 36
                                        symbolColor: sectionButton.selected
                                                      ? appWindow.accentTextColor
                                                      : appWindow.secondaryTextColor
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: sectionButton.modelData.label
                                        horizontalAlignment: Text.AlignHCenter
                                        color: appWindow.primaryTextColor
                                        font.family: "Roboto"
                                        font.pixelSize: 16
                                        font.bold: sectionButton.selected
                                        elide: Text.ElideRight
                                    }
                                }
                                background: Rectangle {
                                    radius: 12
                                    color: sectionButton.selected
                                           ? appWindow.accentSurfaceColor
                                           : sectionButton.down
                                             ? appWindow.accentSurfaceColor
                                             : sectionButton.hovered
                                               ? appWindow.nestedSurfaceColor
                                               : appWindow.surfaceColor
                                    border.color: sectionButton.selected
                                                  ? appWindow.accentTextColor
                                                  : appWindow.borderColor
                                }
                                onClicked: appWindow.selectedWorkspaceSection =
                                               sectionButton.modelData.label
                            }
                        }

                        Item {
                            Layout.fillHeight: true
                        }
                    }
                }

                Rectangle {
                    id: studentsPanel
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: appWindow.selectedWorkspaceSection === "Estudiantes"
                    radius: 0
                    color: appWindow.surfaceColor
                    border.color: appWindow.borderColor

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 16

                        RowLayout {
                            Layout.fillWidth: true

                            Label {
                                text: "Estudiantes"
                                color: appWindow.primaryTextColor
                                font.family: "Roboto"
                                font.pixelSize: 24
                                font.bold: true
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            Label {
                                text: appWindow.matchingStudentCount + " estudiantes"
                                color: appWindow.secondaryTextColor
                                font.family: "Roboto"
                                font.pixelSize: 14
                            }
                        }

                        TextField {
                            id: studentSearch
                            Layout.fillWidth: true
                            placeholderText: "Buscar por nombre, documento o curso..."
                            font.family: "Roboto"
                            onTextChanged: {
                                appWindow.studentPageIndex = 0
                                appWindow.refreshStudentPage()
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: appWindow.dividerColor
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            Label {
                                Layout.fillWidth: true
                                text: "ESTUDIANTE"
                                color: appWindow.secondaryTextColor
                                font.family: "Roboto"
                                font.pixelSize: 12
                                font.bold: true
                            }

                            Label {
                                Layout.preferredWidth: 220
                                text: "CURSO(S)"
                                color: appWindow.secondaryTextColor
                                font.family: "Roboto"
                                font.pixelSize: 12
                                font.bold: true
                            }

                            Label {
                                Layout.preferredWidth: 224
                                text: "ACCIONES"
                                color: appWindow.secondaryTextColor
                                font.family: "Roboto"
                                font.pixelSize: 12
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            visible: appWindow.visibleStudentRows.length === 0
                            text: appWindow.matchingStudentCount === 0
                                  && studentSearch.text.trim().length === 0
                                  ? "No hay estudiantes registrados."
                                  : "No se encontraron estudiantes con ese filtro."
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: appWindow.secondaryTextColor
                            font.family: "Roboto"
                            font.pixelSize: 16
                        }

                        ListView {
                            id: studentsList
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            visible: appWindow.visibleStudentRows.length > 0
                            clip: true
                            spacing: 8
                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AlwaysOn
                                active: true
                            }
                            model: appWindow.visibleStudentRows

                            delegate: Rectangle {
                                required property var modelData
                                width: studentsList.width
                                height: 72
                                radius: 10
                                color: appWindow.nestedSurfaceColor
                                border.color: appWindow.borderColor

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 16
                                    anchors.rightMargin: 12
                                    spacing: 12

                                    Label {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        text: modelData.label
                                        color: appWindow.primaryTextColor
                                        font.family: "Roboto"
                                        font.pixelSize: 15
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }

                                    Label {
                                        Layout.preferredWidth: 220
                                        Layout.minimumWidth: 220
                                        Layout.maximumWidth: 220
                                        text: (modelData.courses || []).join(", ")
                                        color: appWindow.secondaryTextColor
                                        font.family: "Roboto"
                                        font.pixelSize: 13
                                        elide: Text.ElideRight
                                    }

                                    RowLayout {
                                        Layout.preferredWidth: 224
                                        Layout.minimumWidth: 224
                                        Layout.maximumWidth: 224
                                        spacing: 6

                                        Button {
                                            id: editStudentButton
                                            Layout.preferredWidth: 94
                                            Layout.minimumWidth: 94
                                            Layout.maximumWidth: 94
                                            Layout.preferredHeight: 34
                                            Layout.maximumHeight: 34
                                            text: "Editar"
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                            leftPadding: 6
                                            rightPadding: 6
                                            Material.foreground: appWindow.accentTextColor
                                            contentItem: RowLayout {
                                                spacing: 4

                                                Item {
                                                    Layout.fillWidth: true
                                                }

                                                MaterialSymbol {
                                                    symbolName: "assignment"
                                                    symbolSize: 18
                                                    symbolColor: appWindow.accentTextColor
                                                }

                                                Label {
                                                    text: editStudentButton.text
                                                    color: appWindow.accentTextColor
                                                    font: editStudentButton.font
                                                    verticalAlignment: Text.AlignVCenter
                                                }

                                                Item {
                                                    Layout.fillWidth: true
                                                }
                                            }
                                            background: Rectangle {
                                                radius: 8
                                                color: appWindow.accentSurfaceColor
                                                border.color: editStudentButton.hovered
                                                              ? appWindow.accentTextColor
                                                              : appWindow.borderColor
                                            }
                                            onClicked: {
                                                appWindow.editingStudentId = modelData.id
                                                editStudentLastName.text = modelData.last_name
                                                editStudentFirstName.text = modelData.first_name
                                                editStudentDocument.text = modelData.document_number || ""
                                                editStudentPhones.text = (modelData.phone_numbers || []).join(", ")
                                                studentEditDialog.open()
                                            }
                                        }

                                        Button {
                                            id: activeStudentButton
                                            property color stateColor: modelData.active
                                                                       ? appWindow.successColor
                                                                       : appWindow.errorColor
                                            property color stateSurfaceColor: modelData.active
                                                                              ? appWindow.successSurfaceColor
                                                                              : appWindow.errorSurfaceColor
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 124
                                            Layout.minimumWidth: 124
                                            Layout.maximumWidth: 124
                                            Layout.preferredHeight: 34
                                            Layout.maximumHeight: 34
                                            text: modelData.active ? "Activo" : "Inactivo"
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                            leftPadding: 6
                                            rightPadding: 6
                                            Material.foreground: stateColor
                                            contentItem: Label {
                                                text: activeStudentButton.text
                                                color: activeStudentButton.stateColor
                                                font: activeStudentButton.font
                                                horizontalAlignment: Text.AlignHCenter
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                            background: Rectangle {
                                                radius: 8
                                                color: activeStudentButton.stateSurfaceColor
                                                border.color: activeStudentButton.hovered
                                                              ? activeStudentButton.stateColor
                                                              : appWindow.borderColor
                                            }
                                            onClicked: backend.setStudentActive(
                                                modelData.id,
                                                !modelData.active
                                            )
                                        }
                                    }
                                }

                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            visible: appWindow.matchingStudentCount
                                     > appWindow.studentPageSize

                            Item {
                                Layout.fillWidth: true
                            }

                            Button {
                                text: "Anterior"
                                enabled: appWindow.studentPageIndex > 0
                                font.family: "Roboto"
                                onClicked: {
                                    appWindow.studentPageIndex -= 1
                                    appWindow.refreshStudentPage()
                                }
                            }

                            Label {
                                text: "Página " + (appWindow.studentPageIndex + 1)
                                      + " de "
                                      + Math.ceil(
                                            appWindow.matchingStudentCount
                                            / appWindow.studentPageSize
                                        )
                                color: appWindow.secondaryTextColor
                                font.family: "Roboto"
                                font.pixelSize: 13
                            }

                            Button {
                                text: "Siguiente"
                                enabled: (appWindow.studentPageIndex + 1)
                                         * appWindow.studentPageSize
                                         < appWindow.matchingStudentCount
                                font.family: "Roboto"
                                onClicked: {
                                    appWindow.studentPageIndex += 1
                                    appWindow.refreshStudentPage()
                                }
                            }

                            Item {
                                Layout.fillWidth: true
                            }
                        }
                    }

                }
            }

            Rectangle {
                id: statusBar
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
                       ? appWindow.surfaceColor
                       : successful ? appWindow.successSurfaceColor : appWindow.errorSurfaceColor
                border.color: appWindow.borderColor

                Label {
                    id: statusMessage
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    text: appWindow.statusMessageText
                    color: statusMessage.text.length === 0
                           ? appWindow.secondaryTextColor
                           : statusBar.successful ? appWindow.successColor : appWindow.errorColor
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    font.family: "Roboto"
                    font.pixelSize: 13
                }
            }
        }
    }
}
