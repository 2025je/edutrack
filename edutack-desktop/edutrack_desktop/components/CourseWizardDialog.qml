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

    title: step === 0 ? "Nuevo curso · Paso 1 de 2" : "Nuevo curso · Paso 2 de 2"
    modal: true
    width: Math.min(appWindow.width - 48, 680)
    height: Math.min(appWindow.height - 56, 540)
    anchors.centerIn: parent
    onOpened: sessionOpened = true
    onRejected: sessionOpened = false

    function openWizard() {
        step = 0
        errorMessage = ""
        courseName.text = ""
        courseSchedule.text = ""
        courseGroup.text = "1"
        courseCapacity.text = "20"
        courseStartDate.text = Qt.formatDate(new Date(), "yyyy-MM-dd")
        courseEnrollmentFee.text = ""
        courseMonthlyFee.text = ""
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
            name: courseName.text,
            schedule: courseSchedule.text,
            group: courseGroup.text,
            capacity: courseCapacity.text,
            startDate: courseStartDate.text,
            enrollmentFee: courseEnrollmentFee.text,
            monthlyFee: courseMonthlyFee.text
        }
    }

    function restoreSessionState(state) {
        if (!state || typeof state !== "object")
            return
        courseName.text = state.name || ""
        courseSchedule.text = state.schedule || ""
        courseGroup.text = state.group || "1"
        courseCapacity.text = state.capacity || "20"
        courseStartDate.text = state.startDate || Qt.formatDate(new Date(), "yyyy-MM-dd")
        courseEnrollmentFee.text = state.enrollmentFee || ""
        courseMonthlyFee.text = state.monthlyFee || ""
        step = state.step === 1 ? 1 : 0
        errorMessage = state.errorMessage || ""
        if (state.opened === true)
            open()
    }

    function continueWizard() {
        var group = courseGroup.text.trim()
        if (!courseName.text.trim() || !courseSchedule.text.trim()
                || !/^[0-9]+$/.test(group) || Number(group) < 1) {
            errorMessage = "Ingresa el nombre, horario y un grupo válido para continuar."
            return
        }
        errorMessage = ""
        step = 1
    }

    function saveCourse() {
        var courseId = desktopBackend.createCourse(
            courseName.text,
            courseSchedule.text,
            courseGroup.text,
            courseStartDate.text,
            courseEnrollmentFee.text,
            courseMonthlyFee.text,
            courseCapacity.text
        )
        if (courseId < 1) {
            errorMessage = desktopBackend.errorMessage
            return
        }
        errorMessage = ""
        sessionOpened = false
        close()
        appWindow.currentPage = 2
        desktopBackend.selectCourse(courseId)
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
                        text: "Paso 1 · Información básica"
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Define el nombre, el horario y el grupo del curso."
                        color: appWindow.secondaryTextColor
                        wrapMode: Text.Wrap
                    }
                    UppercaseTextField {
                        id: courseName
                        Layout.fillWidth: true
                        placeholderText: "Nombre del curso"
                    }
                    UppercaseTextField {
                        id: courseSchedule
                        Layout.fillWidth: true
                        placeholderText: "Horario"
                    }
                    UppercaseTextField {
                        id: courseGroup
                        Layout.fillWidth: true
                        text: "1"
                        placeholderText: "Grupo"
                        inputMethodHints: Qt.ImhDigitsOnly
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
                        text: "Paso 2 · Configuración"
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Indica fecha de inicio, capacidad y tarifas."
                        color: appWindow.secondaryTextColor
                        wrapMode: Text.Wrap
                    }
                    DatePickerField {
                        id: courseStartDate
                        Layout.fillWidth: true
                        text: Qt.formatDate(new Date(), "yyyy-MM-dd")
                        placeholderText: "Fecha de inicio (AAAA-MM-DD)"
                    }
                    UppercaseTextField {
                        id: courseCapacity
                        Layout.fillWidth: true
                        text: "20"
                        placeholderText: "Capacidad"
                        inputMethodHints: Qt.ImhDigitsOnly
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        UppercaseTextField {
                            id: courseEnrollmentFee
                            Layout.fillWidth: true
                            placeholderText: "Costo de matrícula"
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                        UppercaseTextField {
                            id: courseMonthlyFee
                            Layout.fillWidth: true
                            placeholderText: "Mensualidad"
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: courseName.text + " · " + courseSchedule.text
                              + " · Grupo " + courseGroup.text
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
                text: wizard.step === 0 ? "1 de 2 · Datos básicos" : "2 de 2 · Configuración"
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
                text: "Crear curso"
                highlighted: true
                onClicked: wizard.saveCourse()
            }
        }
    }
}
