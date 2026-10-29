import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "enrollmentEditorPage"
    property var backendObject
    property var enrollment
    property var theme
    property string errorText: ""
    property var selectedStudentId: ""
    property var selectedCourseId: ""
    property string studentSearchQuery: ""
    property string courseSearchQuery: ""
    readonly property var monthNames: [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    readonly property var studentOptions: {
        var options = root.backendObject
                      ? root.backendObject.studentOptions.slice()
                      : []
        var studentId = root.enrollment ? root.enrollment.student_id : ""
        if (studentId
                && !options.some(function(option) {
                    return String(option.id) === String(studentId)
                })) {
            options.push({
                id: studentId,
                label: "Estudiante no disponible",
                active: false,
                missing: true
            })
        }
        return options
    }
    readonly property var filteredStudentOptions: {
        var query = root.studentSearchQuery.trim().toLowerCase()
        return root.studentOptions.filter(function(option) {
            var searchableText = [
                option.label,
                option.last_name,
                option.first_name,
                option.document_number
            ].join(" ").toLowerCase()
            return searchableText.indexOf(query) >= 0
        })
    }
    readonly property var filteredCourseOptions: {
        var query = root.courseSearchQuery.trim().toLowerCase()
        return root.courseOptions.filter(function(option) {
            return String(option.label).toLowerCase().indexOf(query) >= 0
        })
    }
    readonly property var courseOptions: {
        var options = root.backendObject
                      ? root.backendObject.courseOptions.slice()
                      : []
        var courseId = root.enrollment ? root.enrollment.course_id : ""
        if (courseId
                && !options.some(function(option) {
                    return String(option.id) === String(courseId)
                })) {
            options.push({
                id: courseId,
                label: "Curso no disponible",
                active: false,
                missing: true
            })
        }
        return options
    }
    signal cancelRequested()
    signal enrollmentSaved()

    color: theme.surface
    border.color: theme.outline

    function optionForId(options, id) {
        var desiredId = String(id === undefined || id === null ? "" : id)
        for (var index = 0; index < options.length; index++) {
            if (String(options[index].id) === desiredId)
                return options[index]
        }
        return null
    }

    function optionLabel(options, id, fallback) {
        var option = root.optionForId(options, id)
        return option ? option.label : fallback
    }

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
            enrollmentDatePopup.displayedYear,
            enrollmentDatePopup.displayedMonth + offset,
            1
        )
        enrollmentDatePopup.displayedYear = nextMonth.getFullYear()
        enrollmentDatePopup.displayedMonth = nextMonth.getMonth()
    }

    function selectEnrollmentDate(value) {
        enrollmentDateField.text = root.isoDate(value)
        root.errorText = ""
        enrollmentDatePopup.close()
    }

    function loadEnrollment() {
        if (!root.enrollment)
            return
        root.errorText = ""
        root.selectedStudentId = root.enrollment.student_id || ""
        root.selectedCourseId = root.enrollment.course_id || ""
        enrollmentDateField.text = root.enrollment.enrollment_date || ""
        enrollmentFeeField.text = String(root.enrollment.enrollment_fee || "0.00")
        monthlyFeeField.text = String(root.enrollment.monthly_fee || "0.00")
        enrollmentActiveField.checked = root.enrollment.active !== false
    }

    function chooseStudent(option) {
        root.selectedStudentId = option.id
        root.studentSearchQuery = ""
        root.errorText = ""
        studentPicker.close()
    }

    function chooseCourse(option) {
        root.selectedCourseId = option.id
        root.courseSearchQuery = ""
        root.errorText = ""
        coursePicker.close()
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

    function saveChanges() {
        root.errorText = ""
        var student = root.optionForId(root.studentOptions, root.selectedStudentId)
        var course = root.optionForId(root.courseOptions, root.selectedCourseId)
        if (!student || student.missing) {
            root.errorText = "Selecciona un estudiante válido."
            return
        }
        if (!course || course.missing) {
            root.errorText = "Selecciona un curso válido."
            return
        }
        if (!/^\d{4}-\d{2}-\d{2}$/.test(enrollmentDateField.text.trim())) {
            root.errorText = "Ingresa la fecha con el formato AAAA-MM-DD."
            return
        }
        if (!root.normalizeAmount(enrollmentFeeField)
                || !root.normalizeAmount(monthlyFeeField)) {
            root.errorText = "Revisa los costos de matrícula y mensualidad."
            return
        }

        var saved = root.backendObject.saveEnrollment(root.enrollment.id, {
            student_id: student.id,
            course_id: course.id,
            enrollment_date: enrollmentDateField.text.trim(),
            enrollment_fee: enrollmentFeeField.text,
            monthly_fee: monthlyFeeField.text,
            active: enrollmentActiveField.checked
        })
        if (saved)
            root.enrollmentSaved()
        else
            root.errorText = root.backendObject.errorMessage
    }

    onEnrollmentChanged: loadEnrollment()
    Component.onCompleted: loadEnrollment()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Button {
                text: "Volver a matrículas"
                enabled: !root.backendObject.isBusy
                onClicked: root.cancelRequested()
            }

            Label {
                Layout.fillWidth: true
                text: "Editar matrícula"
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 22
                font.bold: true
            }

            Label {
                text: enrollmentActiveField.checked ? "Activa" : "Inactiva"
                color: enrollmentActiveField.checked
                       ? root.theme.success
                       : root.theme.secondaryText
                font.family: "Roboto"
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: root.theme.divider
        }

        ScrollView {
            id: enrollmentFormScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                width: enrollmentFormScroll.availableWidth
                spacing: 16

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 20
                    rowSpacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label {
                            text: "Estudiante"
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                        }
                        Button {
                            id: studentPickerButton
                            objectName: "editEnrollmentStudent"
                            Layout.fillWidth: true
                            text: root.optionLabel(
                                      root.studentOptions,
                                      root.selectedStudentId,
                                      "Seleccionar estudiante"
                                  )
                            onClicked: studentPicker.open()

                            contentItem: RowLayout {
                                Label {
                                    Layout.fillWidth: true
                                    text: studentPickerButton.text
                                    color: root.theme.primaryText
                                    font: studentPickerButton.font
                                    elide: Text.ElideRight
                                }
                                Label {
                                    text: "Cambiar"
                                    color: root.theme.accent
                                    font.family: "Roboto"
                                }
                            }

                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label {
                            text: "Curso"
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                        }
                        Button {
                            id: coursePickerButton
                            objectName: "editEnrollmentCourse"
                            Layout.fillWidth: true
                            text: root.optionLabel(
                                      root.courseOptions,
                                      root.selectedCourseId,
                                      "Seleccionar curso"
                                  )
                            onClicked: coursePicker.open()

                            contentItem: RowLayout {
                                Label {
                                    Layout.fillWidth: true
                                    text: coursePickerButton.text
                                    color: root.theme.primaryText
                                    font: coursePickerButton.font
                                    elide: Text.ElideRight
                                }
                                Label {
                                    text: "Cambiar"
                                    color: root.theme.accent
                                    font.family: "Roboto"
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label {
                            text: "Fecha de matrícula (AAAA-MM-DD)"
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                        }
                        RowLayout {
                            Layout.fillWidth: true

                            TextField {
                                id: enrollmentDateField
                                objectName: "editEnrollmentDate"
                                Layout.fillWidth: true
                                readOnly: true
                                placeholderText: "AAAA-MM-DD"
                                maximumLength: 10
                            }

                            Button {
                                text: "Calendario"
                                onClicked: enrollmentDatePopup.open()
                            }
                        }

                        Popup {
                            id: studentPicker
                            objectName: "enrollmentStudentPicker"
                            modal: true
                            focus: true
                            width: Math.min(root.width - 48, 620)
                            height: Math.min(root.height - 48, 480)
                            padding: 16
                            anchors.centerIn: Overlay.overlay
                            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

                            onOpened: {
                                root.studentSearchQuery = ""
                                studentSearchField.forceActiveFocus()
                            }

                            contentItem: ColumnLayout {
                                spacing: 12

                                Label {
                                    text: "Seleccionar estudiante"
                                    color: root.theme.primaryText
                                    font.family: "Roboto"
                                    font.pixelSize: 18
                                    font.bold: true
                                }

                                TextField {
                                    id: studentSearchField
                                    objectName: "editEnrollmentStudentSearch"
                                    Layout.fillWidth: true
                                    placeholderText: "Buscar por nombre, apellido o documento..."
                                    onTextChanged: root.studentSearchQuery = text
                                }

                                ListView {
                                    id: studentResultList
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    clip: true
                                    spacing: 4
                                    model: root.filteredStudentOptions

                                    delegate: Button {
                                        id: studentResultButton
                                        required property var modelData
                                        width: studentResultList.width
                                        height: 62
                                        enabled: !modelData.missing
                                                 && (modelData.id === ""
                                                     || modelData.active !== false
                                                     || String(modelData.id)
                                                        === String(root.selectedStudentId))
                                        onClicked: root.chooseStudent(modelData)

                                        contentItem: RowLayout {
                                            spacing: 12

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2

                                                Label {
                                                    Layout.fillWidth: true
                                                    text: studentResultButton.modelData.label
                                                    color: root.theme.primaryText
                                                    font.family: "Roboto"
                                                    font.bold: true
                                                    elide: Text.ElideRight
                                                }

                                                Label {
                                                    Layout.fillWidth: true
                                                    visible: studentResultButton.modelData.document_number
                                                             !== undefined
                                                             && studentResultButton.modelData.document_number
                                                                !== ""
                                                    text: "Documento: "
                                                          + studentResultButton.modelData.document_number
                                                    color: root.theme.secondaryText
                                                    font.family: "Roboto"
                                                    font.pixelSize: 12
                                                }
                                            }

                                            Label {
                                                text: studentResultButton.modelData.missing
                                                      ? "No disponible"
                                                      : studentResultButton.modelData.id === ""
                                                        ? "Sin asignar"
                                                        : studentResultButton.modelData.active
                                                          ? "Activo"
                                                          : "Inactivo"
                                                color: studentResultButton.modelData.active
                                                       ? root.theme.accent
                                                       : root.theme.secondaryText
                                                font.family: "Roboto"
                                            }
                                        }

                                        background: Rectangle {
                                            radius: 8
                                            color: String(studentResultButton.modelData.id)
                                                   === String(root.selectedStudentId)
                                                   ? root.theme.accentSurface
                                                   : root.theme.raisedSurface
                                            border.color: String(studentResultButton.modelData.id)
                                                          === String(root.selectedStudentId)
                                                          ? root.theme.accent
                                                          : root.theme.outline
                                        }
                                    }
                                }

                                Label {
                                    Layout.fillWidth: true
                                    visible: root.filteredStudentOptions.length === 0
                                    text: "No se encontraron estudiantes."
                                    color: root.theme.secondaryText
                                    font.family: "Roboto"
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }

                        Popup {
                            id: coursePicker
                            objectName: "enrollmentCoursePicker"
                            modal: true
                            focus: true
                            width: Math.min(root.width - 48, 620)
                            height: Math.min(root.height - 48, 480)
                            padding: 16
                            anchors.centerIn: Overlay.overlay
                            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

                            onOpened: {
                                root.courseSearchQuery = ""
                                courseSearchField.forceActiveFocus()
                            }

                            contentItem: ColumnLayout {
                                spacing: 12

                                Label {
                                    text: "Seleccionar curso"
                                    color: root.theme.primaryText
                                    font.family: "Roboto"
                                    font.pixelSize: 18
                                    font.bold: true
                                }

                                TextField {
                                    id: courseSearchField
                                    objectName: "editEnrollmentCourseSearch"
                                    Layout.fillWidth: true
                                    placeholderText: "Buscar por nombre, horario o grupo..."
                                    onTextChanged: root.courseSearchQuery = text
                                }

                                ListView {
                                    id: courseResultList
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    clip: true
                                    spacing: 4
                                    model: root.filteredCourseOptions

                                    delegate: Button {
                                        id: courseResultButton
                                        required property var modelData
                                        width: courseResultList.width
                                        height: 62
                                        enabled: !modelData.missing
                                                 && (modelData.id === ""
                                                     || modelData.active !== false
                                                     || String(modelData.id)
                                                        === String(root.selectedCourseId))
                                        onClicked: root.chooseCourse(modelData)

                                        contentItem: RowLayout {
                                            spacing: 12

                                            Label {
                                                Layout.fillWidth: true
                                                text: courseResultButton.modelData.label
                                                color: root.theme.primaryText
                                                font.family: "Roboto"
                                                elide: Text.ElideRight
                                            }

                                            Label {
                                                text: courseResultButton.modelData.missing
                                                      ? "No disponible"
                                                      : courseResultButton.modelData.id === ""
                                                        ? "Sin asignar"
                                                        : courseResultButton.modelData.active
                                                          ? "Activo"
                                                          : "Inactivo"
                                                color: courseResultButton.modelData.active
                                                       ? root.theme.accent
                                                       : root.theme.secondaryText
                                                font.family: "Roboto"
                                            }
                                        }

                                        background: Rectangle {
                                            radius: 8
                                            color: String(courseResultButton.modelData.id)
                                                   === String(root.selectedCourseId)
                                                   ? root.theme.accentSurface
                                                   : root.theme.raisedSurface
                                            border.color: String(courseResultButton.modelData.id)
                                                          === String(root.selectedCourseId)
                                                          ? root.theme.accent
                                                          : root.theme.outline
                                        }
                                    }
                                }

                                Label {
                                    Layout.fillWidth: true
                                    visible: root.filteredCourseOptions.length === 0
                                    text: "No se encontraron cursos."
                                    color: root.theme.secondaryText
                                    font.family: "Roboto"
                                    horizontalAlignment: Text.AlignHCenter
                                }
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
                            objectName: "editEnrollmentFee"
                            Layout.fillWidth: true
                            maximumLength: 11
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            validator: RegularExpressionValidator {
                                regularExpression: /^[0-9]+([.,][0-9]{0,2})?$/
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
                            objectName: "editEnrollmentMonthlyFee"
                            Layout.fillWidth: true
                            maximumLength: 11
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            validator: RegularExpressionValidator {
                                regularExpression: /^[0-9]+([.,][0-9]{0,2})?$/
                            }
                        }
                    }

                    CheckBox {
                        id: enrollmentActiveField
                        objectName: "editEnrollmentActive"
                        Layout.columnSpan: 2
                        text: "Matrícula activa"
                    }
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

        RowLayout {
            Layout.fillWidth: true

            Item {
                Layout.fillWidth: true
            }

            Button {
                objectName: "saveEnrollmentChangesButton"
                text: "Guardar cambios"
                highlighted: true
                enabled: !root.backendObject.isBusy
                onClicked: root.saveChanges()
            }
        }
    }

    Popup {
        id: enrollmentDatePopup
        objectName: "enrollmentDatePopup"
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
            var selectedDate = root.dateFromIso(enrollmentDateField.text)
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
                    text: root.monthNames[enrollmentDatePopup.displayedMonth]
                          + " " + enrollmentDatePopup.displayedYear
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
                id: enrollmentDateCalendar
                Layout.fillWidth: true
                Layout.preferredHeight: 260
                month: enrollmentDatePopup.displayedMonth
                year: enrollmentDatePopup.displayedYear
                locale: Qt.locale("es_PE")

                delegate: Button {
                    required property var model
                    implicitWidth: 40
                    implicitHeight: 36
                    text: String(model.day)
                    enabled: model.month === enrollmentDateCalendar.month
                    flat: true
                    highlighted: root.isoDate(model.date) === enrollmentDateField.text
                    onClicked: root.selectEnrollmentDate(model.date)
                }
            }
        }
    }
}
