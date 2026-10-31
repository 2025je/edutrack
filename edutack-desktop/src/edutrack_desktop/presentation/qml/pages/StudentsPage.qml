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
                text: windowController.matchingStudentCount + " estudiantes"
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
                windowController.studentPageIndex = 0
                windowController.refreshStudentPage(studentSearch.text)
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
            visible: windowController.visibleStudentRows.length === 0
            text: windowController.matchingStudentCount === 0
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
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: windowController.visibleStudentRows.length > 0
            clip: true
            spacing: 8
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AlwaysOn
                active: true
            }
            model: windowController.visibleStudentRows

            delegate: Rectangle {
                required property var modelData
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
                        text: modelData.label
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
                        text: (modelData.courses || []).join(", ")
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
                            active: modelData.active
                            theme: studentsPage.theme
                            onStateChangeRequested: function(isActive) {
                                studentsPage.backendObject.setStudentActive(
                                    modelData.id,
                                    isActive
                                )
                            }
                        }

                        Button {
                            id: editStudentButton
                            Layout.preferredWidth: 96
                            Layout.minimumWidth: 96
                            Layout.maximumWidth: 96
                            text: "Editar"
                            font.family: "Roboto"
                            font.pixelSize: 12
                            onClicked: studentsPage.openStudentEditor(modelData)
                        }

                    }
                }

            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: windowController.matchingStudentCount
                     > windowController.studentPageSize

            Item {
                Layout.fillWidth: true
            }

            Button {
                text: "Anterior"
                enabled: windowController.studentPageIndex > 0
                font.family: "Roboto"
                onClicked: {
                    windowController.studentPageIndex -= 1
                    windowController.refreshStudentPage()
                }
            }

            Label {
                text: "Página " + (windowController.studentPageIndex + 1)
                      + " de "
                      + Math.ceil(
                            windowController.matchingStudentCount
                            / windowController.studentPageSize
                        )
                color: windowController.secondaryTextColor
                font.family: "Roboto"
                font.pixelSize: 13
            }

            Button {
                text: "Siguiente"
                enabled: (windowController.studentPageIndex + 1)
                         * windowController.studentPageSize
                         < windowController.matchingStudentCount
                font.family: "Roboto"
                onClicked: {
                    windowController.studentPageIndex += 1
                    windowController.refreshStudentPage()
                }
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
