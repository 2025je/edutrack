import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "enrollmentWizardPage"
    property var backendObject
    property var theme
    property int currentStep: 1
    property bool creatingStudent: false
    property bool stepTwoInitialized: false
    property var selectedStudent: null
    property string errorText: ""
    readonly property var matchingStudents: {
        var students = root.backendObject ? root.backendObject.students : []
        var query = studentSearchField.text.trim().toLowerCase()
        return students.filter(function(student) {
            var searchableText = [
                student.label,
                student.last_name,
                student.first_name,
                student.document_number
            ].join(" ").toLowerCase()
            return searchableText.indexOf(query) >= 0
        })
    }
    readonly property var activeCourses: {
        var courses = root.backendObject ? root.backendObject.courses : []
        return courses.filter(function(course) {
            return course.active
        })
    }

    signal cancelRequested()
    signal enrollmentSaved()

    color: theme.surface
    border.color: theme.outline

    function begin() {
        root.currentStep = 1
        root.creatingStudent = false
        root.stepTwoInitialized = false
        root.selectedStudent = null
        root.errorText = ""
        studentSearchField.clear()
        lastNameField.clear()
        firstNameField.clear()
        documentField.clear()
        phonesField.clear()
    }

    function studentLabel(student) {
        return [student.last_name, student.first_name].filter(function(part) {
            return part
        }).join(" ")
    }

    function todayDate() {
        var today = new Date()
        var month = ("0" + (today.getMonth() + 1)).slice(-2)
        var day = ("0" + today.getDate()).slice(-2)
        return today.getFullYear() + "-" + month + "-" + day
    }

    function continueToStepTwo(student) {
        if (student)
            root.selectedStudent = student
        if (!root.selectedStudent)
            return

        root.errorText = ""
        if (!root.stepTwoInitialized) {
            enrollmentDateField.text = root.todayDate()
            courseField.currentIndex = root.activeCourses.length > 0 ? 0 : -1
            root.updateCourseFees()
            root.stepTwoInitialized = true
        }
        root.currentStep = 2
    }

    function updateCourseFees() {
        var course = root.activeCourses[courseField.currentIndex]
        if (!course) {
            enrollmentFeeField.text = ""
            monthlyFeeField.text = ""
            return
        }
        enrollmentFeeField.text = String(course.enrollment_fee || "0.00")
        monthlyFeeField.text = String(course.monthly_fee || "0.00")
    }

    function createStudent() {
        root.errorText = ""
        if (!root.backendObject.saveStudent(
                    "",
                    lastNameField.text,
                    firstNameField.text,
                    documentField.text,
                    phonesField.text)) {
            root.errorText = root.backendObject.errorMessage
            return
        }

        var student = root.backendObject.selectedStudent
        if (!student || !student.id) {
            root.errorText = "No se pudo recuperar el estudiante guardado."
            return
        }
        root.continueToStepTwo(student)
    }

    function saveEnrollment() {
        root.errorText = ""
        var course = root.activeCourses[courseField.currentIndex]
        if (!course) {
            root.errorText = "Selecciona un curso activo."
            return
        }
        if (!/^\d{4}-\d{2}-\d{2}$/.test(enrollmentDateField.text.trim())) {
            root.errorText = "Ingresa la fecha con el formato AAAA-MM-DD."
            return
        }
        if (!enrollmentFeeField.acceptableInput
                || !monthlyFeeField.acceptableInput
                || enrollmentFeeField.text.length === 0
                || monthlyFeeField.text.length === 0) {
            root.errorText = "Revisa los costos de matrícula y mensualidad."
            return
        }

        var saved = root.backendObject.saveEnrollment("", {
            student_id: root.selectedStudent.id,
            course_id: course.id,
            enrollment_date: enrollmentDateField.text.trim(),
            enrollment_fee: enrollmentFeeField.text.replace(",", "."),
            monthly_fee: monthlyFeeField.text.replace(",", ".")
        })
        if (saved)
            root.enrollmentSaved()
        else
            root.errorText = root.backendObject.errorMessage
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Cancelar"
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
                text: root.currentStep === 1 ? "Paso 1 de 2" : "Paso 2 de 2"
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
                placeholderText: "Buscar por nombre, apellido o documento..."
                font.family: "Roboto"
                onTextChanged: {
                    root.selectedStudent = null
                    root.errorText = ""
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
                visible: !root.creatingStudent && root.matchingStudents.length > 0
                clip: true
                spacing: 8
                model: root.matchingStudents

                delegate: Button {
                    id: studentChoice
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
                                      + (studentChoice.modelData.document_number || "No registrado")
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                        }

                        Label {
                            text: studentChoice.modelData.active ? "Seleccionar" : "Inactivo"
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
            }

            Label {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: !root.creatingStudent && root.matchingStudents.length === 0
                text: "No se encontraron estudiantes con ese criterio."
                color: root.theme.secondaryText
                font.family: "Roboto"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
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
                    }
                }

                Item {
                    Layout.fillWidth: true
                }

                Button {
                    objectName: "enrollmentContinueToCourseButton"
                    visible: !root.creatingStudent
                    text: "Continuar"
                    highlighted: true
                    enabled: root.selectedStudent && root.selectedStudent.active
                    onClicked: root.continueToStepTwo(root.selectedStudent)
                }

                Button {
                    objectName: "enrollmentSaveStudentButton"
                    visible: root.creatingStudent
                    text: "Guardar estudiante y continuar"
                    highlighted: true
                    enabled: !root.backendObject.isBusy
                    onClicked: root.createStudent()
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.currentStep === 2
            spacing: 16

            Label {
                Layout.fillWidth: true
                text: "Estudiante: " + root.studentLabel(root.selectedStudent || {})
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
                        text: "Fecha de matrícula (AAAA-MM-DD)"
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                    }
                    TextField {
                        id: enrollmentDateField
                        objectName: "newEnrollmentDate"
                        Layout.fillWidth: true
                        validator: RegularExpressionValidator {
                            regularExpression: /^\d{4}-\d{2}-\d{2}$/
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
                        objectName: "newEnrollmentFee"
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
                        objectName: "newEnrollmentMonthlyFee"
                        Layout.fillWidth: true
                        maximumLength: 11
                        inputMethodHints: Qt.ImhFormattedNumbersOnly
                        validator: RegularExpressionValidator {
                            regularExpression: /^[0-9]+([.,][0-9]{0,2})?$/
                        }
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
                    objectName: "enrollmentSaveButton"
                    text: "Guardar matrícula"
                    highlighted: true
                    enabled: root.activeCourses.length > 0
                             && !root.backendObject.isBusy
                    onClicked: root.saveEnrollment()
                }
            }
        }
    }
}
