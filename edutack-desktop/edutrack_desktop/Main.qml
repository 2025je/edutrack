import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: appWindow
    width: 1280
    height: 740
    minimumWidth: 980
    minimumHeight: 620
    visible: true
    title: "EduTrack Desktop"
    property bool darkMode: false
    readonly property color pageBackgroundColor: appTheme.background
    readonly property color surfaceColor: appTheme.surface
    readonly property color nestedSurfaceColor: appTheme.raisedSurface
    readonly property color borderColor: appTheme.outline
    readonly property color dividerColor: appTheme.divider
    readonly property color primaryTextColor: appTheme.primaryText
    readonly property color secondaryTextColor: appTheme.secondaryText
    readonly property color successColor: appTheme.success
    readonly property color successSurfaceColor: appTheme.successSurface
    readonly property color errorColor: appTheme.error
    readonly property color errorSurfaceColor: appTheme.errorSurface
    readonly property color accentSurfaceColor: appTheme.accentSurface
    readonly property color accentTextColor: appTheme.accent
    color: appTheme.background
    Material.theme: appTheme.controlsTheme
    Material.primary: appTheme.primary
    Material.accent: Material.Teal
    property string pendingPackagePath: ""
    property var desktopBackend: null
    property int currentPage: 0
    property bool showEnrollmentEditor: false
    property bool editingEnrollment: Boolean(
        appWindow.showEnrollmentEditor
        && backend.hasWorkspace
        && backend.selectedEnrollment
        && backend.selectedEnrollment.id
    )

    AppTheme {
        id: appTheme
        darkMode: appWindow.darkMode
    }

    function optionIndex(options, value) {
        for (var index = 0; index < options.length; index++) {
            if (String(options[index].id) === String(value === null ? "" : value))
                return index
        }
        return 0
    }

    function loadStudentForm() {
        var student = backend.selectedStudent
        lastName.text = student.last_name || ""
        firstName.text = student.first_name || ""
        documentNumber.text = student.document_number || ""
        phones.text = student.phone_numbers ? student.phone_numbers.join(", ") : ""
    }

    function loadEnrollmentForm() {
        var enrollment = backend.selectedEnrollment
        studentSelect.currentIndex = optionIndex(backend.studentOptions, enrollment.student_id || "")
        courseSelect.currentIndex = optionIndex(backend.courseOptions, enrollment.course_id || "")
        enrollmentDate.text = enrollment.enrollment_date || Qt.formatDate(new Date(), "yyyy-MM-dd")
        enrollmentFee.text = enrollment.enrollment_fee || ""
        monthlyFee.text = enrollment.monthly_fee || ""
        recordCode.text = enrollment.record_code || ""
        imageQuality.currentIndex = enrollment.record_image_quality === 60 ? 0
                                     : enrollment.record_image_quality === 90 ? 2 : 1
    }

    function saveEnrollment() {
        var selectedPromoters = []
        for (var index = 0; index < promoterRepeater.count; index++) {
            var item = promoterRepeater.itemAt(index)
            if (item && item.checked)
                selectedPromoters.push(item.promoterId)
        }
        backend.saveEnrollment(backend.selectedEnrollment.id || "", {
            student_id: studentSelect.currentValue,
            course_id: courseSelect.currentValue,
            enrollment_date: enrollmentDate.text,
            enrollment_fee: enrollmentFee.text,
            monthly_fee: monthlyFee.text,
            record_code: recordCode.text,
            record_image_quality: imageQuality.currentValue,
            promoter_ids: selectedPromoters
        })
    }

    function openCourseDialog() {
        courseWizardDialog.openWizard()
    }

    function openStudentWizard() {
        studentWizardDialog.openWizard()
    }

    function openEnrollmentWizard() {
        enrollmentWizardDialog.openWizard()
    }

    FileDialog {
        id: openDialog
        title: "Abrir datos de una sede"
        fileMode: FileDialog.OpenFile
        nameFilters: ["EduTrack (*.edutrack *.zip)", "Todos los archivos (*)"]
        onAccepted: {
            appWindow.pendingPackagePath = selectedFile.toLocalFile()
            if (backend.hasWorkspace)
                replaceDialog.open()
            else
                backend.openPackage(appWindow.pendingPackagePath)
        }
    }

    Dialog {
        id: replaceDialog
        title: "Reemplazar el espacio de trabajo"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        Label {
            text: "Abrir otro archivo reemplaza los datos locales guardados en este dispositivo. ¿Deseas continuar?"
            wrapMode: Text.Wrap
        }
        onAccepted: backend.openPackage(appWindow.pendingPackagePath)
        onRejected: appWindow.pendingPackagePath = ""
    }

    FileDialog {
        id: saveDialog
        title: "Guardar archivo de sincronización"
        fileMode: FileDialog.SaveFile
        currentFile: backend.isNewCampus
                     ? "edutrack-sede-inicial.edutrack"
                     : "edutrack-sincronizacion.edutrack"
        nameFilters: ["EduTrack (*.edutrack)"]
        onAccepted: backend.exportPackage(selectedFile.toLocalFile())
    }

    FileDialog {
        id: imageDialog
        title: "Seleccionar imagen de ficha"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Imágenes (*.jpg *.jpeg *.png *.webp)"]
        onAccepted: backend.attachEnrollmentImage(selectedFile.toLocalFile())
    }

    Dialog {
        id: promoterDialog
        title: "Agregar promotor"
        modal: true
        width: 380
        standardButtons: Dialog.Save | Dialog.Cancel
        anchors.centerIn: parent
        TextField {
            id: promoterNameInput
            width: parent.width
            placeholderText: "Nombre del promotor"
        }
        onAccepted: backend.createPromoter(promoterNameInput.text)
    }

    CourseWizardDialog {
        id: courseWizardDialog
        objectName: "courseWizardDialog"
        appWindow: appWindow
        desktopBackend: backend
    }

    StudentWizardDialog {
        id: studentWizardDialog
        objectName: "studentWizardDialog"
        appWindow: appWindow
        desktopBackend: backend
    }

    EnrollmentWizardDialog {
        id: enrollmentWizardDialog
        objectName: "enrollmentWizardDialog"
        appWindow: appWindow
        desktopBackend: backend
    }

    Connections {
        target: backend
        function onSelectionChanged() {
            appWindow.loadStudentForm()
            appWindow.loadEnrollmentForm()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 16

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 88
            radius: 14
            color: Material.primary
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 24
                anchors.rightMargin: 20
                spacing: 18
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Label {
                        text: "EduTrack Desktop"
                        color: appTheme.headerText
                        font.pixelSize: 23
                        font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true
                        text: backend.campusName
                        color: appTheme.headerSecondary
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }
                }
                Button {
                    text: "Abrir archivo de sede"
                    flat: true
                    icon.source: Qt.resolvedUrl("icons/folder-open.svg")
                    icon.width: 18
                    icon.height: 18
                    icon.color: appTheme.headerText
                    Material.foreground: appTheme.headerText
                    onClicked: openDialog.open()
                }
                Button {
                    text: appWindow.darkMode ? "Modo claro" : "Modo nocturno"
                    flat: true
                    icon.source: appWindow.darkMode
                                  ? Qt.resolvedUrl("icons/sun.svg")
                                  : Qt.resolvedUrl("icons/moon.svg")
                    icon.width: 18
                    icon.height: 18
                    icon.color: appTheme.headerText
                    Material.foreground: appTheme.headerText
                    onClicked: appWindow.darkMode = !appWindow.darkMode
                }
                Button {
                    id: exportButton
                    text: backend.isNewCampus
                          ? "Exportar sede inicial"
                          : "Exportar sincronización"
                    icon.source: Qt.resolvedUrl("icons/export.svg")
                    icon.width: 18
                    icon.height: 18
                    icon.color: appTheme.headerText
                    Material.foreground: appTheme.headerText
                    highlighted: true
                    visible: backend.hasWorkspace
                    enabled: backend.hasWorkspace
                    background: Rectangle {
                        implicitWidth: 190
                        implicitHeight: 42
                        radius: 8
                        color: exportButton.down
                               ? appTheme.exportButtonPressed : appTheme.exportButton
                    }
                    onClicked: saveDialog.open()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: statusMessage.implicitHeight + 24
            radius: 10
            visible: statusMessage.text.length > 0
            property bool successful: backend.errorMessage.indexOf("correctamente") >= 0
                                      || backend.errorMessage.indexOf("guardado") >= 0
            color: successful ? appWindow.successSurfaceColor : appWindow.errorSurfaceColor
            Label {
                id: statusMessage
                anchors.fill: parent
                anchors.margins: 12
                text: backend.errorMessage
                color: parent.successful ? appWindow.successColor : appWindow.errorColor
                wrapMode: Text.Wrap
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !backend.hasWorkspace
            radius: 14
            color: appWindow.surfaceColor
            border.color: appWindow.borderColor
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 560)
                spacing: 14
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 52
                    height: 52
                    radius: 26
                    color: appWindow.accentSurfaceColor
                    Label {
                        anchors.centerIn: parent
                        text: "1"
                        color: appWindow.accentTextColor
                        font.pixelSize: 23
                        font.bold: true
                    }
                }
                Label {
                    Layout.fillWidth: true
                    text: "Prepara una sede nueva sin conexión"
                    horizontalAlignment: Text.AlignHCenter
                    color: appWindow.primaryTextColor
                    font.pixelSize: 25
                    font.bold: true
                    wrapMode: Text.Wrap
                }
                Label {
                    Layout.fillWidth: true
                    text: "Ingresa los datos básicos y crea aquí cursos, estudiantes y matrículas. Al importar el paquete inicial, la web creará la sede con toda su información."
                    horizontalAlignment: Text.AlignHCenter
                    color: appWindow.secondaryTextColor
                    font.pixelSize: 15
                    wrapMode: Text.Wrap
                }
                TextField {
                    id: newCampusNameInput
                    Layout.fillWidth: true
                    placeholderText: "Nombre de la sede"
                    maximumLength: 120
                }
                TextField {
                    id: newCampusAddressInput
                    Layout.fillWidth: true
                    placeholderText: "Dirección (opcional)"
                    maximumLength: 200
                }
                Button {
                    id: createWorkspaceButton
                    Layout.alignment: Qt.AlignHCenter
                    text: "Crear sede en este dispositivo"
                    icon.source: Qt.resolvedUrl("icons/add.svg")
                    icon.color: appTheme.headerText
                    Material.foreground: appTheme.headerText
                    highlighted: true
                    background: Rectangle {
                        implicitWidth: 250
                        implicitHeight: 44
                        radius: 8
                        color: createWorkspaceButton.down
                               ? appTheme.createButtonPressed : appTheme.createButton
                    }
                    onClicked: backend.createWorkspace(
                        newCampusNameInput.text,
                        newCampusAddressInput.text
                    )
                }
                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: "Abrir una sede existente"
                    flat: true
                    onClicked: openDialog.open()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16
            visible: backend.hasWorkspace

            Rectangle {
                Layout.preferredWidth: 190
                Layout.fillHeight: true
                radius: 14
                color: appWindow.surfaceColor
                border.color: appWindow.borderColor
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8
                    Label {
                        Layout.leftMargin: 8
                        Layout.bottomMargin: 6
                        text: "GESTIÓN"
                        color: appWindow.secondaryTextColor
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Button {
                        Layout.fillWidth: true
                        text: "Estudiantes"
                        icon.source: Qt.resolvedUrl("icons/students.svg")
                        icon.width: 20
                        icon.height: 20
                        icon.color: checked ? appTheme.headerText : appTheme.primaryTextColor
                        checkable: true
                        checked: appWindow.currentPage === 0
                        onClicked: appWindow.currentPage = 0
                    }
                    Button {
                        Layout.fillWidth: true
                        text: "Matrículas"
                        icon.source: Qt.resolvedUrl("icons/enrollments.svg")
                        icon.width: 20
                        icon.height: 20
                        icon.color: checked ? appTheme.headerText : appTheme.primaryTextColor
                        checkable: true
                        checked: appWindow.currentPage === 1
                        onClicked: appWindow.currentPage = 1
                    }
                    Button {
                        Layout.fillWidth: true
                        text: "Cursos"
                        icon.source: Qt.resolvedUrl("icons/courses.svg")
                        icon.width: 20
                        icon.height: 20
                        icon.color: checked ? appTheme.headerText : appTheme.primaryTextColor
                        checkable: true
                        checked: appWindow.currentPage === 2
                        onClicked: appWindow.currentPage = 2
                    }
                    Item { Layout.fillHeight: true }
                    Label {
                        Layout.fillWidth: true
                        text: backend.campusName
                        color: appWindow.secondaryTextColor
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: appWindow.currentPage === 0
                radius: 14
                color: appWindow.surfaceColor
                border.color: appWindow.borderColor
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12
                    ScrollView {
                        id: studentScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOn
                        ColumnLayout {
                            width: studentScroll.availableWidth
                            spacing: 12
                            Label {
                                text: "Estudiantes"
                                font.pixelSize: 18
                                font.bold: true
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Button {
                                    text: "Nuevo estudiante"
                                    icon.source: Qt.resolvedUrl("icons/add.svg")
                                    icon.color: appTheme.primaryTextColor
                                    enabled: backend.hasWorkspace
                                    onClicked: appWindow.openStudentWizard()
                                }
                                Label {
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignRight
                                    text: backend.students.length + " registros"
                                    color: appWindow.secondaryTextColor
                                }
                            }
                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 170
                                clip: true
                                model: backend.students
                                delegate: ItemDelegate {
                                    width: ListView.view.width
                                    text: modelData.label + (modelData.server_id ? "" : " · nuevo")
                                    highlighted: appWindow.desktopBackend
                                                 ? appWindow.desktopBackend.selectedStudent.id === modelData.id
                                                 : false
                                    onClicked: {
                                        if (appWindow.desktopBackend)
                                            appWindow.desktopBackend.selectStudent(modelData.id)
                                    }
                                }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: 10
                                Label { text: "Apellidos" }
                                TextField {
                                    id: lastName
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    placeholderText: "Apellidos"
                                }
                                Label { text: "Nombres" }
                                TextField {
                                    id: firstName
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    placeholderText: "Nombres"
                                }
                                Label { text: "DNI" }
                                TextField {
                                    id: documentNumber
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    placeholderText: "Opcional"
                                }
                                Label { text: "Celulares" }
                                TextField {
                                    id: phones
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    placeholderText: "9 dígitos, separados por coma"
                                }
                            }
                        }
                    }
                    Button {
                        text: "Guardar estudiante"
                        enabled: backend.hasWorkspace
                                 && Boolean(backend.selectedStudent.id)
                        onClicked: backend.saveStudent(
                            backend.selectedStudent.id || "",
                            lastName.text,
                            firstName.text,
                            documentNumber.text,
                            phones.text
                        )
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: appWindow.currentPage === 1
                radius: 14
                color: appWindow.surfaceColor
                border.color: appWindow.borderColor
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12
                    ScrollView {
                        id: enrollmentScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOn
                        ColumnLayout {
                            width: enrollmentScroll.availableWidth
                            spacing: 12
                            Label {
                                text: "Matrículas"
                                font.pixelSize: 18
                                font.bold: true
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Button {
                                    text: "Nueva matrícula guiada"
                                    icon.source: Qt.resolvedUrl("icons/enrollments.svg")
                                    icon.color: appTheme.primaryTextColor
                                    enabled: backend.hasWorkspace
                                    onClicked: appWindow.openEnrollmentWizard()
                                }
                                Button {
                                    text: "Nuevo curso"
                                    icon.source: Qt.resolvedUrl("icons/add.svg")
                                    icon.color: appTheme.primaryTextColor
                                    enabled: backend.hasWorkspace
                                    onClicked: appWindow.openCourseDialog()
                                }
                                Button {
                                    visible: backend.hasWorkspace
                                             && Boolean(backend.selectedEnrollment.id)
                                    text: appWindow.showEnrollmentEditor
                                          ? "Ocultar edición" : "Editar seleccionada"
                                    icon.source: Qt.resolvedUrl("icons/enrollments.svg")
                                    icon.color: appTheme.primaryTextColor
                                    onClicked: appWindow.showEnrollmentEditor =
                                               !appWindow.showEnrollmentEditor
                                }
                                Label {
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignRight
                                    text: backend.enrollments.length + " registros"
                                    color: appWindow.secondaryTextColor
                                }
                            }
                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 170
                                clip: true
                                model: backend.enrollments
                                delegate: ItemDelegate {
                                    width: ListView.view.width
                                    text: modelData.label + (modelData.server_id ? "" : " · nueva")
                                    highlighted: appWindow.desktopBackend
                                                 ? appWindow.desktopBackend.selectedEnrollment.id === modelData.id
                                                 : false
                                    onClicked: {
                                        if (appWindow.desktopBackend) {
                                            appWindow.showEnrollmentEditor = false
                                            appWindow.desktopBackend.selectEnrollment(modelData.id)
                                        }
                                    }
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                visible: backend.hasWorkspace && !appWindow.editingEnrollment
                                text: backend.selectedEnrollment && backend.selectedEnrollment.id
                                      ? "Matrícula seleccionada. Usa «Editar seleccionada» para modificar sus datos."
                                      : backend.enrollments.length > 0
                                        ? "Selecciona una matrícula para editarla o usa «Nueva matrícula guiada» para registrar otra."
                                        : "Para registrar una matrícula, usa «Nueva matrícula guiada»."
                                color: appWindow.secondaryTextColor
                                wrapMode: Text.Wrap
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                visible: appWindow.editingEnrollment
                                height: 1
                                color: appWindow.dividerColor
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                visible: appWindow.editingEnrollment
                                columns: 2
                                columnSpacing: 10
                                Label { text: "Estudiante" }
                                ComboBox {
                                    id: studentSelect
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    model: backend.studentOptions
                                    textRole: "label"
                                    valueRole: "id"
                                }
                                Label { text: "Curso" }
                                ComboBox {
                                    id: courseSelect
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    model: backend.courseOptions
                                    textRole: "label"
                                    valueRole: "id"
                                }
                                Label { text: "Fecha" }
                                TextField {
                                    id: enrollmentDate
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    placeholderText: "AAAA-MM-DD"
                                }
                                Label { text: "Costo matrícula" }
                                TextField {
                                    id: enrollmentFee
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                                }
                                Label { text: "Mensualidad" }
                                TextField {
                                    id: monthlyFee
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                                }
                                Label { text: "Código de ficha" }
                                TextField {
                                    id: recordCode
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    placeholderText: "Opcional"
                                    inputMethodHints: Qt.ImhDigitsOnly
                                }
                                Label { text: "Calidad de imagen" }
                                ComboBox {
                                    id: imageQuality
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
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
                            RowLayout {
                                Layout.fillWidth: true
                                visible: appWindow.editingEnrollment
                                Label {
                                    Layout.fillWidth: true
                                    text: backend.enrollmentImageName
                                    elide: Text.ElideMiddle
                                    color: appWindow.secondaryTextColor
                                }
                                Button {
                                    text: "Adjuntar/reemplazar imagen"
                                    enabled: backend.hasWorkspace
                                             && Boolean(backend.selectedEnrollment.id)
                                             && Boolean(backend.selectedEnrollment.record_code)
                                    onClicked: imageDialog.open()
                                }
                                Button {
                                    text: "Quitar imagen"
                                    enabled: backend.hasWorkspace
                                             && Boolean(backend.selectedEnrollment.record_image)
                                    onClicked: backend.clearEnrollmentImage()
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                visible: appWindow.editingEnrollment
                                Label {
                                    Layout.fillWidth: true
                                    text: "Promotores"
                                    font.bold: true
                                }
                                Button {
                                    text: "Nuevo promotor"
                                    visible: backend.isNewCampus
                                    enabled: backend.isNewCampus
                                    onClicked: {
                                        promoterNameInput.text = ""
                                        promoterDialog.open()
                                    }
                                }
                            }
                            ScrollView {
                                visible: appWindow.editingEnrollment
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(
                                    Math.max(backend.promoterOptions.length * 64, 128),
                                    256
                                )
                                clip: true
                                Flow {
                                    width: parent.width
                                    Repeater {
                                        id: promoterRepeater
                                        model: backend.promoterOptions
                                        CheckBox {
                                            required property var modelData
                                            property int promoterId: modelData.id
                                            text: modelData.name + (modelData.active ? "" : " (inactivo)")
                                            checked: appWindow.desktopBackend
                                                     && appWindow.desktopBackend.selectedEnrollment.promoter_ids
                                                     ? appWindow.desktopBackend.selectedEnrollment.promoter_ids.indexOf(modelData.id) >= 0
                                                     : false
                                            enabled: appWindow.desktopBackend
                                                     ? appWindow.desktopBackend.hasWorkspace
                                                     : false
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Button {
                        text: "Guardar matrícula"
                        visible: appWindow.editingEnrollment
                        enabled: appWindow.editingEnrollment
                        onClicked: appWindow.saveEnrollment()
                    }
                }
            }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    visible: appWindow.currentPage === 2
                                    radius: 14
                                    color: appWindow.surfaceColor
                                    border.color: appWindow.borderColor
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        spacing: 14
                                        RowLayout {
                                            Layout.fillWidth: true
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 3
                                                Label {
                                                    text: "Cursos"
                                                    font.pixelSize: 20
                                                    font.bold: true
                                                }
                                                Label {
                                                    text: "Consulta los estudiantes matriculados en cada curso."
                                                    color: appWindow.secondaryTextColor
                                                    wrapMode: Text.Wrap
                                                }
                                            }
                                            Button {
                                                text: "Nuevo curso"
                                                icon.source: Qt.resolvedUrl("icons/add.svg")
                                                icon.color: appTheme.headerText
                                                highlighted: true
                                                enabled: backend.hasWorkspace
                                                onClicked: appWindow.openCourseDialog()
                                            }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.fillHeight: true
                                            spacing: 12
                                            Rectangle {
                                                Layout.preferredWidth: 310
                                                Layout.fillHeight: true
                                                radius: 10
                                                color: appWindow.nestedSurfaceColor
                                                border.color: appWindow.dividerColor
                                                ColumnLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 12
                                                    spacing: 8
                                                    Label {
                                                        text: backend.courses.length + " cursos"
                                                        color: appWindow.secondaryTextColor
                                                        font.bold: true
                                                    }
                                                    ListView {
                                                        Layout.fillWidth: true
                                                        Layout.fillHeight: true
                                                        clip: true
                                                        model: backend.courses
                                                        delegate: ItemDelegate {
                                                            width: ListView.view.width
                                                            text: modelData.label
                                                                  + (modelData.active ? "" : " · inactivo")
                                                                  + " · " + modelData.student_count + " estudiantes"
                                                            highlighted: backend.selectedCourse.id === modelData.id
                                                            onClicked: backend.selectCourse(modelData.id)
                                                        }
                                                    }
                                                    Label {
                                                        Layout.fillWidth: true
                                                        visible: backend.courses.length === 0
                                                        text: "Todavía no hay cursos. Usa «Nuevo curso» para agregar uno."
                                                        color: appWindow.secondaryTextColor
                                                        wrapMode: Text.Wrap
                                                    }
                                                }
                                            }
                                            }
                                            Rectangle {
                                                Layout.fillWidth: true
                                                Layout.fillHeight: true
                                                radius: 10
                                                color: appWindow.surfaceColor
                                                border.color: appWindow.dividerColor
                                                ColumnLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 16
                                                    spacing: 8
                                                    Label {
                                                        Layout.fillWidth: true
                                                        text: backend.selectedCourse.id
                                                              ? backend.selectedCourse.name
                                                              : "Selecciona un curso"
                                                        color: appWindow.primaryTextColor
                                                        font.pixelSize: 18
                                                        font.bold: true
                                                        wrapMode: Text.Wrap
                                                    }
                                                    Label {
                                                        Layout.fillWidth: true
                                                        visible: Boolean(backend.selectedCourse.id)
                                                        text: backend.selectedCourse.id
                                                              ? backend.selectedCourse.schedule
                                                                + " · Grupo " + backend.selectedCourse.group
                                                                + " · Capacidad " + backend.selectedCourse.capacity
                                                              : ""
                                                        color: appWindow.secondaryTextColor
                                                        wrapMode: Text.Wrap
                                                    }
                                                    Rectangle {
                                                        Layout.fillWidth: true
                                                        height: 1
                                                        color: appWindow.dividerColor
                                                    }
                                                    Label {
                                                        text: backend.courseStudents.length + " estudiantes"
                                                        color: appWindow.secondaryTextColor
                                                        font.bold: true
                                                    }
                                                    ListView {
                                                        Layout.fillWidth: true
                                                        Layout.fillHeight: true
                                                        clip: true
                                                        model: backend.courseStudents
                                                        delegate: ItemDelegate {
                                                            width: ListView.view.width
                                                            text: modelData.label
                                                        }
                                                    }
                                                    Label {
                                                        Layout.fillWidth: true
                                                        visible: Boolean(backend.selectedCourse.id)
                                                                 && backend.courseStudents.length === 0
                                                        text: "Este curso todavía no tiene estudiantes matriculados."
                                                        color: appWindow.secondaryTextColor
                                                        wrapMode: Text.Wrap
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
        }
    }
