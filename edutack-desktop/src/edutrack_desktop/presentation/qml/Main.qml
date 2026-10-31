import QtQuick
import QtQuick.Controls.Material
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"
import "pages"
import "dialogs"

ApplicationWindow {
    id: appWindow
    width: 980
    height: 620
    minimumWidth: 980
    minimumHeight: 620
    visible: false
    title: "EduTrack Desktop"
    flags: Qt.Window
           | Qt.WindowTitleHint
           | Qt.WindowSystemMenuHint
           | Qt.WindowMinimizeButtonHint
           | Qt.WindowMaximizeButtonHint
           | Qt.WindowCloseButtonHint
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
    property var desktopBackend: null
    property bool restoringSession: false
    property bool sessionTrackingEnabled: false
    property string sessionSnapshot: sessionTrackingEnabled
                                         ? JSON.stringify(collectSessionState()) : ""
    property var initialSessionState: ({})
    property bool creatingCampus: false
    property string selectedWorkspaceSection: "Resumen"
    property bool startupComplete: false
    property bool closeAfterCurrentOperation: false
    property bool closeAllowedWithUnsavedChanges: false
    property string statusMessageText: ""
    property string campusFormName: ""
    property string campusFormAddress: ""
    property bool campusSetupPageLoaded: false
    property bool workspacePageLoaded: false
    property bool appDialogsRequested: false
    property bool appDialogsLoaded: false
    property string pendingAppDialogAction: ""
    property var campusSetupPageItem: null
    property var workspacePageItem: null
    property var appDialogsItem: null

    AppTheme {
        id: appTheme
        darkMode: appWindow.darkMode
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: backend.hasWorkspace && !backend.isBusy
                 && !appWindow.creatingCampus
        onActivated: {
            if (appWindow.workspacePageItem)
                appWindow.workspacePageItem.openNewStudent()
        }
    }

    Shortcut {
        sequence: "Ctrl+M"
        enabled: backend.hasWorkspace && !backend.isBusy
                 && !appWindow.creatingCampus
        onActivated: {
            if (appWindow.workspacePageItem)
                appWindow.workspacePageItem.openNewEnrollment()
        }
    }

    Shortcut {
        sequence: "Ctrl+F"
        enabled: backend.hasWorkspace && !appWindow.creatingCampus
        onActivated: {
            if (appWindow.workspacePageItem)
                appWindow.workspacePageItem.focusCurrentSearch()
        }
    }

    Shortcut {
        sequence: "Ctrl+E"
        enabled: backend.hasWorkspace && !backend.isBusy
        onActivated: appWindow.requestAppDialog("export")
    }

    Shortcut {
        sequence: "F5"
        enabled: backend.hasWorkspace && !backend.isBusy
        onActivated: backend.refreshWorkspace()
    }

    function activeCampusPath() {
        var index = backend.activeCampusIndex
        var campuses = backend.campuses
        return index >= 0 && index < campuses.length ? campuses[index].path : ""
    }

    function requestAppDialog(action) {
        appWindow.pendingAppDialogAction = action
        appWindow.appDialogsRequested = true
        if (appWindow.appDialogsItem)
            Qt.callLater(appWindow.dispatchPendingAppDialog)
    }

    function dispatchPendingAppDialog() {
        if (!appWindow.appDialogsItem || !appWindow.pendingAppDialogAction)
            return

        var action = appWindow.pendingAppDialogAction
        appWindow.pendingAppDialogAction = ""
        if (action === "import")
            appWindow.appDialogsItem.openImportDialog()
        else if (action === "createDatabase")
            appWindow.appDialogsItem.openCreateDatabaseDialog()
        else if (action === "openDatabase")
            appWindow.appDialogsItem.openLocalDatabaseDialog()
        else if (action === "export")
            appWindow.appDialogsItem.openExportDialog()
        else if (action === "closeCampus")
            appWindow.appDialogsItem.openCloseCampusDialog()
    }

    function loadSessionState() {
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
        return state
    }

    function initializeWindowGeometry(state) {
        var savedWindow = state.window || {}
        var hasSavedGeometry =
                typeof savedWindow.x === "number" && isFinite(savedWindow.x)
                && typeof savedWindow.y === "number" && isFinite(savedWindow.y)
                && typeof savedWindow.width === "number"
                && isFinite(savedWindow.width)
                && savedWindow.width >= appWindow.minimumWidth
                && typeof savedWindow.height === "number"
                && isFinite(savedWindow.height)
                && savedWindow.height >= appWindow.minimumHeight
        if (hasSavedGeometry) {
            appWindow.width = Math.round(savedWindow.width)
            appWindow.height = Math.round(savedWindow.height)
            appWindow.x = Math.round(savedWindow.x)
            appWindow.y = Math.round(savedWindow.y)
            return
        }

        appWindow.width = appWindow.minimumWidth
        appWindow.height = appWindow.minimumHeight
        appWindow.x = Math.round(
            Screen.virtualX + Math.max(0, (Screen.width - appWindow.width) / 2)
        )
        appWindow.y = Math.round(
            Screen.virtualY + Math.max(0, (Screen.height - appWindow.height) / 2)
        )
    }

    function restoreSessionState(state) {
        appWindow.restoringSession = true
        appWindow.darkMode = state.darkMode === true
        var workspaceSections = [
            "Resumen",
            "Estudiantes",
            "Matrículas",
            "Cursos",
            "Sincronización",
            "Respaldos"
        ]
        if (workspaceSections.indexOf(state.selectedWorkspaceSection) >= 0)
            appWindow.selectedWorkspaceSection = state.selectedWorkspaceSection
        if (state.campusPath === appWindow.activeCampusPath()) {
            var campusForm = state.campusForm || {}
            appWindow.campusFormName = campusForm.name || ""
            appWindow.campusFormAddress = campusForm.address || ""
            appWindow.creatingCampus = state.creatingCampus === true
            if (appWindow.campusSetupPageItem) {
                appWindow.campusSetupPageItem.campusName = appWindow.campusFormName
                appWindow.campusSetupPageItem.campusAddress = appWindow.campusFormAddress
            }
        }

        if (appWindow.workspacePageItem) {
            appWindow.workspacePageItem.ensureSectionLoaded(
                appWindow.selectedWorkspaceSection
            )
        }
        appWindow.restoringSession = false
        appWindow.sessionTrackingEnabled = true
    }

    function collectSessionState() {
        return {
            version: 1,
            campusPath: appWindow.activeCampusPath(),
            darkMode: appWindow.darkMode,
            selectedWorkspaceSection: appWindow.selectedWorkspaceSection,
            creatingCampus: appWindow.creatingCampus,
            window: {
                x: appWindow.x,
                y: appWindow.y,
                width: appWindow.width,
                height: appWindow.height
            },
            campusForm: {
                name: appWindow.campusFormName,
                address: appWindow.campusFormAddress
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

    Component.onCompleted: {
        appWindow.initialSessionState = appWindow.loadSessionState()
        appWindow.initializeWindowGeometry(appWindow.initialSessionState)
        appWindow.showStatusMessage(backend.errorMessage)
        startupTimer.start()
    }
    onClosing: function(closeEvent) {
        if (backend.isBusy) {
            closeEvent.accepted = false
            appWindow.closeAfterCurrentOperation = true
            return
        }
        if (!appWindow.closeAllowedWithUnsavedChanges
                && appWindow.workspacePageItem
                && appWindow.workspacePageItem.hasUnsavedChanges) {
            closeEvent.accepted = false
            unsavedCloseDialog.open()
            return
        }
        appWindow.persistSessionState()
    }
    onSessionSnapshotChanged: {
        if (appWindow.sessionTrackingEnabled && !appWindow.restoringSession)
            sessionSaveTimer.restart()
    }

    Connections {
        target: backend
        function onActivityStateChanged() {
            if (appWindow.closeAfterCurrentOperation && !backend.isBusy) {
                Qt.callLater(function() {
                    if (appWindow.closeAfterCurrentOperation && !backend.isBusy) {
                        appWindow.closeAfterCurrentOperation = false
                        appWindow.close()
                    }
                })
            }
        }
        function onErrorChanged() {
            appWindow.showStatusMessage(backend.errorMessage)
        }
    }

    Dialog {
        id: unsavedCloseDialog
        modal: true
        title: "Cambios sin guardar"
        standardButtons: Dialog.NoButton
        width: Math.min(440, appWindow.width - 32)
        anchors.centerIn: Overlay.overlay

        contentItem: ColumnLayout {
            spacing: 16

            Label {
                Layout.fillWidth: true
                text: "Hay cambios sin guardar en un formulario. "
                      + "¿Quieres descartarlos y cerrar EduTrack Desktop?"
                color: appTheme.primaryText
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true

                Item {
                    Layout.fillWidth: true
                }

                Button {
                    text: "Seguir trabajando"
                    onClicked: unsavedCloseDialog.close()
                }

                Button {
                    text: "Descartar y cerrar"
                    highlighted: true
                    onClicked: {
                        unsavedCloseDialog.close()
                        appWindow.closeAllowedWithUnsavedChanges = true
                        Qt.callLater(function() {
                            appWindow.close()
                        })
                    }
                }
            }
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
            appWindow.restoreSessionState(appWindow.initialSessionState)
            appWindow.startupComplete = true
        }
    }

    Loader {
        id: appDialogsLoader
        objectName: "appDialogsLoader"
        anchors.fill: parent
        active: appWindow.appDialogsRequested || appWindow.appDialogsLoaded
        asynchronous: true
        sourceComponent: Component {
            AppDialogs {
                anchors.fill: parent
                backendObject: backend
                windowController: appWindow
                campusPage: appWindow.campusSetupPageItem
                theme: appTheme
            }
        }
        onLoaded: {
            appWindow.appDialogsItem = item
            appWindow.appDialogsLoaded = true
            appWindow.dispatchPendingAppDialog()
        }
        onStatusChanged: {
            if (status === Loader.Error) {
                appWindow.appDialogsItem = null
                appWindow.pendingAppDialogAction = ""
                console.error("No se pudieron cargar los diálogos: " + errorString())
                appWindow.showStatusMessage(
                    "No se pudieron cargar los diálogos de la aplicación."
                )
            }
        }
    }

    StartupOverlay {
        anchors.fill: parent
        theme: appTheme
        startupComplete: appWindow.startupComplete
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 16

        WorkspaceHeader {
            Layout.fillWidth: true
            windowController: appWindow
            backendObject: backend
            theme: appTheme
            onCloseCampusRequested: appWindow.requestAppDialog("closeCampus")
            onDarkModeToggleRequested: appWindow.darkMode = !appWindow.darkMode
            onExportRequested: appWindow.requestAppDialog("export")
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            property bool setupVisible: !backend.hasWorkspace || appWindow.creatingCampus
            radius: 0
            color: setupVisible ? appWindow.surfaceColor : "transparent"
            border.color: setupVisible ? appWindow.borderColor : "transparent"

            Loader {
                id: campusSetupLoader
                objectName: "campusSetupPageLoader"
                anchors.fill: parent
                active: !backend.hasWorkspace || appWindow.creatingCampus
                        || appWindow.campusSetupPageLoaded
                visible: !backend.hasWorkspace || appWindow.creatingCampus
                sourceComponent: Component {
                    CampusSetupPage {
                        anchors.fill: parent
                        backendObject: backend
                        windowController: appWindow
                        theme: appTheme
                        statusBarHeight: statusBar.height
                        onCampusNameChanged: appWindow.campusFormName = campusName
                        onCampusAddressChanged: appWindow.campusFormAddress = campusAddress
                        onImportRequested: appWindow.requestAppDialog("import")
                        onOpenLocalDatabaseRequested: appWindow.requestAppDialog(
                                                           "openDatabase"
                                                       )
                        onCreateDatabaseRequested: appWindow.requestAppDialog(
                                                       "createDatabase"
                                                   )
                    }
                }
                onLoaded: {
                    appWindow.campusSetupPageLoaded = true
                    appWindow.campusSetupPageItem = item
                    appWindow.campusSetupPageItem.campusName =
                            appWindow.campusFormName
                    appWindow.campusSetupPageItem.campusAddress =
                            appWindow.campusFormAddress
                }
                onStatusChanged: {
                    if (status === Loader.Error) {
                        appWindow.campusSetupPageItem = null
                        console.error(
                            "No se pudo cargar la configuración de sede: "
                            + errorString()
                        )
                        appWindow.showStatusMessage(
                            "No se pudo cargar la configuración de sede."
                        )
                    }
                }
            }

            Loader {
                id: workspacePageLoader
                objectName: "workspacePageLoader"
                anchors.fill: parent
                active: backend.hasWorkspace || appWindow.workspacePageLoaded
                visible: backend.hasWorkspace && !appWindow.creatingCampus
                sourceComponent: Component {
                    WorkspacePage {
                        anchors.fill: parent
                        backendObject: backend
                        windowController: appWindow
                        theme: appTheme
                        statusBarHeight: statusBar.height
                    }
                }
                onLoaded: {
                    appWindow.workspacePageLoaded = true
                    appWindow.workspacePageItem = item
                    appWindow.workspacePageItem.ensureSectionLoaded(
                        appWindow.selectedWorkspaceSection
                    )
                }
                onStatusChanged: {
                    if (status === Loader.Error) {
                        appWindow.workspacePageItem = null
                        console.error(
                            "No se pudo cargar el espacio de trabajo: "
                            + errorString()
                        )
                        appWindow.showStatusMessage(
                            "No se pudo cargar el espacio de trabajo."
                        )
                    }
                }
            }

            StatusBar {
                id: statusBar
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                theme: appTheme
                message: appWindow.statusMessageText
            }
        }
    }

    DatabaseSavingOverlay {
        backendObject: backend
        theme: appTheme
    }
}
