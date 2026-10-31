import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "../components"

RowLayout {
    id: workspaceNavigation
    objectName: "workspaceNavigation"
    property var backendObject
    property var windowController
    property var theme
    property real statusBarHeight: 38
    property string studentSearchText: ""
    property string pendingPageAction: ""
    property string pendingPageActionSection: ""
    property bool enrollmentsPageLoaded: false
    property bool studentsPageLoaded: false
    property bool coursesPageLoaded: false
    property bool summaryPageLoaded: false
    property bool syncPageLoaded: false
    property bool backupsPageLoaded: false

    function ensureSectionLoaded(section) {
        if (section === "Matrículas")
            enrollmentsPageLoaded = true
        else if (section === "Estudiantes")
            studentsPageLoaded = true
        else if (section === "Sincronización")
            syncPageLoaded = true
        else if (section === "Cursos" && !coursesPageLoaded) {
            coursesPageLoaded = true
            coursesPageLoader.setSource(
                Qt.resolvedUrl("CoursesPage.qml"),
                {
                    backendObject: backendObject,
                    windowController: windowController,
                    theme: theme
                }
            )
        } else if (section === "Resumen" && !summaryPageLoaded) {
            summaryPageLoaded = true
            summaryPageLoader.setSource(
                Qt.resolvedUrl("SummaryPage.qml"),
                {
                    backendObject: backendObject,
                    windowController: windowController,
                    theme: theme
                }
            )
        } else if (section === "Respaldos" && !backupsPageLoaded) {
            backupsPageLoaded = true
            backupsPageLoader.setSource(
                Qt.resolvedUrl("BackupsPage.qml"),
                {
                    backendObject: backendObject,
                    windowController: windowController,
                    theme: theme
                }
            )
        }
    }

    function pageForSection(section) {
        if (section === "Matrículas")
            return enrollmentsPageLoader.item
        if (section === "Estudiantes")
            return studentsPageLoader.item
        if (section === "Cursos")
            return coursesPageLoader.item
        return null
    }

    function requestPageAction(section, action) {
        pendingPageActionSection = section
        pendingPageAction = action
        windowController.selectedWorkspaceSection = section
        ensureSectionLoaded(section)
        Qt.callLater(dispatchPendingPageAction)
    }

    function dispatchPendingPageAction() {
        if (!pendingPageAction)
            return
        var page = pageForSection(pendingPageActionSection)
        if (!page)
            return

        var action = pendingPageAction
        pendingPageAction = ""
        pendingPageActionSection = ""
        if (action === "newStudent")
            page.openNewStudent()
        else if (action === "newEnrollment")
            page.openEnrollmentWizard()
        else if (action === "focusSearch")
            page.focusSearch()
    }

    function openNewStudent() {
        requestPageAction("Estudiantes", "newStudent")
    }

    function openNewEnrollment() {
        requestPageAction("Matrículas", "newEnrollment")
    }

    function focusCurrentSearch() {
        var section = windowController.selectedWorkspaceSection
        if (section !== "Estudiantes" && section !== "Matrículas"
                && section !== "Cursos")
            section = "Estudiantes"
        requestPageAction(section, "focusSearch")
    }

    anchors.fill: parent
    anchors.margins: 16
    anchors.bottomMargin: statusBarHeight + 32
    spacing: 16
    visible: backendObject.hasWorkspace && !windowController.creatingCampus

    Component.onCompleted: ensureSectionLoaded(windowController.selectedWorkspaceSection)

    ScrollView {
        id: workspaceSidebar
        objectName: "workspaceSidebarScroll"
        Layout.preferredWidth: 152
        Layout.fillHeight: true
        clip: true
        contentWidth: availableWidth
        contentHeight: sidebarButtons.implicitHeight + 20
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        background: Rectangle {
            radius: 0
            color: windowController.surfaceColor
            border.color: windowController.borderColor
        }

        ColumnLayout {
            id: sidebarButtons
            width: workspaceSidebar.availableWidth - 20
            x: 10
            y: 10
            spacing: 8

            Repeater {
                model: [
                    { label: "Matrículas", symbol: "assignment" },
                    { label: "Estudiantes", symbol: "groups" },
                    { label: "Cursos", symbol: "menu_book" },
                    { label: "Sincronización", symbol: "sync" },
                    { label: "Respaldos", symbol: "backup" },
                    { label: "Resumen", symbol: "event" }
                ]

                delegate: Button {
                    id: sectionButton
                    objectName: "workspaceSectionButton_" + modelData.label
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(
                        72,
                        Math.min(96, (workspaceNavigation.height - 64) / 6)
                    )
                    padding: 0
                    property bool selected: windowController.selectedWorkspaceSection
                                            === modelData.label
                    Material.foreground: windowController.primaryTextColor
                    contentItem: ColumnLayout {
                        spacing: 2
                        MaterialSymbol {
                            Layout.alignment: Qt.AlignHCenter
                            symbolName: sectionButton.modelData.symbol
                            symbolSize: 32
                            symbolColor: sectionButton.selected
                                          ? windowController.accentTextColor
                                          : windowController.secondaryTextColor
                        }
                        Label {
                            objectName: "workspaceSectionLabel_"
                                          + sectionButton.modelData.label
                            Layout.fillWidth: true
                            text: sectionButton.modelData.label
                            horizontalAlignment: Text.AlignHCenter
                            color: windowController.primaryTextColor
                            font.family: "Roboto"
                            font.pixelSize: 14
                            font.bold: sectionButton.selected
                            elide: Text.ElideRight
                        }
                    }
                    background: Rectangle {
                        radius: 12
                        color: sectionButton.selected
                               ? windowController.accentSurfaceColor
                               : sectionButton.down
                                 ? windowController.accentSurfaceColor
                                 : sectionButton.hovered
                                   ? windowController.nestedSurfaceColor
                                   : windowController.surfaceColor
                        border.color: sectionButton.selected
                                      ? windowController.accentTextColor
                                      : windowController.borderColor
                    }
                    onClicked: {
                        workspaceNavigation.pendingPageAction = ""
                        workspaceNavigation.pendingPageActionSection = ""
                        windowController.selectedWorkspaceSection =
                                sectionButton.modelData.label
                        workspaceNavigation.ensureSectionLoaded(
                            sectionButton.modelData.label
                        )
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }
        }
    }

    ScrollView {
        id: workspacePanelScroll
        objectName: "workspacePanelScroll"
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentWidth: availableWidth
        contentHeight: workspacePanelContent.height
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        Item {
            id: workspacePanelContent
            width: workspacePanelScroll.availableWidth
            height: Math.max(workspaceNavigation.height, 560)

            Loader {
                id: enrollmentsPageLoader
                objectName: "enrollmentsPageLoader"
                anchors.fill: parent
                active: windowController.selectedWorkspaceSection === "Matrículas"
                        || workspaceNavigation.enrollmentsPageLoaded
                visible: windowController.selectedWorkspaceSection === "Matrículas"
                asynchronous: true
                sourceComponent: Component {
                    EnrollmentsPage {
                        anchors.fill: parent
                        backendObject: workspaceNavigation.backendObject
                        windowController: workspaceNavigation.windowController
                        theme: workspaceNavigation.theme
                    }
                }
                onLoaded: {
                    workspaceNavigation.enrollmentsPageLoaded = true
                    workspaceNavigation.dispatchPendingPageAction()
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    visible: enrollmentsPageLoader.status === Loader.Loading

                    BusyIndicator {
                        Layout.alignment: Qt.AlignHCenter
                        running: enrollmentsPageLoader.status === Loader.Loading
                    }

                    Label {
                        text: "Cargando matrículas..."
                        color: workspaceNavigation.windowController.secondaryTextColor
                    }
                }
            }

            Loader {
                id: studentsPageLoader
                anchors.fill: parent
                active: windowController.selectedWorkspaceSection === "Estudiantes"
                        || workspaceNavigation.studentsPageLoaded
                visible: windowController.selectedWorkspaceSection === "Estudiantes"
                asynchronous: true
                sourceComponent: Component {
                    StudentsPage {
                        anchors.fill: parent
                        backendObject: workspaceNavigation.backendObject
                        windowController: workspaceNavigation.windowController
                        theme: workspaceNavigation.theme
                        Component.onCompleted: studentSearchText = workspaceNavigation.studentSearchText
                        onStudentSearchTextChanged: {
                            workspaceNavigation.studentSearchText = studentSearchText
                        }
                    }
                }
                onLoaded: {
                    workspaceNavigation.studentsPageLoaded = true
                    workspaceNavigation.dispatchPendingPageAction()
                }
            }

            Loader {
                id: coursesPageLoader
                anchors.fill: parent
                active: windowController.selectedWorkspaceSection === "Cursos"
                        || workspaceNavigation.coursesPageLoaded
                visible: windowController.selectedWorkspaceSection === "Cursos"
                asynchronous: true
                onLoaded: {
                    workspaceNavigation.coursesPageLoaded = true
                    workspaceNavigation.dispatchPendingPageAction()
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    visible: coursesPageLoader.status === Loader.Loading

                    BusyIndicator {
                        Layout.alignment: Qt.AlignHCenter
                        running: coursesPageLoader.status === Loader.Loading
                    }

                    Label {
                        text: "Cargando cursos..."
                        color: workspaceNavigation.windowController.secondaryTextColor
                    }
                }
            }

            Loader {
                id: summaryPageLoader
                anchors.fill: parent
                active: windowController.selectedWorkspaceSection === "Resumen"
                        || workspaceNavigation.summaryPageLoaded
                visible: windowController.selectedWorkspaceSection === "Resumen"
                asynchronous: true
                onLoaded: workspaceNavigation.summaryPageLoaded = true

                ColumnLayout {
                    anchors.centerIn: parent
                    visible: summaryPageLoader.status === Loader.Loading

                    BusyIndicator {
                        Layout.alignment: Qt.AlignHCenter
                        running: summaryPageLoader.status === Loader.Loading
                    }

                    Label {
                        text: "Cargando resumen..."
                        color: workspaceNavigation.windowController.secondaryTextColor
                    }
                }
            }

            Loader {
                id: syncPageLoader
                anchors.fill: parent
                active: workspaceNavigation.windowController.selectedWorkspaceSection
                        === "Sincronización" || workspaceNavigation.syncPageLoaded
                visible: workspaceNavigation.windowController.selectedWorkspaceSection
                         === "Sincronización"
                asynchronous: true
                sourceComponent: Component {
                    SyncPage {
                        anchors.fill: parent
                        backendObject: workspaceNavigation.backendObject
                        windowController: workspaceNavigation.windowController
                        theme: workspaceNavigation.theme
                    }
                }
                onLoaded: workspaceNavigation.syncPageLoaded = true
            }

            Loader {
                id: backupsPageLoader
                anchors.fill: parent
                active: workspaceNavigation.windowController.selectedWorkspaceSection
                        === "Respaldos" || workspaceNavigation.backupsPageLoaded
                visible: workspaceNavigation.windowController.selectedWorkspaceSection
                         === "Respaldos"
                asynchronous: true
                sourceComponent: Component {
                    BackupsPage {
                        anchors.fill: parent
                        backendObject: workspaceNavigation.backendObject
                        windowController: workspaceNavigation.windowController
                        theme: workspaceNavigation.theme
                    }
                }
                onLoaded: workspaceNavigation.backupsPageLoaded = true
            }
        }
    }
}
