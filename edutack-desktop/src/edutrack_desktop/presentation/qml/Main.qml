import QtQuick
import QtQuick.Controls.Material
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"
import "dialogs"

ApplicationWindow {
    id: appWindow
    width: 1280
    height: 740
    minimumWidth: 980
    minimumHeight: 620
    visible: false
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
    property var desktopBackend: null
    property bool restoringSession: false
    property bool sessionTrackingEnabled: false
    property string sessionSnapshot: sessionTrackingEnabled
                                         ? JSON.stringify(collectSessionState()) : ""
    property bool creatingCampus: false
    property string selectedWorkspaceSection: "Resumen"
    property bool startupComplete: false
    property bool closeAfterCurrentOperation: false
    property int studentPageIndex: 0
    property int studentPageSize: 50
    property int matchingStudentCount: 0
    property var visibleStudentRows: []
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
            window: {
                x: appWindow.x,
                y: appWindow.y,
                width: appWindow.width,
                height: appWindow.height
            },
            creatingCampus: appWindow.creatingCampus,
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

    function requestClose() {
        if (backend.isBusy) {
            appWindow.closeAfterCurrentOperation = true
            return
        }
        appWindow.close()
    }

    function refreshStudentPage(searchText) {
        var query = searchText === undefined ? workspacePage.studentSearchText : searchText
        appWindow.matchingStudentCount = backend.matchingStudentCount(query)
        var pageCount = Math.max(
            1,
            Math.ceil(appWindow.matchingStudentCount / appWindow.studentPageSize)
        )
        appWindow.studentPageIndex = Math.min(
            appWindow.studentPageIndex,
            pageCount - 1
        )
        appWindow.visibleStudentRows = backend.studentPage(
            query,
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
            appWindow.restoreSessionState()
            appWindow.refreshStudentPage()
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
        windowController: appWindow
        closePending: appWindow.closeAfterCurrentOperation
        startupComplete: appWindow.startupComplete
        onCloseRequested: appWindow.requestClose()
    }

    WindowResizeHandles {
        anchors.fill: parent
        windowController: appWindow
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 16

        WindowTitleBar {
            Layout.fillWidth: true
            windowController: appWindow
            backendObject: backend
            theme: appTheme
            onCloseCampusRequested: appDialogs.openCloseCampusDialog()
            onDarkModeToggleRequested: appWindow.darkMode = !appWindow.darkMode
            onExportRequested: appDialogs.openExportDialog()
            onMinimizeRequested: appWindow.visibility = Window.Minimized
            onMaximizeRequested: appWindow.toggleMaximized()
            onCloseRequested: appWindow.requestClose()
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
        windowController: appWindow
        allowCloseRequest: true
        closePending: appWindow.closeAfterCurrentOperation
        onCloseRequested: appWindow.requestClose()
    }
}
