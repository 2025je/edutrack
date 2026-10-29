import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "courseEditorPage"
    property var backendObject
    property var course
    property var theme
    property string errorText: ""
    readonly property var monthNames: [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    signal cancelRequested()
    signal saveSucceeded()

    function dateFromIso(value) {
        var dateText = String(value || "")
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText))
            return null
        var parts = dateText.split("-")
        var parsed = new Date(
            Number(parts[0]),
            Number(parts[1]) - 1,
            Number(parts[2])
        )
        if (parsed.getFullYear() !== Number(parts[0])
                || parsed.getMonth() !== Number(parts[1]) - 1
                || parsed.getDate() !== Number(parts[2]))
            return null
        return parsed
    }

    function isoDate(value) {
        var month = ("0" + (value.getMonth() + 1)).slice(-2)
        var day = ("0" + value.getDate()).slice(-2)
        return value.getFullYear() + "-" + month + "-" + day
    }

    function changeCalendarMonth(offset) {
        var nextMonth = new Date(
            startDatePopup.displayedYear,
            startDatePopup.displayedMonth + offset,
            1
        )
        startDatePopup.displayedYear = nextMonth.getFullYear()
        startDatePopup.displayedMonth = nextMonth.getMonth()
    }

    function selectStartDate(value) {
        startDateField.text = root.isoDate(value)
        root.errorText = ""
        startDatePopup.close()
    }

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

    function loadCourse() {
        if (!root.course)
            return
        nameField.text = root.course.name
        scheduleField.text = root.course.schedule
        groupField.text = root.course.group
        startDateField.text = root.course.start_date
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
                RowLayout {
                    Layout.fillWidth: true

                    TextField {
                        id: startDateField
                        Layout.fillWidth: true
                        readOnly: true
                        placeholderText: "AAAA-MM-DD"
                        maximumLength: 10
                    }

                    Button {
                        text: "Calendario"
                        onClicked: startDatePopup.open()
                    }
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
                TextField {
                    id: enrollmentFeeField
                    Layout.fillWidth: true
                    maximumLength: 11
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: RegularExpressionValidator {
                        regularExpression: /^[0-9]+([.,][0-9]{0,2})?$/
                    }
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
                TextField {
                    id: monthlyFeeField
                    Layout.fillWidth: true
                    maximumLength: 11
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: RegularExpressionValidator {
                        regularExpression: /^[0-9]+([.,][0-9]{0,2})?$/
                    }
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
                onClicked: {
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
                        startDateField.text,
                        enrollmentFeeField.text,
                        monthlyFeeField.text,
                        capacityField.text,
                        activeCheckBox.checked
                    )
                    if (!started)
                        root.errorText = root.backendObject.errorMessage
                }
            }
        }

        Popup {
            id: startDatePopup
            objectName: "startDatePopup"
            modal: true
            focus: true
            width: 360
            height: 410
            padding: 12
            anchors.centerIn: Overlay.overlay
            property int displayedYear: new Date().getFullYear()
            property int displayedMonth: new Date().getMonth()
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

            onOpened: {
                var selectedDate = root.dateFromIso(startDateField.text)
                var date = selectedDate || new Date()
                displayedYear = date.getFullYear()
                displayedMonth = date.getMonth()
            }

            contentItem: ColumnLayout {
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: "Anterior"
                        onClicked: root.changeCalendarMonth(-1)
                    }

                    Label {
                        Layout.fillWidth: true
                        text: root.monthNames[startDatePopup.displayedMonth]
                              + " " + startDatePopup.displayedYear
                        horizontalAlignment: Text.AlignHCenter
                        color: root.theme.primaryText
                        font.family: "Roboto"
                        font.bold: true
                    }

                    Button {
                        text: "Siguiente"
                        onClicked: root.changeCalendarMonth(1)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Repeater {
                        model: ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

                        delegate: Label {
                            required property var modelData
                            Layout.fillWidth: true
                            text: modelData
                            horizontalAlignment: Text.AlignHCenter
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }
                }

                MonthGrid {
                    id: startDateCalendar
                    Layout.fillWidth: true
                    Layout.preferredHeight: 260
                    month: startDatePopup.displayedMonth
                    year: startDatePopup.displayedYear
                    locale: Qt.locale("es_PE")

                    delegate: Button {
                        required property var model
                        implicitWidth: 40
                        implicitHeight: 36
                        text: String(model.day)
                        enabled: model.month === startDateCalendar.month
                        flat: true
                        highlighted: root.isoDate(model.date) === startDateField.text
                        onClicked: root.selectStartDate(model.date)
                    }
                }
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
