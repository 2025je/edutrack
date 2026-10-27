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
    property var promoterIds: []
    property bool creatingStudent: false
    property string errorMessage: ""

    title: step === 0 ? "Nueva matrícula · Paso 1 de 2"
                      : "Nueva matrícula · Paso 2 de 2"
    modal: true
    width: Math.min(appWindow.width - 48, 760)
    height: Math.min(appWindow.height - 56, 590)
    anchors.centerIn: parent

    function openWizard() {
        appWindow.showEnrollmentEditor = false
        step = 0
        studentId = ""
        studentLabel = ""
        studentMatches = []
        promoterIds = []
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
        recordCode.text = ""
        course.currentIndex = 0
        open()
    }

    function searchStudents(query) {
        var normalized = String(query).trim().toLowerCase()
        var matches = []
        studentId = ""
        studentLabel = ""
        if (normalized.length >= 2) {
            for (var index = 0; index < desktopBackend.students.length; index++) {
                var student = desktopBackend.students[index]
                var phones = student.phone_numbers ? student.phone_numbers.join(" ") : ""
                var searchable = (student.label + " "
                                  + (student.document_number || "") + " "
                                  + phones).toLowerCase()
                if (student.active && searchable.indexOf(normalized) >= 0)
                    matches.push(student)
            }
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
        creatingStudent = false
        step = 1
        errorMessage = ""
    }

    function togglePromoter(promoterId, checked) {
        var selected = promoterIds.slice()
        var index = selected.indexOf(promoterId)
        if (checked && index < 0)
            selected.push(promoterId)
        else if (!checked && index >= 0)
            selected.splice(index, 1)
        promoterIds = selected
    }

    function saveEnrollment() {
        var saved = desktopBackend.saveEnrollment("", {
            student_id: studentId,
            course_id: course.currentValue,
            enrollment_date: enrollmentDate.text,
            enrollment_fee: enrollmentFee.text,
            monthly_fee: monthlyFee.text,
            record_code: recordCode.text,
            record_image_quality: imageQuality.currentValue,
            promoter_ids: promoterIds
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
                        Layout.fillWidth: true
                        placeholderText: "Buscar estudiante"
                        onTextChanged: wizard.searchStudents(text)
                    }
                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(wizard.studentMatches.length * 52, 200)
                        visible: wizard.studentMatches.length > 0
                        clip: true
                        model: wizard.studentMatches
                        delegate: ItemDelegate {
                            width: ListView.view.width
                            text: modelData.label
                                  + (modelData.document_number
                                     ? " · DNI " + modelData.document_number : "")
                                  + (modelData.phone_numbers.length
                                     ? " · " + modelData.phone_numbers.join(", ") : "")
                            highlighted: wizard.studentId === modelData.id
                            onClicked: wizard.chooseStudent(modelData.id)
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: studentSearch.text.trim().length >= 2
                                 && wizard.studentMatches.length === 0
                        text: "No encontramos coincidencias. Puedes registrar un estudiante nuevo."
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
                            model: desktopBackend.courses.filter(function(item) {
                                return item.active
                            })
                            textRole: "label"
                            valueRole: "id"
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
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                        Label { text: "Mensualidad" }
                        TextField {
                            id: monthlyFee
                            Layout.fillWidth: true
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                        Label { text: "Código de ficha" }
                        TextField {
                            id: recordCode
                            Layout.fillWidth: true
                            placeholderText: "Opcional"
                            inputMethodHints: Qt.ImhDigitsOnly
                        }
                        Label { text: "Calidad de imagen" }
                        ComboBox {
                            id: imageQuality
                            Layout.fillWidth: true
                            model: [
                                { label: "Baja · 60%", value: 60 },
                                { label: "Recomendada · 80%", value: 80 },
                                { label: "Alta · 90%", value: 90 }
                            ]
                            textRole: "label"
                            valueRole: "value"
                            currentIndex: 1
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Promotores (opcional)"
                        font.bold: true
                    }
                    Flow {
                        Layout.fillWidth: true
                        Repeater {
                            model: desktopBackend.promoterOptions.filter(function(promoter) {
                                return promoter.active
                            })
                            CheckBox {
                                required property var modelData
                                text: modelData.name
                                checked: wizard.promoterIds.indexOf(modelData.id) >= 0
                                onToggled: wizard.togglePromoter(modelData.id, checked)
                            }
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: desktopBackend.courses.filter(function(item) {
                            return item.active
                        }).length === 0
                        text: "No hay cursos activos. Agrega un curso desde la sección «Cursos» y vuelve a la matrícula."
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
                enabled: course.currentIndex >= 0
                text: "Guardar matrícula"
                highlighted: true
                onClicked: wizard.saveEnrollment()
            }
        }
    }
}
