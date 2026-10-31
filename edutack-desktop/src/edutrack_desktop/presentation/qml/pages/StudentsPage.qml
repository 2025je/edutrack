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

    function closeStudentEditor() {
        selectedStudent = null
        currentView = "list"
    }

    Layout.fillWidth: true
    Layout.fillHeight: true
    visible: windowController.selectedWorkspaceSection === "Estudiantes"
    radius: 0
    color: windowController.surfaceColor
    border.color: windowController.borderColor
    Component.onCompleted: backendObject.studentListModel.activate()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        visible: studentsPage.currentView === "list"

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Estudiantes"
                color: windowController.primaryTextColor
                font.family: "Roboto"
                font.pixelSize: 24
                font.bold: true
            }

            Item {
                Layout.fillWidth: true
            }

            Label {
                text: studentsPage.backendObject.studentListModel.matchingCount
                      + " estudiantes"
                color: windowController.secondaryTextColor
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

        TextField {
            id: studentSearch
            Layout.fillWidth: true
            placeholderText: "Buscar por nombre, documento o curso..."
            font.family: "Roboto"
            onTextChanged: {
                studentsPage.backendObject.studentListModel.setQuery(
                    studentSearch.text
                )
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: windowController.dividerColor
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: "ESTUDIANTE"
                color: windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
            }

            Label {
                Layout.preferredWidth: 220
                text: "CURSO(S)"
                color: windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
            }

            Label {
                Layout.preferredWidth: 224
                text: "ACCIONES"
                color: windowController.secondaryTextColor
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
            color: windowController.secondaryTextColor
            font.family: "Roboto"
            font.pixelSize: 16
        }

        ListView {
            id: studentsList
            objectName: "studentsList"
            Layout.fillWidth: true
            Layout.fillHeight: true
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
                height: 72
                radius: 10
                color: windowController.nestedSurfaceColor
                border.color: windowController.borderColor

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 12
                    spacing: 12

                    Label {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: label
                        color: windowController.primaryTextColor
                        font.family: "Roboto"
                        font.pixelSize: 15
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.preferredWidth: 220
                        Layout.minimumWidth: 220
                        Layout.maximumWidth: 220
                        text: (courses || []).join(", ")
                        color: windowController.secondaryTextColor
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
                                    studentId,
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
                color: windowController.secondaryTextColor
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

    StudentEditorPage {
        anchors.fill: parent
        visible: studentsPage.currentView === "edit"
        backendObject: studentsPage.backendObject
        student: studentsPage.selectedStudent
        theme: studentsPage.theme
        onCancelRequested: studentsPage.closeStudentEditor()
        onSaveSucceeded: studentsPage.closeStudentEditor()
    }

}
