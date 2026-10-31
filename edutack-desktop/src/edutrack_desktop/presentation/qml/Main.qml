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
    property string statusMessageText: ""

    AppTheme {
        id: appTheme
        darkMode: appWindow.darkMode
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: backend.hasWorkspace && !backend.isBusy
                 && !appWindow.creatingCampus
        onActivated: workspacePage.openNewStudent()
    }

    Shortcut {
        sequence: "Ctrl+M"
        enabled: backend.hasWorkspace && !backend.isBusy
                 && !appWindow.creatingCampus
        onActivated: workspacePage.openNewEnrollment()
    }

    Shortcut {
        sequence: "Ctrl+F"
        enabled: backend.hasWorkspace && !appWindow.creatingCampus
        onActivated: workspacePage.focusCurrentSearch()
    }

    Shortcut {
        sequence: "Ctrl+E"
        enabled: backend.hasWorkspace && !backend.isBusy
        onActivated: appDialogs.openExportDialog()
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
            campusSetupPage.campusName = campusForm.name || ""
            campusSetupPage.campusAddress = campusForm.address || ""
            appWindow.creatingCampus = state.creatingCampus === true
        }

        workspacePage.ensureSectionLoaded(appWindow.selectedWorkspaceSection)
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
                name: campusSetupPage.campusName,
                address: campusSetupPage.campusAddress
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

    AppDialogs {
        id: appDialogs
        anchors.fill: parent
        backendObject: backend
        windowController: appWindow
        campusPage: campusSetupPage
        theme: appTheme
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
            onCloseCampusRequested: appDialogs.openCloseCampusDialog()
            onDarkModeToggleRequested: appWindow.darkMode = !appWindow.darkMode
            onExportRequested: appDialogs.openExportDialog()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            property bool setupVisible: !backend.hasWorkspace || appWindow.creatingCampus
            radius: 0
            color: setupVisible ? appWindow.surfaceColor : "transparent"
            border.color: setupVisible ? appWindow.borderColor : "transparent"

            CampusSetupPage {
                id: campusSetupPage
                anchors.fill: parent
                backendObject: backend
                windowController: appWindow
                theme: appTheme
                statusBarHeight: statusBar.height
                onImportRequested: appDialogs.openImportDialog()
                onOpenLocalDatabaseRequested: appDialogs.openLocalDatabaseDialog()
                onCreateDatabaseRequested: appDialogs.openCreateDatabaseDialog()
            }

            WorkspacePage {
                id: workspacePage
                anchors.fill: parent
                backendObject: backend
                windowController: appWindow
                theme: appTheme
                statusBarHeight: statusBar.height
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
