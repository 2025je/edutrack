import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: wizard

    required property var appWindow
    required property var desktopBackend
    property int step: 0
    property string errorMessage: ""
    property bool sessionOpened: false

    title: step === 0 ? "Nuevo estudiante · Paso 1 de 2"
                      : "Nuevo estudiante · Paso 2 de 2"
    modal: true
    width: Math.min(appWindow.width - 48, 680)
    height: Math.min(appWindow.height - 56, 540)
    anchors.centerIn: parent
    onOpened: sessionOpened = true
    onRejected: sessionOpened = false

    function openWizard() {
        step = 0
        errorMessage = ""
        studentLastName.text = ""
        studentFirstName.text = ""
        studentDocument.text = ""
        studentPhones.text = ""
        sessionOpened = true
        open()
    }

    function cancelWizard() {
        sessionOpened = false
        close()
    }

    function sessionState() {
        return {
            opened: sessionOpened,
            step: step,
            errorMessage: errorMessage,
            lastName: studentLastName.text,
            firstName: studentFirstName.text,
            document: studentDocument.text,
            phones: studentPhones.text
        }
    }

    function restoreSessionState(state) {
        if (!state || typeof state !== "object")
            return
        studentLastName.text = state.lastName || ""
        studentFirstName.text = state.firstName || ""
        studentDocument.text = state.document || ""
        studentPhones.text = state.phones || ""
        step = state.step === 1 ? 1 : 0
        errorMessage = state.errorMessage || ""
        if (state.opened === true)
            sessionOpened = true
        if (state.opened === true)
            open()
    }

    function continueWizard() {
        if (!studentLastName.text.trim() || !studentFirstName.text.trim()) {
            errorMessage = "Ingresa los apellidos y nombres para continuar."
            return
        }
        errorMessage = ""
        step = 1
    }

    function saveStudent() {
        desktopBackend.newStudent()
        desktopBackend.saveStudent(
            "",
            studentLastName.text,
            studentFirstName.text,
            studentDocument.text,
            studentPhones.text
        )
        if (!desktopBackend.selectedStudent.id) {
            errorMessage = desktopBackend.errorMessage
            return
        }
        errorMessage = ""
        sessionOpened = false
        close()
        appWindow.currentPage = 0
    }

    contentItem: ColumnLayout {
        spacing: 12
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: wizard.step
            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 12
                    Label {
                        Layout.fillWidth: true
                        text: "Paso 1 · Datos personales"
                        font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Registra los datos básicos del estudiante."
                        color: appWindow.secondaryTextColor
                        wrapMode: Text.Wrap
                    }
                    UppercaseTextField {
                        id: studentLastName
                        objectName: "studentWizardLastNameField"
                        Layout.fillWidth: true
                        placeholderText: "Apellidos"
                    }
                    UppercaseTextField {
                        id: studentFirstName
                        Layout.fillWidth: true
                        placeholderText: "Nombres"
                    }
                    UppercaseTextField {
                        id: studentDocument
                        Layout.fillWidth: true
                        placeholderText: "DNI (opcional)"
                    }
                    Item { Layout.fillHeight: true }
                }
            }
            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 12
                    Label {
                        Layout.fillWidth: true
                        text: "Paso 2 · Contacto y confirmación"
                        font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true
                        text: studentLastName.text + " "
                              + studentFirstName.text
                              + (studentDocument.text.trim()
                                 ? " · DNI " + studentDocument.text.trim() : "")
                        color: appWindow.primaryTextColor
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                    UppercaseTextField {
                        id: studentPhones
                        Layout.fillWidth: true
                        placeholderText: "Celular(es), separados por coma"
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Ingresa entre 1 y 20 celulares peruanos de 9 dígitos."
                        color: appWindow.secondaryTextColor
                        wrapMode: Text.Wrap
                    }
                    Item { Layout.fillHeight: true }
                }
            }
        }
        Label {
            Layout.fillWidth: true
            visible: wizard.errorMessage.length > 0
            text: wizard.errorMessage
            color: appWindow.errorColor
            wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.fillWidth: true
            Label {
                text: wizard.step === 0 ? "1 de 2 · Datos personales" : "2 de 2 · Contacto"
                color: appWindow.secondaryTextColor
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Cancelar"
                onClicked: wizard.cancelWizard()
            }
            Button {
                visible: wizard.step === 1
                text: "Atrás"
                onClicked: {
                    wizard.step = 0
                    wizard.errorMessage = ""
                }
            }
            Button {
                visible: wizard.step === 0
                text: "Continuar"
                highlighted: true
                onClicked: wizard.continueWizard()
            }
            Button {
                visible: wizard.step === 1
                text: "Guardar estudiante"
                highlighted: true
                onClicked: wizard.saveStudent()
            }
        }
    }
}
