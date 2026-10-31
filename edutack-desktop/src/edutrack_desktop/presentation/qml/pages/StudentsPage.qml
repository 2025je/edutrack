pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "../components"

Rectangle {
    id: studentsPage
    objectName: "studentsPage"
    property var backendObject
    property var windowController
    property var theme
    property alias studentSearchText: studentSearch.text
    property var selectedStudent: null
    property var studentEditorItem: null
    property string currentView: "list"

    function openStudentEditor(student) {
        selectedStudent = student
        currentView = "edit"
    }

    function openNewStudent() {
        backendObject.newStudent()
        openStudentEditor(null)
    }

    function focusSearch() {
        studentSearch.forceActiveFocus()
    }

    function applyStudentFilters() {
        studentSearchDebounce.stop()
        backendObject.studentListModel.setFilters(
            studentSearch.text,
            studentStatusFilter.currentIndex,
            Number(studentCourseFilter.currentValue) || 0
        )
    }

    function closeStudentEditor() {
        selectedStudent = null
        currentView = "list"
    }

    Layout.fillWidth: true
    Layout.fillHeight: true
    visible: studentsPage.windowController.selectedWorkspaceSection === "Estudiantes"
    radius: 0
    color: studentsPage.windowController.surfaceColor
    border.color: studentsPage.windowController.borderColor
    Component.onCompleted: backendObject.studentListModel.activate()

    Timer {
        id: studentSearchDebounce
        interval: 250
        repeat: false
        onTriggered: studentsPage.applyStudentFilters()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        visible: studentsPage.currentView === "list"

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Estudiantes"
                color: studentsPage.windowController.primaryTextColor
                font.family: "Roboto"
                font.pixelSize: 24
                font.bold: true
            }

            Item {
                Layout.fillWidth: true
            }

            Label {
                text: studentsPage.backendObject.studentListModel.matchingCount
                      + " de "
                      + studentsPage.backendObject.studentListModel.totalCount
                      + " estudiantes"
                color: studentsPage.windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 14
            }

            Button {
                objectName: "newStudentButton"
                text: "Nuevo estudiante"
                highlighted: true
                onClicked: studentsPage.openNewStudent()
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            columns: width < 700 ? 1 : 3
            columnSpacing: 8
            rowSpacing: 8

            TextField {
                id: studentSearch
                objectName: "studentSearch"
                Layout.fillWidth: true
                Layout.minimumWidth: 180
                Layout.preferredWidth: 360
                placeholderText: "Buscar por nombre, documento o curso..."
                font.family: "Roboto"
                onTextChanged: studentSearchDebounce.restart()
            }

            ComboBox {
                id: studentStatusFilter
                objectName: "studentStatusFilter"
                Layout.fillWidth: true
                Layout.minimumWidth: 120
                Layout.preferredWidth: 150
                model: ["Todos", "Activos", "Inactivos"]
                font.family: "Roboto"
                onActivated: studentsPage.applyStudentFilters()
            }

            ComboBox {
                id: studentCourseFilter
                objectName: "studentCourseFilter"
                Layout.fillWidth: true
                Layout.minimumWidth: 160
                Layout.preferredWidth: 240
                textRole: "label"
                valueRole: "id"
                model: {
                    var options = [{"id": 0, "label": "Todos los cursos"}]
                    var availableCourses = studentsPage.backendObject.courses
                    for (var index = 0; index < availableCourses.length; index++)
                        options.push({
                            "id": Number(availableCourses[index].id),
                            "label": availableCourses[index].label
                        })
                    return options
                }
                font.family: "Roboto"
                onActivated: studentsPage.applyStudentFilters()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: studentsPage.windowController.dividerColor
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            visible: !studentsList.compactLayout

            Label {
                Layout.fillWidth: true
                text: "ESTUDIANTE"
                color: studentsPage.windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
            }

            Label {
                Layout.preferredWidth: 220
                text: "CURSO(S)"
                color: studentsPage.windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
            }

            Label {
                Layout.preferredWidth: 224
                text: "ACCIONES"
                color: studentsPage.windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: studentsPage.backendObject.studentListModel.matchingCount === 0
            text: studentsPage.backendObject.studentListModel.totalCount === 0
                  && studentSearch.text.trim().length === 0
                  ? "No hay estudiantes registrados."
                  : "No se encontraron estudiantes con ese filtro."
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: studentsPage.windowController.secondaryTextColor
            font.family: "Roboto"
            font.pixelSize: 16
        }

        ListView {
            id: studentsList
            objectName: "studentsList"
            readonly property bool compactLayout: width < 820
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: parent.width
            visible: studentsPage.backendObject.studentListModel.matchingCount > 0
            clip: true
            spacing: 8
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AlwaysOn
                active: true
            }
            model: studentsPage.backendObject.studentListModel

            delegate: Rectangle {
                id: studentRow
                objectName: "studentRow_" + studentId
                required property int index
                required property string studentId
                required property string label
                required property var courses
                required property bool active
                width: studentsList.width
                height: studentsList.compactLayout ? 104 : 72
                radius: 10
                color: studentsPage.windowController.nestedSurfaceColor
                border.color: studentsPage.windowController.borderColor

                RowLayout {
                    visible: !studentsList.compactLayout
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 12
                    spacing: 12

                    Label {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: studentRow.label
                        color: studentsPage.windowController.primaryTextColor
                        font.family: "Roboto"
                        font.pixelSize: 15
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.preferredWidth: 220
                        Layout.minimumWidth: 220
                        Layout.maximumWidth: 220
                        text: (studentRow.courses || []).join(", ")
                        color: studentsPage.windowController.secondaryTextColor
                        font.family: "Roboto"
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }

                    RowLayout {
                        Layout.preferredWidth: 224
                        Layout.minimumWidth: 224
                        Layout.maximumWidth: 224
                        spacing: 6

                        Item {
                            Layout.fillWidth: true
                        }

                        StudentStatusButton {
                            active: studentRow.active
                            theme: studentsPage.theme
                            onStateChangeRequested: function(isActive) {
                                studentsPage.backendObject.setStudentActive(
                                    studentRow.studentId,
                                    isActive
                                )
                            }
                        }

                        Button {
                            id: editStudentButton
                            objectName: "editStudentButton"
                            Layout.preferredWidth: 96
                            Layout.minimumWidth: 96
                            Layout.maximumWidth: 96
                            text: "Editar"
                            font.family: "Roboto"
                            font.pixelSize: 12
                            onClicked: studentsPage.openStudentEditor(
                                studentsPage.backendObject.studentListModel.rowAt(
                                    studentRow.index
                                )
                            )
                        }

                    }
                }

                ColumnLayout {
                    visible: studentsList.compactLayout
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: studentRow.label
                            color: studentsPage.windowController.primaryTextColor
                            font.family: "Roboto"
                            font.pixelSize: 15
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        StudentStatusButton {
                            active: studentRow.active
                            theme: studentsPage.theme
                            onStateChangeRequested: function(isActive) {
                                studentsPage.backendObject.setStudentActive(
                                    studentRow.studentId,
                                    isActive
                                )
                            }
                        }

                        Button {
                            objectName: "editStudentButtonCompact"
                            Layout.preferredWidth: 84
                            Layout.minimumWidth: 84
                            Layout.maximumWidth: 84
                            text: "Editar"
                            font.family: "Roboto"
                            font.pixelSize: 12
                            onClicked: studentsPage.openStudentEditor(
                                studentsPage.backendObject.studentListModel.rowAt(
                                    studentRow.index
                                )
                            )
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: (studentRow.courses || []).length
                              ? (studentRow.courses || []).join(", ")
                              : "Sin matrículas activas"
                        color: studentsPage.windowController.secondaryTextColor
                        font.family: "Roboto"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: studentsPage.backendObject.studentListModel.pageCount > 1

            Item {
                Layout.fillWidth: true
            }

            Button {
                text: "Anterior"
                enabled: studentsPage.backendObject.studentListModel.pageIndex > 0
                font.family: "Roboto"
                onClicked: studentsPage.backendObject.studentListModel.setPageIndex(
                               studentsPage.backendObject.studentListModel.pageIndex - 1
                           )
            }

            Label {
                text: "Página "
                      + (studentsPage.backendObject.studentListModel.pageIndex + 1)
                      + " de "
                      + studentsPage.backendObject.studentListModel.pageCount
                color: studentsPage.windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 13
            }

            Button {
                text: "Siguiente"
                enabled: studentsPage.backendObject.studentListModel.pageIndex + 1
                         < studentsPage.backendObject.studentListModel.pageCount
                font.family: "Roboto"
                onClicked: studentsPage.backendObject.studentListModel.setPageIndex(
                               studentsPage.backendObject.studentListModel.pageIndex + 1
                           )
            }

            Item {
                Layout.fillWidth: true
            }

        }
    }

    Loader {
        id: studentEditorLoader
        objectName: "studentEditorLoader"
        anchors.fill: parent
        active: studentsPage.currentView === "edit"
        asynchronous: true
        sourceComponent: Component {
            StudentEditorPage {
                anchors.fill: parent
                backendObject: studentsPage.backendObject
                theme: studentsPage.theme
                onCancelRequested: studentsPage.closeStudentEditor()
                onSaveSucceeded: studentsPage.closeStudentEditor()
            }
        }
        onLoaded: {
            studentsPage.studentEditorItem = item
            studentsPage.studentEditorItem.student = studentsPage.selectedStudent
        }
        onStatusChanged: {
            if (status === Loader.Null) {
                studentsPage.studentEditorItem = null
            } else if (status === Loader.Error) {
                studentsPage.studentEditorItem = null
                console.error("No se pudo cargar el editor de estudiantes: "
                              + errorString())
                studentsPage.closeStudentEditor()
            }
        }
    }

    ColumnLayout {
        anchors.centerIn: parent
        visible: studentEditorLoader.status === Loader.Loading

        BusyIndicator {
            Layout.alignment: Qt.AlignHCenter
            running: studentEditorLoader.status === Loader.Loading
        }

        Label {
            text: "Cargando editor de estudiantes..."
            color: studentsPage.windowController.secondaryTextColor
        }
    }

}
