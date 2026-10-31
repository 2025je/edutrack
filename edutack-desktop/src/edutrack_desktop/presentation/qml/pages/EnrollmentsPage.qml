import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "../components"

Rectangle {
    id: root
    objectName: "enrollmentsPanel"
    property var backendObject
    property var windowController
    property var theme
    property string currentView: "list"
    property var editingEnrollment: null
    property var pendingEnrollment: null
    property bool editorLoading: false
    property bool filtersUpdating: false
    property bool resettingFilters: false
    readonly property bool hasUnsavedChanges: {
        if (root.currentView === "wizard")
            return enrollmentWizardLoader.item
                    && enrollmentWizardLoader.item.hasUnsavedChanges
        if (root.currentView === "editor")
            return enrollmentEditorLoader.item
                    && enrollmentEditorLoader.item.hasUnsavedChanges
        return false
    }
    readonly property var enrollmentModel: backendObject.enrollmentListModel
    readonly property int totalEnrollments: enrollmentModel.totalCount
    readonly property int filteredEnrollmentCount: enrollmentModel.matchingCount
    readonly property int pageIndex: enrollmentModel.pageIndex
    readonly property int pageCount: enrollmentModel.pageCount
    readonly property var courseFilterOptions: [{
        id: 0,
        label: "Todos los cursos"
    }].concat(backendObject.courses.map(function(course) {
        return {
            id: course.id,
            label: course.label
        }
    }))

    radius: 0
    color: theme.surface
    border.color: theme.outline
    visible: windowController.selectedWorkspaceSection === "Matrículas"
    onVisibleChanged: {
        if (visible)
            enrollmentModel.activate()
    }
    Component.onCompleted: enrollmentModel.activate()
    onCurrentViewChanged: {
        if (currentView !== "editor")
            enrollmentEditorLoader.source = ""
    }

    function scheduleFilterUpdate() {
        root.filtersUpdating = true
        filterUpdateFinishTimer.stop()
        filterApplyTimer.restart()
    }

    function focusSearch() {
        enrollmentSearch.forceActiveFocus()
    }

    function openEnrollmentWizard() {
        root.pendingEnrollment = null
        root.editingEnrollment = null
        root.currentView = "wizard"
    }

    function openEnrollmentEditor(enrollment) {
        root.pendingEnrollment = enrollment
        root.editorLoading = true
        editorOpenTimer.restart()
    }

    Timer {
        id: editorOpenTimer
        interval: 100
        onTriggered: {
            root.editingEnrollment = root.pendingEnrollment
            enrollmentEditorLoader.setSource(
                Qt.resolvedUrl("EnrollmentEditorPage.qml"),
                {
                    backendObject: root.backendObject,
                    enrollment: root.editingEnrollment,
                    theme: root.theme
                }
            )
            root.currentView = "editor"
        }
    }

    Timer {
        id: filterApplyTimer
        interval: 80
        onTriggered: {
            root.enrollmentModel.setFilters(
                enrollmentSearch.text,
                statusFilter.currentIndex,
                root.courseFilterOptions[courseFilter.currentIndex].id
            )
            filterUpdateFinishTimer.start()
        }
    }

    Timer {
        id: filterUpdateFinishTimer
        interval: 250
        onTriggered: root.filtersUpdating = false
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        visible: root.currentView === "list"

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Matrículas"
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 24
                font.bold: true
            }

            Item {
                Layout.fillWidth: true
            }

            Label {
                text: root.filteredEnrollmentCount === root.totalEnrollments
                      ? root.totalEnrollments + " matrículas"
                      : root.filteredEnrollmentCount
                        + " de "
                        + root.totalEnrollments
                        + " matrículas"
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 14
            }

            Button {
                objectName: "matriculateEnrollmentButton"
                text: "Matricular"
                highlighted: true
                font.family: "Roboto"
                onClicked: root.openEnrollmentWizard()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TextField {
                id: enrollmentSearch
                Layout.fillWidth: true
                placeholderText: "Buscar estudiante, curso o fecha..."
                font.family: "Roboto"
                onTextChanged: {
                    if (!root.resettingFilters)
                        root.scheduleFilterUpdate()
                }
            }

            ComboBox {
                id: statusFilter
                Layout.preferredWidth: 190
                model: [
                    "Todos los estados",
                    "Activas",
                    "Inactivas",
                    "Pendiente de estudiante",
                    "Pendiente de curso"
                ]
                currentIndex: 0
                onActivated: function(index) {
                    root.scheduleFilterUpdate()
                }
            }

            ComboBox {
                id: courseFilter
                Layout.preferredWidth: 270
                model: root.courseFilterOptions
                textRole: "label"
                onActivated: function(index) {
                    root.scheduleFilterUpdate()
                }
            }

            Button {
                id: clearFiltersButton
                objectName: "clearEnrollmentFiltersButton"
                text: root.filtersUpdating ? "Filtrando..." : "Limpiar"
                enabled: !root.filtersUpdating
                         && (enrollmentSearch.text.length > 0
                             || statusFilter.currentIndex !== 0
                             || courseFilter.currentIndex !== 0)
                font.family: "Roboto"
                onClicked: {
                    root.resettingFilters = true
                    enrollmentSearch.clear()
                    statusFilter.currentIndex = 0
                    courseFilter.currentIndex = 0
                    root.resettingFilters = false
                    root.scheduleFilterUpdate()
                }

                contentItem: RowLayout {
                    spacing: root.filtersUpdating ? 6 : 0

                    BusyIndicator {
                        Layout.preferredWidth: root.filtersUpdating ? 18 : 0
                        Layout.preferredHeight: 18
                        visible: root.filtersUpdating
                        running: visible
                    }

                    Label {
                        Layout.fillWidth: true
                        text: clearFiltersButton.text
                        color: root.filtersUpdating
                               ? root.theme.accent
                               : clearFiltersButton.enabled
                                 ? root.theme.primaryText
                                 : root.theme.secondaryText
                        font: clearFiltersButton.font
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: root.theme.divider
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredEnrollmentCount === 0
                     && root.enrollmentModel.isLoading
            text: "Cargando matrículas..."
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: root.theme.secondaryText
            font.family: "Roboto"
            font.pixelSize: 16
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredEnrollmentCount === 0
                     && !root.enrollmentModel.isLoading
            text: root.totalEnrollments === 0
                  ? "No hay matrículas registradas."
                  : "No se encontraron matrículas con esos filtros."
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: root.theme.secondaryText
            font.family: "Roboto"
            font.pixelSize: 16
        }

        ListView {
            id: enrollmentList
            objectName: "enrollmentList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredEnrollmentCount > 0
            clip: true
            spacing: 8
            model: root.enrollmentModel

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AlwaysOn
                active: true
            }

            delegate: Rectangle {
                id: enrollmentRow
                objectName: "enrollmentRow_" + enrollmentId
                required property int index
                required property string enrollmentId
                required property string studentLabel
                required property string courseLabel
                required property string enrollmentDate
                required property bool pendingStudent
                required property bool pendingCourse
                required property bool active
                width: enrollmentList.width
                height: 88
                radius: 10
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 16

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: 5

                        Label {
                            Layout.fillWidth: true
                            text: studentLabel
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 15
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            text: courseLabel
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }

                    Label {
                        Layout.preferredWidth: 176
                        Layout.minimumWidth: 176
                        Layout.maximumWidth: 176
                        text: "Fecha: " + enrollmentDate
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }

                    Rectangle {
                        Layout.preferredWidth: 150
                        Layout.minimumWidth: 150
                        Layout.preferredHeight: 30
                        radius: 8
                        color: pendingStudent || pendingCourse
                               ? root.theme.errorSurface
                               : active
                                 ? root.theme.successSurface
                                 : root.theme.raisedSurface
                        border.color: pendingStudent || pendingCourse
                                      ? root.theme.error
                                      : active
                                        ? root.theme.success
                                        : root.theme.outline

                        Label {
                            anchors.fill: parent
                            anchors.margins: 6
                            text: pendingStudent
                                  ? "Pendiente de estudiante"
                                  : pendingCourse
                                    ? "Pendiente de curso"
                                    : active ? "Activa" : "Inactiva"
                            color: pendingStudent || pendingCourse
                                   ? root.theme.error
                                   : active
                                     ? root.theme.success
                                     : root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }

                    Button {
                        objectName: "editEnrollmentButton"
                        text: "Editar"
                        font.family: "Roboto"
                        enabled: !root.backendObject.isBusy
                        onClicked: root.openEnrollmentEditor(
                            root.enrollmentModel.rowAt(enrollmentRow.index)
                        )
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.pageCount > 1

            Item {
                Layout.fillWidth: true
            }

            Button {
                text: "Anterior"
                enabled: root.pageIndex > 0
                font.family: "Roboto"
                onClicked: root.enrollmentModel.setPageIndex(root.pageIndex - 1)
            }

            Label {
                text: "Página " + (root.pageIndex + 1) + " de " + root.pageCount
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 13
            }

            Button {
                text: "Siguiente"
                enabled: root.pageIndex + 1 < root.pageCount
                font.family: "Roboto"
                onClicked: root.enrollmentModel.setPageIndex(root.pageIndex + 1)
            }

            Item {
                Layout.fillWidth: true
            }
        }
    }

    Loader {
        id: enrollmentWizardLoader
        anchors.fill: parent
        active: root.currentView === "wizard"
        asynchronous: true
        sourceComponent: Component {
            EnrollmentWizardPage {
                anchors.fill: parent
                backendObject: root.backendObject
                theme: root.theme
                onCancelRequested: root.currentView = "list"
                onEnrollmentSaved: root.currentView = "list"
            }
        }
        onLoaded: item.begin()
    }

    Loader {
        id: enrollmentEditorLoader
        anchors.fill: parent
        active: root.currentView === "editor"
        asynchronous: true
        onLoaded: {
            root.editorLoading = false
        }
        onStatusChanged: {
            if (status === Loader.Error) {
                root.editorLoading = false
                console.error("No se pudo cargar el editor de matrículas: "
                              + errorString())
                root.currentView = "list"
            }
        }
    }

    Connections {
        target: enrollmentEditorLoader.item
        ignoreUnknownSignals: true

        function onCancelRequested() {
            root.pendingEnrollment = null
            root.editingEnrollment = null
            root.currentView = "list"
        }

        function onEnrollmentSaved() {
            root.pendingEnrollment = null
            root.editingEnrollment = null
            root.currentView = "list"
        }
    }

    DatabaseSavingOverlay {
        objectName: "enrollmentEditorLoadingOverlay"
        backendObject: root.backendObject
        theme: root.theme
        forceVisible: root.editorLoading
        watchBackendActivity: false
        forcedMessage: "Preparando la vista de edición..."
    }
}
