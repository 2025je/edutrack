import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: wizard

    required property var appWindow
    required property var desktopBackend
    property int step: 0
    property string studentId: ""
    property string studentLabel: ""
    property var studentMatches: []
    property bool withoutStudent: false
    property bool creatingStudent: false
    property string errorMessage: ""

    title: step === 0 ? "Nueva matrícula · Paso 1 de 2"
                      : "Nueva matrícula · Paso 2 de 2"
    modal: true
    width: Math.min(appWindow.width - 48, 760)
    height: Math.min(appWindow.height - 56, 590)
    anchors.centerIn: parent

    function openWizard(reserveSeat) {
        appWindow.showEnrollmentEditor = false
        withoutStudent = reserveSeat === true
        step = withoutStudent ? 1 : 0
        studentId = ""
        studentLabel = withoutStudent ? "Cupo reservado (sin estudiante)" : ""
        studentMatches = []
        creatingStudent = false
        errorMessage = ""
        studentSearch.text = ""
        newStudentLastName.text = ""
        newStudentFirstName.text = ""
        newStudentDocument.text = ""
        newStudentPhones.text = ""
        enrollmentDate.text = Qt.formatDate(new Date(), "yyyy-MM-dd")
        enrollmentFee.text = ""
        monthlyFee.text = ""
        course.currentIndex = withoutStudent && course.count > 1 ? 1 : 0
        updateCourseFees()
        if (!withoutStudent)
            searchStudents("")
        open()
    }

    function updateCourseFees() {
        if (!course.currentValue) {
            enrollmentFee.text = "0.00"
            monthlyFee.text = "0.00"
            return
        }
        var availableCourses = desktopBackend.courses
        for (var index = 0; index < availableCourses.length; index++) {
            var item = availableCourses[index]
            if (String(item.id) === String(course.currentValue)) {
                enrollmentFee.text = String(item.enrollment_fee)
                monthlyFee.text = String(item.monthly_fee)
                return
            }
        }
    }

    function searchStudents(query) {
        var normalized = String(query).trim().toLowerCase()
        var matches = []
        studentId = ""
        studentLabel = ""
        for (var index = 0; index < desktopBackend.students.length; index++) {
            var student = desktopBackend.students[index]
            var phones = student.phone_numbers ? student.phone_numbers.join(" ") : ""
            var searchable = (student.label + " "
                              + (student.document_number || "") + " "
                              + phones).toLowerCase()
            if (student.active
                    && (!normalized || searchable.indexOf(normalized) >= 0))
                matches.push(student)
        }
        studentMatches = matches
    }

    function beginStudentCreation() {
        studentId = ""
        studentLabel = ""
        creatingStudent = true
        errorMessage = ""
        var query = studentSearch.text.trim()
        newStudentDocument.text = /^[0-9]+$/.test(query) ? query : ""
    }

    function chooseStudent(sourceId) {
        for (var index = 0; index < desktopBackend.students.length; index++) {
            var student = desktopBackend.students[index]
            if (student.id === sourceId && student.active) {
                withoutStudent = false
                studentId = student.id
                studentLabel = student.label
                desktopBackend.selectStudent(student.id)
                errorMessage = ""
                step = 1
                return
            }
        }
    }

    function createStudent() {
        desktopBackend.newStudent()
        desktopBackend.saveStudent(
            "",
            newStudentLastName.text,
            newStudentFirstName.text,
            newStudentDocument.text,
            newStudentPhones.text
        )
        var student = desktopBackend.selectedStudent
        if (!student.id) {
            errorMessage = desktopBackend.errorMessage
            return
        }
        studentId = student.id
        studentLabel = student.last_name + " " + student.first_name
        withoutStudent = false
        creatingStudent = false
        step = 1
        errorMessage = ""
    }

    function saveEnrollment() {
        var saved = desktopBackend.saveEnrollment("", {
            student_id: studentId,
            course_id: course.currentValue,
            enrollment_date: enrollmentDate.text,
            enrollment_fee: enrollmentFee.text,
            monthly_fee: monthlyFee.text
        })
        if (!saved) {
            errorMessage = desktopBackend.errorMessage
            return
        }
        errorMessage = ""
        close()
        appWindow.showEnrollmentEditor = false
        appWindow.currentPage = 1
    }

    contentItem: ColumnLayout {
        spacing: 12

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: wizard.step

            ScrollView {
                id: studentStepScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ColumnLayout {
                    width: studentStepScroll.availableWidth
                    spacing: 10
                    Label {
                        Layout.fillWidth: true
                        text: "Busca por nombre, DNI o celular. Selecciona al estudiante para continuar."
                        wrapMode: Text.Wrap
                        color: appWindow.secondaryTextColor
                    }
                    TextField {
                        id: studentSearch
                        objectName: "studentSearchField"
                        Layout.fillWidth: true
                        placeholderText: "Buscar estudiante"
                        onTextChanged: wizard.searchStudents(text)
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        visible: !wizard.creatingStudent
                        radius: 6
                        color: appWindow.nestedSurfaceColor
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 12
                            Label {
                                Layout.fillWidth: true
                                text: "Estudiante"
                                font.bold: true
                                color: appWindow.primaryTextColor
                            }
                            Label {
                                Layout.preferredWidth: 100
                                text: "DNI"
                                font.bold: true
                                color: appWindow.primaryTextColor
                            }
                            Label {
                                Layout.preferredWidth: 150
                                text: "Celular"
                                font.bold: true
                                color: appWindow.primaryTextColor
                            }
                        }
                    }
                    ListView {
                        id: studentTable
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(
                            Math.max(wizard.studentMatches.length, 1) * 44,
                            220
                        )
                        visible: !wizard.creatingStudent
                        clip: true
                        model: wizard.studentMatches
                        delegate: ItemDelegate {
                            width: ListView.view.width
                            height: 44
                            padding: 8
                            background: Rectangle {
                                color: wizard.studentId === modelData.id
                                       ? appWindow.accentSurfaceColor
                                       : parent.hovered
                                         ? appWindow.nestedSurfaceColor
                                         : appWindow.surfaceColor
                                border.color: appWindow.borderColor
                            }
                            contentItem: RowLayout {
                                spacing: 12
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.label
                                    elide: Text.ElideRight
                                    color: appWindow.primaryTextColor
                                }
                                Label {
                                    Layout.preferredWidth: 100
                                    text: modelData.document_number || "—"
                                    elide: Text.ElideRight
                                    color: appWindow.secondaryTextColor
                                }
                                Label {
                                    Layout.preferredWidth: 150
                                    text: modelData.phone_numbers
                                          ? modelData.phone_numbers.join(", ")
                                          : "—"
                                    elide: Text.ElideRight
                                    color: appWindow.secondaryTextColor
                                }
                            }
                            onClicked: wizard.chooseStudent(modelData.id)
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !wizard.creatingStudent
                                 && studentSearch.text.trim().length > 0
                                 && wizard.studentMatches.length === 0
                        text: "No encontramos coincidencias. Puedes registrar un estudiante nuevo."
                        wrapMode: Text.Wrap
                        color: appWindow.secondaryTextColor
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !wizard.creatingStudent
                                 && studentSearch.text.trim().length === 0
                                 && wizard.studentMatches.length === 0
                        text: "No hay estudiantes activos. Puedes registrar uno nuevo."
                        wrapMode: Text.Wrap
                        color: appWindow.secondaryTextColor
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: Boolean(wizard.studentId) && !wizard.creatingStudent
                        text: "Seleccionado: " + wizard.studentLabel
                        wrapMode: Text.Wrap
                        color: appWindow.successColor
                        font.bold: true
                    }
                    Button {
                        Layout.fillWidth: true
                        text: wizard.creatingStudent
                              ? "Cancelar registro de estudiante"
                              : "¿No aparece? Registrar estudiante"
                        onClicked: {
                            if (wizard.creatingStudent) {
                                wizard.creatingStudent = false
                                wizard.errorMessage = ""
                            } else {
                                wizard.beginStudentCreation()
                            }
                        }
                    }
                    Button {
                        Layout.fillWidth: true
                        visible: !wizard.creatingStudent
                        text: "Reservar cupo sin estudiante"
                        onClicked: wizard.openWizard(true)
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        visible: wizard.creatingStudent
                        columns: 2
                        columnSpacing: 10
                        Label { text: "Apellidos" }
                        TextField {
                            id: newStudentLastName
                            Layout.fillWidth: true
                            placeholderText: "Apellidos"
                        }
                        Label { text: "Nombres" }
                        TextField {
                            id: newStudentFirstName
                            Layout.fillWidth: true
                            placeholderText: "Nombres"
                        }
                        Label { text: "DNI" }
                        TextField {
                            id: newStudentDocument
                            Layout.fillWidth: true
                            placeholderText: "Opcional"
                        }
                        Label { text: "Celular(es)" }
                        TextField {
                            id: newStudentPhones
                            Layout.fillWidth: true
                            placeholderText: "9 dígitos, separados por coma"
                        }
                    }
                    Button {
                        Layout.alignment: Qt.AlignRight
                        visible: wizard.creatingStudent
                        text: "Crear estudiante y continuar"
                        highlighted: true
                        onClicked: wizard.createStudent()
                    }
                }
            }

            ScrollView {
                id: detailsStepScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ColumnLayout {
                    width: detailsStepScroll.availableWidth
                    spacing: 10
                    Label {
                        Layout.fillWidth: true
                        text: "Estudiante: " + wizard.studentLabel
                        color: appWindow.successColor
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 10
                        Label { text: "Curso" }
                        ComboBox {
                            id: course
                            Layout.fillWidth: true
                            model: [{ id: "", label: "PENDIENTE DE ASIGNACIÓN" }].concat(
                                desktopBackend.courses.filter(function(item) {
                                return item.active
                                })
                            )
                            textRole: "label"
                            valueRole: "id"
                            onActivated: wizard.updateCourseFees()
                        }
                        Label { text: "Fecha de matrícula" }
                        TextField {
                            id: enrollmentDate
                            Layout.fillWidth: true
                            placeholderText: "AAAA-MM-DD"
                        }
                        Label { text: "Costo matrícula" }
                        TextField {
                            id: enrollmentFee
                            Layout.fillWidth: true
                            readOnly: !Boolean(course.currentValue)
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                        Label { text: "Mensualidad" }
                        TextField {
                            id: monthlyFee
                            Layout.fillWidth: true
                            readOnly: !Boolean(course.currentValue)
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: desktopBackend.courses.filter(function(item) {
                            return item.active
                        }).length === 0
                        text: wizard.withoutStudent
                              ? "No hay cursos activos. Agrega un curso desde la sección «Cursos» para reservar un cupo."
                              : "No hay cursos activos. Puedes guardar una matrícula pendiente o agregar un curso."
                        color: appWindow.errorColor
                        wrapMode: Text.Wrap
                    }
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
                text: wizard.step === 0 ? "1 de 2 · Estudiante" : "2 de 2 · Curso y detalles"
                color: appWindow.secondaryTextColor
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Cancelar"
                onClicked: wizard.close()
            }
            Button {
                visible: wizard.step === 1
                text: "Atrás"
                onClicked: wizard.step = 0
            }
            Button {
                visible: wizard.step === 1
                enabled: wizard.withoutStudent
                         ? course.currentIndex > 0
                         : Boolean(wizard.studentId) && course.currentIndex >= 0
                text: "Guardar matrícula"
                highlighted: true
                onClicked: wizard.saveEnrollment()
            }
        }
    }
}
