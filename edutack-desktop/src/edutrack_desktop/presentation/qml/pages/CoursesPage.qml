import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "coursesPanel"
    property var backendObject
    property var windowController
    property var theme
    property var selectedCourse: null
    property var courseDetailsItem: null
    property var courseEditorItem: null
    property string currentView: "list"
    readonly property var courseListModel: root.backendObject.courseListModel
    readonly property bool hasUnsavedChanges: currentView === "edit"
                                               && courseEditorItem
                                               && courseEditorItem.hasUnsavedChanges

    function focusSearch() {
        courseSearch.forceActiveFocus()
    }

    radius: 0
    color: theme.surface
    border.color: theme.outline
    visible: windowController.selectedWorkspaceSection === "Cursos"
    onVisibleChanged: {
        if (visible)
            root.courseListModel.activate()
    }

    Component.onCompleted: {
        if (visible)
            root.courseListModel.activate()
    }

    Timer {
        id: courseSearchTimer
        interval: 120
        onTriggered: root.courseListModel.setQuery(courseSearch.text)
    }

    ColumnLayout {
        id: coursesListView
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        visible: root.currentView === "list"

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Cursos"
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 24
                font.bold: true
            }

            Item {
                Layout.fillWidth: true
            }

            Label {
                text: root.courseListModel.matchingCount
                      === root.courseListModel.totalCount
                      ? root.courseListModel.totalCount + " cursos"
                      : root.courseListModel.matchingCount + " de "
                        + root.courseListModel.totalCount + " cursos"
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 14
            }
        }

        TextField {
            id: courseSearch
            objectName: "courseSearchField"
            Layout.fillWidth: true
            placeholderText: "Buscar por curso, horario, grupo o fecha..."
            onTextChanged: courseSearchTimer.restart()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: root.theme.divider
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.courseListModel.matchingCount === 0
                     && root.courseListModel.isLoading
            text: "Cargando cursos..."
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: root.theme.secondaryText
            font.family: "Roboto"
            font.pixelSize: 16
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.courseListModel.matchingCount === 0
                     && !root.courseListModel.isLoading
            text: root.courseListModel.totalCount === 0
                  ? "No hay cursos registrados."
                  : "No se encontraron cursos con ese filtro."
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: root.theme.secondaryText
            font.family: "Roboto"
            font.pixelSize: 16
        }

        Flickable {
            id: coursesFlickable
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.courseListModel.matchingCount > 0
            clip: true
            contentWidth: width
            contentHeight: coursesContent.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            ColumnLayout {
                id: coursesContent
                width: coursesFlickable.width
                spacing: 20

                Repeater {
                    model: root.courseListModel

                    delegate: ColumnLayout {
                        required property string weekLabel
                        required property var courses
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.maximumWidth: coursesFlickable.width
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true

                            Label {
                                text: weekLabel
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 13
                                font.bold: true
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: root.theme.divider
                            }

                            Label {
                                text: courses.length + " cursos"
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 12
                            }
                        }

                        Repeater {
                            model: courses

                            delegate: Rectangle {
                                id: courseCard
                                required property var modelData
                                readonly property bool full: modelData.capacity > 0
                                                               && modelData.student_count
                                                                  >= modelData.capacity
                                readonly property bool compact:
                                    coursesFlickable.width < 820
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.maximumWidth: coursesFlickable.width
                                Layout.preferredHeight: compact ? 124 : 76
                                radius: 10
                                color: full ? root.theme.successSurface
                                            : root.theme.raisedSurface
                                border.color: full ? root.theme.success
                                                   : root.theme.outline

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: courseCard.compact ? 10 : 12
                                    spacing: courseCard.compact ? 5 : 0

                                    RowLayout {
                                        visible: !courseCard.compact
                                        Layout.fillWidth: true
                                        spacing: 10

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            spacing: 4

                                            Label {
                                                Layout.minimumWidth: 0
                                                Layout.fillWidth: true
                                                text: modelData.name
                                                color: root.theme.primaryText
                                                font.family: "Roboto"
                                                font.pixelSize: 15
                                                font.bold: true
                                                elide: Text.ElideRight
                                            }

                                            Label {
                                                Layout.minimumWidth: 0
                                                Layout.fillWidth: true
                                                text: modelData.schedule
                                                color: root.theme.secondaryText
                                                font.family: "Roboto"
                                                font.pixelSize: 13
                                                elide: Text.ElideRight
                                            }
                                        }

                                        Label {
                                            Layout.preferredWidth: 76
                                            text: "Grupo " + modelData.group
                                            color: root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 13
                                            elide: Text.ElideRight
                                        }

                                        ColumnLayout {
                                            Layout.preferredWidth: 150
                                            Layout.minimumWidth: 125
                                            spacing: 4

                                            Label {
                                                Layout.fillWidth: true
                                                text: "Inicio: " + modelData.start_date
                                                color: root.theme.secondaryText
                                                font.family: "Roboto"
                                                font.pixelSize: 12
                                                elide: Text.ElideRight
                                            }

                                            Label {
                                                Layout.fillWidth: true
                                                text: modelData.student_count
                                                      + " / "
                                                      + modelData.capacity
                                                      + " estudiantes"
                                                color: courseCard.full
                                                       ? root.theme.success
                                                       : root.theme.secondaryText
                                                font.family: "Roboto"
                                                font.pixelSize: 12
                                                font.bold: courseCard.full
                                                elide: Text.ElideRight
                                            }
                                        }

                                        Label {
                                            text: modelData.active ? "Activo" : "Inactivo"
                                            color: modelData.active
                                                   ? root.theme.success
                                                   : root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                        }

                                        Button {
                                            Layout.preferredWidth: 68
                                            text: "Ver"
                                            onClicked: {
                                                root.backendObject.selectCourse(
                                                    courseCard.modelData.id
                                                )
                                                root.selectedCourse = courseCard.modelData
                                                root.currentView = "details"
                                            }
                                        }

                                        Button {
                                            objectName: "editCourseButtonWide_"
                                                        + modelData.id
                                            Layout.preferredWidth: 78
                                            text: "Editar"
                                            onClicked: {
                                                root.backendObject.selectCourse(
                                                    courseCard.modelData.id
                                                )
                                                root.selectedCourse = courseCard.modelData
                                                root.currentView = "edit"
                                            }
                                        }
                                    }

                                    RowLayout {
                                        visible: courseCard.compact
                                        Layout.fillWidth: true

                                        Label {
                                            Layout.minimumWidth: 0
                                            Layout.fillWidth: true
                                            text: modelData.name
                                            color: root.theme.primaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 15
                                            font.bold: true
                                            elide: Text.ElideRight
                                        }

                                        Label {
                                            text: "Grupo " + modelData.group
                                            color: root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 13
                                        }
                                    }

                                    RowLayout {
                                        visible: courseCard.compact
                                        Layout.fillWidth: true

                                        Label {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: modelData.schedule
                                            color: root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 13
                                            elide: Text.ElideRight
                                        }

                                        Label {
                                            text: "Inicio: " + modelData.start_date
                                            color: root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                        }
                                    }

                                    RowLayout {
                                        visible: courseCard.compact
                                        Layout.fillWidth: true

                                        Label {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: modelData.student_count
                                                  + " / "
                                                  + modelData.capacity
                                                  + " estudiantes"
                                            color: courseCard.full
                                                   ? root.theme.success
                                                   : root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                            font.bold: courseCard.full
                                            elide: Text.ElideRight
                                        }

                                        Label {
                                            text: modelData.active ? "Activo" : "Inactivo"
                                            color: modelData.active
                                                   ? root.theme.success
                                                   : root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                        }

                                        Button {
                                            Layout.preferredWidth: 64
                                            text: "Ver"
                                            onClicked: {
                                                root.backendObject.selectCourse(
                                                    courseCard.modelData.id
                                                )
                                                root.selectedCourse = courseCard.modelData
                                                root.currentView = "details"
                                            }
                                        }

                                        Button {
                                            objectName: "editCourseButtonCompact_"
                                                        + modelData.id
                                            Layout.preferredWidth: 76
                                            text: "Editar"
                                            onClicked: {
                                                root.backendObject.selectCourse(
                                                    courseCard.modelData.id
                                                )
                                                root.selectedCourse = courseCard.modelData
                                                root.currentView = "edit"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.courseListModel.pageCount > 1

            Button {
                text: "Anterior"
                enabled: root.courseListModel.pageIndex > 0
                onClicked: root.courseListModel.setPageIndex(
                               root.courseListModel.pageIndex - 1
                           )
            }

            Label {
                Layout.fillWidth: true
                text: "Página " + (root.courseListModel.pageIndex + 1)
                      + " de " + root.courseListModel.pageCount
                color: root.theme.secondaryText
                horizontalAlignment: Text.AlignHCenter
            }

            Button {
                text: "Siguiente"
                enabled: root.courseListModel.pageIndex
                         < root.courseListModel.pageCount - 1
                onClicked: root.courseListModel.setPageIndex(
                               root.courseListModel.pageIndex + 1
                           )
            }
        }
    }

    Loader {
        id: courseDetailsLoader
        objectName: "courseDetailsLoader"
        anchors.fill: parent
        active: root.currentView === "details"
        asynchronous: true
        sourceComponent: Component {
            CourseDetailsPage {
                anchors.fill: parent
                theme: root.theme
                onBackRequested: {
                    root.selectedCourse = null
                    root.currentView = "list"
                }
            }
        }
        onLoaded: {
            root.courseDetailsItem = item
            root.courseDetailsItem.course = root.selectedCourse
            root.courseDetailsItem.students = root.backendObject.courseStudents
        }
        onStatusChanged: {
            if (status === Loader.Null) {
                root.courseDetailsItem = null
            } else if (status === Loader.Error) {
                root.courseDetailsItem = null
                console.error("No se pudo cargar el detalle del curso: "
                              + errorString())
                root.selectedCourse = null
                root.currentView = "list"
            }
        }
    }

    Loader {
        id: courseEditorLoader
        objectName: "courseEditorLoader"
        anchors.fill: parent
        active: root.currentView === "edit"
        asynchronous: true
        sourceComponent: Component {
            CourseEditorPage {
                anchors.fill: parent
                backendObject: root.backendObject
                theme: root.theme
                onCancelRequested: {
                    root.selectedCourse = null
                    root.currentView = "list"
                }
                onSaveSucceeded: {
                    root.selectedCourse = null
                    root.currentView = "list"
                }
            }
        }
        onLoaded: {
            root.courseEditorItem = item
            root.courseEditorItem.course = root.selectedCourse
        }
        onStatusChanged: {
            if (status === Loader.Null) {
                root.courseEditorItem = null
            } else if (status === Loader.Error) {
                root.courseEditorItem = null
                console.error("No se pudo cargar el editor de cursos: "
                              + errorString())
                root.selectedCourse = null
                root.currentView = "list"
            }
        }
    }

    ColumnLayout {
        anchors.centerIn: parent
        visible: (root.currentView === "details"
                  && courseDetailsLoader.status === Loader.Loading)
                 || (root.currentView === "edit"
                     && courseEditorLoader.status === Loader.Loading)

        BusyIndicator {
            Layout.alignment: Qt.AlignHCenter
            running: parent.visible
        }

        Label {
            text: root.currentView === "edit"
                  ? "Cargando editor de cursos..."
                  : "Cargando curso..."
            color: root.windowController.secondaryTextColor
        }
    }
}
