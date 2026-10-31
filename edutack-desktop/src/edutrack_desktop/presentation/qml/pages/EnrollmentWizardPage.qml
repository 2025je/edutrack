import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"

Rectangle {
    id: root
    objectName: "enrollmentWizardPage"
    property var backendObject
    property var theme
    // Pasos: 1 estudiante, 2 datos de matrícula, 3 resumen, 4 resultado.
    property int currentStep: 1
    property bool creatingStudent: false
    property bool stepTwoInitialized: false
    property var selectedStudent: null
    property string errorText: ""
    property var searchResults: []
    property int searchLimit: 20
    property var duplicateCandidates: []
    property var savedResult: null

    readonly property var activeCourses: {
        var courses = root.backendObject ? root.backendObject.courses : []
        return courses.filter(function(course) {
            return course.active
        })
    }
    readonly property string stepTitle: {
        if (root.currentStep === 1)
            return "Paso 1 de 2 · Estudiante"
        if (root.currentStep === 2)
            return "Paso 2 de 2 · Datos de matrícula"
        if (root.currentStep === 3)
            return "Resumen"
        return "Matrícula registrada"
    }

    signal cancelRequested()
    signal enrollmentSaved()

    color: theme.surface
    border.color: theme.outline

    Shortcut {
        sequence: "Ctrl+S"
        enabled: root.visible && root.currentStep === 3
        onActivated: root.confirmSave()
    }

    Shortcut {
        sequence: "Esc"
        enabled: root.visible && !recordImageDialog.visible
                 && !enrollmentDateField.popupOpen
        onActivated: root.cancelRequested()
    }

    function begin() {
        root.currentStep = 1
        root.creatingStudent = false
        root.stepTwoInitialized = false
        root.selectedStudent = null
        root.errorText = ""
        root.searchLimit = 20
        root.duplicateCandidates = []
        root.savedResult = null
        studentSearchField.clear()
        lastNameField.clear()
        firstNameField.clear()
        documentField.clear()
        phonesField.clear()
        root.refreshSearch()
    }

    function refreshSearch() {
        if (!root.backendObject)
            return
        root.searchResults = root.backendObject.searchStudents(
            studentSearchField.text, root.searchLimit)
    }

    function refreshDuplicates() {
        if (!root.backendObject || !root.creatingStudent) {
            root.duplicateCandidates = []
            return
        }
        var query = (lastNameField.text + " " + firstNameField.text).trim()
        root.duplicateCandidates = query.length >= 3
            ? root.backendObject.searchStudents(query, 5)
            : []
    }

    function studentLabel(student) {
        return [student.last_name, student.first_name].filter(function(part) {
            return part
        }).join(" ")
    }

    function studentDisplayName() {
        if (root.creatingStudent)
            return (lastNameField.text + " " + firstNameField.text)
                .trim().toUpperCase()
        return root.selectedStudent ? root.studentLabel(root.selectedStudent) : ""
    }

    function currentCourse() {
        return root.activeCourses[courseField.currentIndex] || null
    }

    function todayDate() {
        var today = new Date()
        var month = ("0" + (today.getMonth() + 1)).slice(-2)
        var day = ("0" + today.getDate()).slice(-2)
        return today.getFullYear() + "-" + month + "-" + day
    }

    function continueToStepTwo() {
        root.errorText = ""
        if (root.creatingStudent) {
            if (!lastNameField.text.trim() || !firstNameField.text.trim()
                    || !phonesField.text.trim()) {
                root.errorText =
                        "Completa apellidos, nombres y al menos un celular."
                return
            }
        } else if (!root.selectedStudent || !root.selectedStudent.active) {
            root.errorText = "Selecciona un estudiante activo o crea uno nuevo."
            return
        }
        if (!root.stepTwoInitialized) {
            enrollmentDateField.value = root.todayDate()
            courseField.currentIndex = root.activeCourses.length > 0 ? 0 : -1
            root.updateCourseFees()
            root.stepTwoInitialized = true
        }
        root.currentStep = 2
    }

    function updateCourseFees() {
        var course = root.currentCourse()
        if (!course) {
            enrollmentFeeField.text = ""
            monthlyFeeField.text = ""
            return
        }
        enrollmentFeeField.text = String(course.enrollment_fee || "0.00")
        monthlyFeeField.text = String(course.monthly_fee || "0.00")
    }

    function continueToSummary() {
        root.errorText = ""
        if (!root.currentCourse()) {
            root.errorText = "Selecciona un curso activo."
            return
        }
        if (!enrollmentDateField.valid) {
            root.errorText = "Selecciona una fecha válida."
            return
        }
        if (!enrollmentFeeField.normalizeText()
                || !monthlyFeeField.normalizeText()) {
            root.errorText = "Revisa los costos de matrícula y mensualidad."
            return
        }
        root.currentStep = 3
    }

    function confirmSave() {
        root.errorText = ""
        var course = root.currentCourse()
        if (!course) {
            root.errorText = "Selecciona un curso activo."
            return
        }
        var studentFields = root.creatingStudent
            ? {
                  last_name: lastNameField.text,
                  first_name: firstNameField.text,
                  document_number: documentField.text,
                  phone_text: phonesField.text
              }
            : { id: root.selectedStudent.id }
        var result = root.backendObject.createEnrollment(studentFields, {
            course_id: course.id,
            enrollment_date: enrollmentDateField.value,
            enrollment_fee: enrollmentFeeField.text.replace(",", "."),
            monthly_fee: monthlyFeeField.text.replace(",", "."),
            record_code: "",
            promoter_ids: []
        })
        if (!result.ok) {
            root.errorText = root.backendObject.errorMessage
            return
        }
        root.savedResult = {
            student: root.studentDisplayName(),
            courseName: course.name,
            schedule: course.schedule,
            group: course.group,
            date: enrollmentDateField.value,
            recordCode: ""
        }
        root.currentStep = 4
    }

    Timer {
        id: searchDebounce
        interval: 250
        repeat: false
        onTriggered: root.refreshSearch()
    }

    Timer {
        id: duplicateDebounce
        interval: 300
        repeat: false
        onTriggered: root.refreshDuplicates()
    }

    Connections {
        target: root.backendObject
        function onDataChanged() {
            if (root.currentStep === 1 && !root.creatingStudent)
                root.refreshSearch()
        }
    }

    FileDialog {
        id: recordImageDialog
        title: "Selecciona la imagen de la ficha"
        nameFilters: ["Imágenes (*.jpg *.jpeg *.png *.webp)"]
        onAccepted: root.backendObject.attachEnrollmentImage(
                        selectedFile.toString())
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Cancelar"
                visible: root.currentStep < 4
                enabled: !root.backendObject.isBusy
                onClicked: root.cancelRequested()
            }

            Label {
                Layout.fillWidth: true
                text: "Nueva matrícula"
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 24
                font.bold: true
            }

            Label {
                text: root.stepTitle
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 14
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: root.theme.divider
        }

        // ---------- Paso 1: seleccionar o crear estudiante ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.currentStep === 1
            spacing: 12

            TextField {
                id: studentSearchField
                objectName: "enrollmentStudentSearch"
                Layout.fillWidth: true
                visible: !root.creatingStudent
                placeholderText: "Buscar por apellidos, nombres o documento..."
                font.family: "Roboto"
                onTextChanged: {
                    root.selectedStudent = null
                    root.errorText = ""
                    root.searchLimit = 20
                    searchDebounce.restart()
                }
            }

            Label {
                Layout.fillWidth: true
                visible: !root.creatingStudent
                text: "Selecciona un estudiante activo o crea uno nuevo."
                color: root.theme.secondaryText
                font.family: "Roboto"
            }

            ListView {
                id: studentList
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: !root.creatingStudent && root.searchResults.length > 0
                clip: true
                spacing: 8
                model: root.searchResults

                delegate: Button {
                    id: studentChoice
                    objectName: "enrollmentStudentOption"
                    required property var modelData
                    width: studentList.width
                    height: 68
                    enabled: modelData.active
                    onClicked: {
                        root.selectedStudent = modelData
                        root.errorText = ""
                    }

                    contentItem: RowLayout {
                        spacing: 12

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3

                            Label {
                                Layout.fillWidth: true
                                text: root.studentLabel(studentChoice.modelData)
                                color: root.theme.primaryText
                                font.family: "Roboto"
                                font.bold: true
                                elide: Text.ElideRight
                            }

                            Label {
                                Layout.fillWidth: true
                                text: "Documento: "
                                      + (studentChoice.modelData.document_number
                                         || "No registrado")
                                      + (studentChoice.modelData.courses.length > 0
                                         ? " · Matrículas activas: "
                                           + studentChoice.modelData.courses.length
                                         : "")
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                        }

                        Label {
                            text: studentChoice.modelData.active
                                  ? "Seleccionar" : "Inactivo"
                            color: studentChoice.modelData.active
                                   ? root.theme.accent
                                   : root.theme.secondaryText
                            font.family: "Roboto"
                        }
                    }

                    background: Rectangle {
                        radius: 8
                        color: root.selectedStudent
                               && root.selectedStudent.id === studentChoice.modelData.id
                               ? root.theme.accentSurface
                               : root.theme.raisedSurface
                        border.color: root.selectedStudent
                                      && root.selectedStudent.id === studentChoice.modelData.id
                                      ? root.theme.accent
                                      : root.theme.outline
                    }
                }

                footer: Item {
                    width: studentList.width
                    height: showMoreButton.visible ? 48 : 0

                    Button {
                        id: showMoreButton
                        anchors.centerIn: parent
                        visible: root.searchResults.length >= root.searchLimit
                                 && root.searchLimit < 100
                        text: "Mostrar más resultados"
                        font.family: "Roboto"
                        onClicked: {
                            root.searchLimit = Math.min(root.searchLimit + 20, 100)
                            root.refreshSearch()
                        }
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: !root.creatingStudent && root.searchResults.length === 0
                text: "No se encontraron estudiantes con ese criterio."
                color: root.theme.secondaryText
                font.family: "Roboto"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            Label {
                objectName: "enrollmentExistingWarning"
                Layout.fillWidth: true
                visible: !root.creatingStudent && root.selectedStudent
                         && root.selectedStudent.courses
                         && root.selectedStudent.courses.length > 0
                text: root.selectedStudent && root.selectedStudent.courses
                      ? "Atención: este estudiante ya tiene "
                        + root.selectedStudent.courses.length
                        + " matrícula(s) activa(s): "
                        + root.selectedStudent.courses.join(" | ")
                      : ""
                color: root.theme.error
                font.family: "Roboto"
                wrapMode: Text.Wrap
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 20
                rowSpacing: 12
                visible: root.creatingStudent

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
                        objectName: "newEnrollmentStudentLastName"
                        Layout.fillWidth: true
                        maximumLength: 120
                        onTextChanged: duplicateDebounce.restart()
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
                        objectName: "newEnrollmentStudentFirstName"
                        Layout.fillWidth: true
                        maximumLength: 120
                        onTextChanged: duplicateDebounce.restart()
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
                        objectName: "newEnrollmentStudentDocument"
                        Layout.fillWidth: true
                        maximumLength: 20
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
                        objectName: "newEnrollmentStudentPhones"
                        Layout.fillWidth: true
                        maximumLength: 250
                        placeholderText: "Celulares de 9 dígitos"
                    }
                }
            }

            Label {
                objectName: "enrollmentDuplicateWarning"
                Layout.fillWidth: true
                visible: root.creatingStudent && root.duplicateCandidates.length > 0
                text: "Posibles duplicados ya registrados: "
                      + root.duplicateCandidates.map(function(student) {
                            return root.studentLabel(student)
                        }).join(" | ")
                color: root.theme.error
                font.family: "Roboto"
                wrapMode: Text.Wrap
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
                spacing: 12

                Button {
                    objectName: "enrollmentCreateStudentButton"
                    text: root.creatingStudent ? "Volver a buscar" : "Crear estudiante"
                    onClicked: {
                        root.errorText = ""
                        root.selectedStudent = null
                        root.creatingStudent = !root.creatingStudent
                        root.duplicateCandidates = []
                        if (!root.creatingStudent)
                            root.refreshSearch()
                    }
                }

                Item {
                    Layout.fillWidth: true
                }

                Button {
                    objectName: "enrollmentContinueToCourseButton"
                    text: "Continuar"
                    highlighted: true
                    enabled: root.creatingStudent
                             || (root.selectedStudent && root.selectedStudent.active)
                    onClicked: root.continueToStepTwo()
                }
            }
        }

        // ---------- Paso 2: datos de matrícula ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.currentStep === 2
            spacing: 16

            Label {
                Layout.fillWidth: true
                text: "Estudiante: " + root.studentDisplayName()
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 16
                font.bold: true
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
                        text: "Curso"
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                    }
                    ComboBox {
                        id: courseField
                        objectName: "newEnrollmentCourse"
                        Layout.fillWidth: true
                        model: root.activeCourses
                        textRole: "label"
                        onActivated: root.updateCourseFees()
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
                        objectName: "newEnrollmentDate"
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
                        objectName: "newEnrollmentFee"
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
                        objectName: "newEnrollmentMonthlyFee"
                        Layout.fillWidth: true
                        theme: root.theme
                    }
                }

            }

            Label {
                Layout.fillWidth: true
                visible: root.activeCourses.length === 0
                text: "No hay cursos activos disponibles para matricular."
                color: root.theme.error
                font.family: "Roboto"
                wrapMode: Text.Wrap
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

                Button {
                    text: "Volver"
                    enabled: !root.backendObject.isBusy
                    onClicked: {
                        root.currentStep = 1
                        root.errorText = ""
                    }
                }

                Item {
                    Layout.fillWidth: true
                }

                Button {
                    objectName: "enrollmentContinueToSummaryButton"
                    text: "Revisar y confirmar"
                    highlighted: true
                    enabled: root.activeCourses.length > 0
                             && !root.backendObject.isBusy
                    onClicked: root.continueToSummary()
                }
            }
        }

        // ---------- Paso 3: resumen antes de confirmar ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.currentStep === 3
            spacing: 16

            Label {
                Layout.fillWidth: true
                text: "Revisa los datos antes de guardar."
                color: root.theme.secondaryText
                font.family: "Roboto"
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: summaryGrid.implicitHeight + 32
                radius: 8
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                GridLayout {
                    id: summaryGrid
                    anchors.fill: parent
                    anchors.margins: 16
                    columns: 2
                    columnSpacing: 24
                    rowSpacing: 8

                    Repeater {
                        model: {
                            var course = root.currentCourse() || {}
                            var rows = [
                                { name: "Estudiante", value: root.studentDisplayName() },
                                { name: "Curso", value: course.name || "" },
                                { name: "Horario", value: course.schedule || "" },
                                { name: "Grupo", value: String(course.group || "") },
                                { name: "Fecha de matrícula",
                                  value: enrollmentDateField.value },
                                { name: "Costo de matrícula",
                                  value: enrollmentFeeField.text },
                                { name: "Mensualidad", value: monthlyFeeField.text }
                            ]
                            if (root.creatingStudent)
                                rows.splice(1, 0, {
                                    name: "Estudiante nuevo",
                                    value: "Se creará junto con la matrícula"
                                })
                            return rows
                        }

                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 2

                            Label {
                                text: modelData.name
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 12
                            }

                            Label {
                                Layout.fillWidth: true
                                text: modelData.value
                                color: root.theme.primaryText
                                font.family: "Roboto"
                                wrapMode: Text.Wrap
                            }
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

            Item {
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Button {
                    text: "Volver"
                    enabled: !root.backendObject.isBusy
                    onClicked: {
                        root.currentStep = 2
                        root.errorText = ""
                    }
                }

                Item {
                    Layout.fillWidth: true
                }

                Button {
                    objectName: "enrollmentSaveButton"
                    text: "Confirmar y guardar"
                    highlighted: true
                    enabled: !root.backendObject.isBusy
                    onClicked: root.confirmSave()
                }
            }
        }

        // ---------- Paso 4: resultado ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.currentStep === 4
            spacing: 16

            Label {
                Layout.fillWidth: true
                text: "Matrícula guardada en este dispositivo."
                color: root.theme.success
                font.family: "Roboto"
                font.pixelSize: 18
                font.bold: true
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: resultGrid.implicitHeight + 32
                radius: 8
                color: root.theme.successSurface
                border.color: root.theme.success

                GridLayout {
                    id: resultGrid
                    anchors.fill: parent
                    anchors.margins: 16
                    columns: 2
                    columnSpacing: 24
                    rowSpacing: 8

                    Repeater {
                        model: root.savedResult ? [
                            { name: "Estudiante", value: root.savedResult.student },
                            { name: "Curso", value: root.savedResult.courseName },
                            { name: "Horario", value: root.savedResult.schedule },
                            { name: "Grupo", value: String(root.savedResult.group) },
                            { name: "Fecha de matrícula",
                              value: root.savedResult.date }
                        ] : []

                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 2

                            Label {
                                text: modelData.name
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 12
                            }

                            Label {
                                Layout.fillWidth: true
                                text: modelData.value
                                color: root.theme.primaryText
                                font.family: "Roboto"
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                visible: root.savedResult && root.savedResult.recordCode.length > 0

                Button {
                    objectName: "enrollmentAttachImageButton"
                    text: "Adjuntar imagen de ficha"
                    enabled: !root.backendObject.isBusy
                    onClicked: recordImageDialog.open()
                }

                Label {
                    Layout.fillWidth: true
                    text: root.backendObject.enrollmentImageName
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                    elide: Text.ElideRight
                }
            }

            Item {
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Button {
                    objectName: "enrollmentNewAnotherButton"
                    text: "Registrar otra matrícula"
                    enabled: !root.backendObject.isBusy
                    onClicked: root.begin()
                }

                Item {
                    Layout.fillWidth: true
                }

                Button {
                    objectName: "enrollmentFinishButton"
                    text: "Finalizar"
                    highlighted: true
                    enabled: !root.backendObject.isBusy
                    onClicked: root.enrollmentSaved()
                }
            }
        }
    }
}
