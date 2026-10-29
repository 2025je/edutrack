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
    property int pageSize: 50
    property int pageIndex: 0
    property string currentView: "list"
    property var editingEnrollment: null
    property var pendingEnrollment: null
    property bool editorLoading: false
    property var appliedFilters: ({
        searchQuery: "",
        statusFilterIndex: 0,
        courseFilterId: 0
    })
    property bool filtersUpdating: false
    property bool resettingFilters: false
    readonly property int totalEnrollments: backendObject.enrollments.length
    readonly property var courseFilterOptions: [{
        id: 0,
        label: "Todos los cursos"
    }].concat(backendObject.courses.map(function(course) {
        return {
            id: course.id,
            label: course.label
        }
    }))
    readonly property var filteredEnrollmentRows: {
        var filters = root.appliedFilters
        var query = filters.searchQuery
        return backendObject.enrollments.filter(function(enrollment) {
            if (query) {
                var searchableText = [
                    enrollment.student_label,
                    enrollment.course_label,
                    enrollment.enrollment_date
                ].join(" ").toLowerCase()
                if (searchableText.indexOf(query) < 0)
                    return false
            }

            if (filters.courseFilterId
                    && enrollment.course_id !== filters.courseFilterId)
                return false

            if (filters.statusFilterIndex === 1)
                return enrollment.active
                       && !enrollment.pending_student
                       && !enrollment.pending_course
            if (filters.statusFilterIndex === 2)
                return !enrollment.active
            if (filters.statusFilterIndex === 3)
                return enrollment.pending_student
            if (filters.statusFilterIndex === 4)
                return enrollment.pending_course
            return true
        })
    }
    readonly property int filteredEnrollmentCount: filteredEnrollmentRows.length
    readonly property int pageCount: Math.max(
        1,
        Math.ceil(filteredEnrollmentCount / pageSize)
    )
    readonly property var visibleEnrollmentRows: filteredEnrollmentRows.slice(
        pageIndex * pageSize,
        (pageIndex + 1) * pageSize
    )

    radius: 0
    color: theme.surface
    border.color: theme.outline
    visible: windowController.selectedWorkspaceSection === "Matrículas"
    onPageCountChanged: pageIndex = Math.min(pageIndex, pageCount - 1)

    function scheduleFilterUpdate() {
        root.filtersUpdating = true
        filterUpdateFinishTimer.stop()
        filterApplyTimer.restart()
    }

    function openEnrollmentWizard() {
        root.pendingEnrollment = null
        root.editingEnrollment = null
        enrollmentWizard.begin()
        root.currentView = "wizard"
    }

    function openEnrollmentEditor(enrollment) {
        root.pendingEnrollment = enrollment
        root.editorLoading = true
        editorOpenFinishTimer.stop()
        editorOpenTimer.restart()
    }

    Timer {
        id: editorOpenTimer
        interval: 100
        onTriggered: {
            root.editingEnrollment = root.pendingEnrollment
            root.currentView = "editor"
            editorOpenFinishTimer.restart()
        }
    }

    Timer {
        id: editorOpenFinishTimer
        interval: 300
        onTriggered: root.editorLoading = false
    }

    Timer {
        id: filterApplyTimer
        interval: 80
        onTriggered: {
            root.appliedFilters = {
                searchQuery: enrollmentSearch.text.trim().toLowerCase(),
                statusFilterIndex: statusFilter.currentIndex,
                courseFilterId: root.courseFilterOptions[courseFilter.currentIndex].id
            }
            root.pageIndex = 0
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
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredEnrollmentCount > 0
            clip: true
            spacing: 8
            model: root.visibleEnrollmentRows

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AlwaysOn
                active: true
            }

            delegate: Rectangle {
                required property var modelData
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
                            text: modelData.student_label
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 15
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            text: modelData.course_label
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
                        text: "Fecha: " + modelData.enrollment_date
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
                        color: modelData.pending_student || modelData.pending_course
                               ? root.theme.errorSurface
                               : modelData.active
                                 ? root.theme.successSurface
                                 : root.theme.raisedSurface
                        border.color: modelData.pending_student || modelData.pending_course
                                      ? root.theme.error
                                      : modelData.active
                                        ? root.theme.success
                                        : root.theme.outline

                        Label {
                            anchors.fill: parent
                            anchors.margins: 6
                            text: modelData.pending_student
                                  ? "Pendiente de estudiante"
                                  : modelData.pending_course
                                    ? "Pendiente de curso"
                                    : modelData.active ? "Activa" : "Inactiva"
                            color: modelData.pending_student || modelData.pending_course
                                   ? root.theme.error
                                   : modelData.active
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
                        onClicked: root.openEnrollmentEditor(modelData)
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
                onClicked: root.pageIndex -= 1
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
                onClicked: root.pageIndex += 1
            }

            Item {
                Layout.fillWidth: true
            }
        }
    }

    EnrollmentWizardPage {
        id: enrollmentWizard
        anchors.fill: parent
        visible: root.currentView === "wizard"
        backendObject: root.backendObject
        theme: root.theme
        onCancelRequested: root.currentView = "list"
        onEnrollmentSaved: root.currentView = "list"
    }

    EnrollmentEditorPage {
        id: enrollmentEditor
        anchors.fill: parent
        visible: root.currentView === "editor"
        backendObject: root.backendObject
        enrollment: root.editingEnrollment
        theme: root.theme
        onCancelRequested: {
            root.pendingEnrollment = null
            root.editingEnrollment = null
            root.currentView = "list"
        }
        onEnrollmentSaved: {
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
