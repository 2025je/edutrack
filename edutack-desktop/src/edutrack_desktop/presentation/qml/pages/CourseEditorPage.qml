import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "../components"

Rectangle {
    id: root
    objectName: "courseEditorPage"
    property var backendObject
    property var course
    property var theme
    property string errorText: ""
    signal cancelRequested()
    signal saveSucceeded()

    function normalizeAmount(field) {
        var match = /^([0-9]+)(?:[.,]([0-9]{1,2}))?$/.exec(field.text.trim())
        if (!match)
            return false
        var decimalPart = match[2] || ""
        while (decimalPart.length < 2)
            decimalPart += "0"
        field.text = match[1] + "." + decimalPart
        return true
    }

    function saveCourse() {
        if (!root.normalizeAmount(enrollmentFeeField)
                || !root.normalizeAmount(monthlyFeeField)) {
            root.errorText = "Ingresa los importes con hasta 2 decimales."
            return
        }
        root.errorText = ""
        var started = root.backendObject.saveCourseAsync(
            root.course.id,
            nameField.text,
            scheduleField.text,
            groupField.text,
            startDateField.value,
            enrollmentFeeField.text,
            monthlyFeeField.text,
            capacityField.text,
            activeCheckBox.checked
        )
        if (!started)
            root.errorText = root.backendObject.errorMessage
    }

    function loadCourse() {
        if (!root.course)
            return
        nameField.text = root.course.name
        scheduleField.text = root.course.schedule
        groupField.text = root.course.group
        startDateField.value = root.course.start_date
        enrollmentFeeField.text = root.course.enrollment_fee
        monthlyFeeField.text = root.course.monthly_fee
        capacityField.text = String(root.course.capacity)
        activeCheckBox.checked = root.course.active
        errorText = ""
    }

    onCourseChanged: loadCourse()
    Component.onCompleted: loadCourse()

    radius: 0
    color: theme.surface
    border.color: theme.outline

    Shortcut {
        sequence: "Ctrl+S"
        enabled: root.visible && !root.backendObject.courseSaveInProgress
                 && !startDateField.popupOpen
        onActivated: root.saveCourse()
    }

    Shortcut {
        sequence: "Esc"
        enabled: root.visible && !startDateField.popupOpen
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
                text: "Volver a cursos"
                onClicked: root.cancelRequested()
            }

            Label {
                Layout.fillWidth: true
                text: "Editar curso"
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
                    text: "Nombre"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: nameField
                    Layout.fillWidth: true
                    maximumLength: 120
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Horario"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: scheduleField
                    Layout.fillWidth: true
                    maximumLength: 120
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Grupo"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: groupField
                    Layout.fillWidth: true
                    maximumLength: 50
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: RegularExpressionValidator {
                        regularExpression: /^[0-9]+$/
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Fecha de inicio"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                DateInput {
                    id: startDateField
                    objectName: "courseStartDate"
                    Layout.fillWidth: true
                    theme: root.theme
                    onDateSelected: root.errorText = ""
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Costo de matrícula"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                MoneySpinBox {
                    id: enrollmentFeeField
                    objectName: "courseEnrollmentFee"
                    Layout.fillWidth: true
                    theme: root.theme
                    onEditingFinished: {
                        if (text.length > 0 && !root.normalizeAmount(enrollmentFeeField))
                            root.errorText = "El costo de matrícula debe tener hasta 2 decimales."
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Mensualidad"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                MoneySpinBox {
                    id: monthlyFeeField
                    objectName: "courseMonthlyFee"
                    Layout.fillWidth: true
                    theme: root.theme
                    onEditingFinished: {
                        if (text.length > 0 && !root.normalizeAmount(monthlyFeeField))
                            root.errorText = "La mensualidad debe tener hasta 2 decimales."
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Capacidad"
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                }
                TextField {
                    id: capacityField
                    Layout.fillWidth: true
                    maximumLength: 10
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: RegularExpressionValidator {
                        regularExpression: /^[0-9]+$/
                    }
                }
            }

            CheckBox {
                id: activeCheckBox
                Layout.columnSpan: 2
                text: "Curso activo"
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
                enabled: !root.backendObject.courseSaveInProgress
                onClicked: root.cancelRequested()
            }

            Button {
                text: "Guardar cambios"
                highlighted: true
                enabled: !root.backendObject.courseSaveInProgress
                onClicked: root.saveCourse()
            }
        }

        Connections {
            target: root.backendObject
            function onCourseSaveFinished(saved) {
                if (saved)
                    root.saveSucceeded()
                else
                    root.errorText = root.backendObject.errorMessage
            }
        }

    }
}
