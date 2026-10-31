import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "studentEditorPage"
    property var backendObject
    property var student
    property var theme
    property string errorText: ""
    signal cancelRequested()
    signal saveSucceeded()

    function loadStudent() {
        lastNameField.clear()
        firstNameField.clear()
        documentField.clear()
        phonesField.clear()
        root.errorText = ""
        if (!root.student)
            return
        lastNameField.text = root.student.last_name
        firstNameField.text = root.student.first_name
        documentField.text = root.student.document_number || ""
        phonesField.text = (root.student.phone_numbers || []).join(", ")
    }

    function saveStudent() {
        root.errorText = ""
        var saved = root.backendObject.saveStudent(
            root.student ? root.student.id : "",
            lastNameField.text,
            firstNameField.text,
            documentField.text,
            phonesField.text
        )
        if (saved)
            root.saveSucceeded()
        else
            root.errorText = root.backendObject.errorMessage
    }

    onStudentChanged: loadStudent()
    Component.onCompleted: loadStudent()

    radius: 0
    color: theme.surface
    border.color: theme.outline

    Shortcut {
        sequence: "Ctrl+S"
        enabled: root.visible
        onActivated: root.saveStudent()
    }

    Shortcut {
        sequence: "Esc"
        enabled: root.visible
        onActivated: root.cancelRequested()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Button {
                text: "Volver a estudiantes"
                onClicked: root.cancelRequested()
            }

            Label {
                Layout.fillWidth: true
                text: root.student ? "Editar estudiante" : "Nuevo estudiante"
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 22
                font.bold: true
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: root.theme.divider
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 20
            rowSpacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Apellidos"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: lastNameField
                    objectName: "studentLastNameField"
                    Layout.fillWidth: true
                    maximumLength: 120
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Nombres"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: firstNameField
                    objectName: "studentFirstNameField"
                    Layout.fillWidth: true
                    maximumLength: 120
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Documento (opcional)"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: documentField
                    objectName: "studentDocumentField"
                    Layout.fillWidth: true
                    maximumLength: 50
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Teléfonos, separados por comas"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: phonesField
                    objectName: "studentPhonesField"
                    Layout.fillWidth: true
                    maximumLength: 250
                }
            }
        }

        Label {
            Layout.fillWidth: true
            visible: root.errorText.length > 0
            text: root.errorText
            color: root.theme.error
            font.family: "Roboto"
            wrapMode: Text.Wrap
        }

        Item {
            Layout.fillHeight: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Item {
                Layout.fillWidth: true
            }

            Button {
                text: "Cancelar"
                onClicked: root.cancelRequested()
            }

            Button {
                objectName: "studentEditorSaveButton"
                text: root.student ? "Guardar cambios" : "Guardar estudiante"
                highlighted: true
                onClicked: root.saveStudent()
            }
        }
    }
}
