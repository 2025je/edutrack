import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

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
    property int studentSearchLimit: 20
    property var studentSearchResults: []
    property int studentSearchResultVersion: 0
    property int studentSearchRequestId: 0
    property bool studentSearchPending: false
    property var initialEnrollmentValues: null
    readonly property bool hasUnsavedChanges: {
        if (!root.initialEnrollmentValues)
            return false
        return String(root.selectedStudentId) !== root.initialEnrollmentValues.studentId
                || String(root.selectedCourseId) !== root.initialEnrollmentValues.courseId
                || enrollmentDateField.value !== root.initialEnrollmentValues.date
                || enrollmentFeeField.text !== root.initialEnrollmentValues.enrollmentFee
                || monthlyFeeField.text !== root.initialEnrollmentValues.monthlyFee
                || enrollmentActiveField.checked !== root.initialEnrollmentValues.active
    }
    readonly property var studentOptions: {
        var resultVersion = root.studentSearchResultVersion
        var options = [{
            id: "",
            label: "Sin estudiante",
            active: true
        }]
        for (var index = 0; index < root.studentSearchResults.length; index++)
            options.push(root.studentSearchResults[index])
        var studentId = root.enrollment ? root.enrollment.student_id : ""
        if (studentId
                && !options.some(function(option) {
                    return String(option.id) === String(studentId)
                })) {
            options.push({
                id: studentId,
                    label: root.enrollment.student_label
                           || "Estudiante no disponible",
                    active: root.enrollment.student_active === true,
                    missing: root.enrollment.pending_student === true
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

    function requestCancel() {
        if (root.hasUnsavedChanges)
            discardDialog.open()
        else
            root.cancelRequested()
    }

    color: theme.surface
    border.color: theme.outline

    Timer {
        id: studentSearchTimer
        interval: 180
        repeat: false
        onTriggered: root.refreshStudentSearch()
    }

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

    function refreshStudentSearch() {
        if (!root.backendObject)
            return
        root.studentSearchPending = true
        root.studentSearchRequestId = root.backendObject.searchStudentsAsync(
            root.studentSearchQuery,
            root.studentSearchLimit
        )
    }

    function loadEnrollment() {
        if (!root.enrollment)
            return
        root.errorText = ""
        root.selectedStudentId = root.enrollment.student_id || ""
        root.selectedCourseId = root.enrollment.course_id || ""
        enrollmentDateField.value = root.enrollment.enrollment_date || ""
        enrollmentFeeField.text = String(root.enrollment.enrollment_fee || "0.00")
        monthlyFeeField.text = String(root.enrollment.monthly_fee || "0.00")
        enrollmentActiveField.checked = root.enrollment.active !== false
        root.initialEnrollmentValues = {
            studentId: String(root.selectedStudentId),
            courseId: String(root.selectedCourseId),
            date: enrollmentDateField.value,
            enrollmentFee: enrollmentFeeField.text,
            monthlyFee: monthlyFeeField.text,
            active: enrollmentActiveField.checked
        }
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
        if (!enrollmentDateField.valid) {
            root.errorText = "Selecciona una fecha válida."
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
            enrollment_date: enrollmentDateField.value,
            enrollment_fee: enrollmentFeeField.text,
            monthly_fee: monthlyFeeField.text,
            active: enrollmentActiveField.checked
        })
        if (saved)
            root.enrollmentSaved()
        else
            root.errorText = root.backendObject.errorMessage
    }

    DiscardChangesDialog {
        id: discardDialog
        theme: root.theme
        onDiscardConfirmed: root.cancelRequested()
    }

    Shortcut {
        sequence: "Ctrl+S"
        enabled: root.visible && !root.backendObject.isBusy
                 && !studentPicker.opened && !coursePicker.opened
                 && !enrollmentDateField.popupOpen
        onActivated: root.saveChanges()
    }

    Shortcut {
        sequence: "Esc"
        enabled: root.visible && !studentPicker.opened
                 && !coursePicker.opened && !enrollmentDateField.popupOpen
        onActivated: root.requestCancel()
    }

    onEnrollmentChanged: loadEnrollment()
    Component.onCompleted: loadEnrollment()

    Connections {
        target: root.backendObject
        function onStudentSearchFinished(requestId, rows, error) {
            if (requestId !== root.studentSearchRequestId)
                return
            root.studentSearchPending = false
            if (error.length > 0) {
                root.studentSearchResults = []
                root.studentSearchResultVersion += 1
                root.errorText = error
            } else {
                root.studentSearchResults = rows
                root.studentSearchResultVersion += 1
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Button {
                objectName: "cancelEnrollmentEditButton"
                text: "Volver a matrículas"
                enabled: !root.backendObject.isBusy
                onClicked: root.requestCancel()
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
                            text: "Fecha de matrícula"
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                        }
                        DateInput {
                            id: enrollmentDateField
                            objectName: "editEnrollmentDate"
                            Layout.fillWidth: true
                            theme: root.theme
                            onDateSelected: root.errorText = ""
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
                                studentSearchField.clear()
                                root.studentSearchQuery = ""
                                root.studentSearchLimit = 20
                                root.studentSearchResults = []
                                root.studentSearchResultVersion += 1
                                studentSearchTimer.stop()
                                root.refreshStudentSearch()
                                studentSearchField.forceActiveFocus()
                            }
                            onClosed: {
                                studentSearchTimer.stop()
                                root.studentSearchRequestId = 0
                                root.studentSearchPending = false
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
                                    onTextChanged: {
                                        root.studentSearchQuery = text
                                        root.studentSearchLimit = 20
                                        root.studentSearchResults = []
                                        root.studentSearchResultVersion += 1
                                        root.studentSearchRequestId = 0
                                        root.studentSearchPending = true
                                        studentSearchTimer.restart()
                                    }
                                }

                                Label {
                                    Layout.fillWidth: true
                                    visible: root.studentSearchPending
                                    text: "Buscando estudiantes..."
                                    color: root.theme.secondaryText
                                    font.family: "Roboto"
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

                                            Button {
                                                objectName: "editEnrollmentShowMoreStudentsButton"
                                                Layout.fillWidth: true
                                                visible: root.studentSearchResults.length
                                                         >= root.studentSearchLimit
                                                         && root.studentSearchLimit < 100
                                                text: "Mostrar más resultados"
                                                onClicked: {
                                                    root.studentSearchLimit = Math.min(
                                                        root.studentSearchLimit + 20,
                                                        100
                                                    )
                                                    root.refreshStudentSearch()
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
                                    visible: root.studentSearchQuery.trim().length > 0
                                             && root.studentSearchResults.length === 0
                                             && !root.studentSearchPending
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
                        MoneySpinBox {
                            id: enrollmentFeeField
                            objectName: "editEnrollmentFee"
                            Layout.fillWidth: true
                            theme: root.theme
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
                            objectName: "editEnrollmentMonthlyFee"
                            Layout.fillWidth: true
                            theme: root.theme
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

}
