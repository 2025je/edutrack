import QtQuick
import QtQuick.Controls.Material
import QtQuick.Controls
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
    property string pendingDatabasePath: ""
    property string pendingDatabaseAction: ""
    property var desktopBackend: null
    property int currentPage: 0
    property bool restoringSession: false
    property bool sessionTrackingEnabled: false
    property string sessionSnapshot: sessionTrackingEnabled
                                         ? JSON.stringify(collectSessionState()) : ""
    property bool creatingCampus: false
    property bool showEnrollmentEditor: false
    property bool editingCourse: false
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

    function activeCampusPath() {
        var index = backend.activeCampusIndex
        var campuses = backend.campuses
        return index >= 0 && index < campuses.length ? campuses[index].path : ""
    }

    function hasOption(items, value) {
        if (value === undefined || value === null || value === "")
            return false
        for (var index = 0; index < items.length; index++) {
            if (String(items[index].id) === String(value))
                return true
        }
        return false
    }

    function restoreSessionState() {
        var serialized = sessionStore.loadState()
        var state = {}
        if (serialized) {
            try {
                state = JSON.parse(serialized)
            } catch (error) {
                console.error("No se pudo restaurar el estado de sesión:", error)
            }
        } else if (sessionStore.errorMessage) {
            console.error("No se pudo leer el estado de sesión:", sessionStore.errorMessage)
        }
        if (!state || state.version !== 1)
            state = {}

        appWindow.restoringSession = true
        appWindow.darkMode = state.darkMode === true
        appWindow.currentPage = Math.max(0, Math.min(2, Number(state.currentPage) || 0))
        if (state.window && typeof state.window === "object") {
            if (isFinite(Number(state.window.width)))
                appWindow.width = Math.max(appWindow.minimumWidth, Number(state.window.width))
            if (isFinite(Number(state.window.height)))
                appWindow.height = Math.max(appWindow.minimumHeight, Number(state.window.height))
            if (isFinite(Number(state.window.x)))
                appWindow.x = Number(state.window.x)
            if (isFinite(Number(state.window.y)))
                appWindow.y = Number(state.window.y)
        }

        if (state.campusPath === appWindow.activeCampusPath()) {
            var selection = state.selection || {}
            if (appWindow.hasOption(backend.students, selection.studentId))
                backend.selectStudent(String(selection.studentId))
            if (appWindow.hasOption(backend.enrollments, selection.enrollmentId))
                backend.selectEnrollment(String(selection.enrollmentId))
            if (appWindow.hasOption(backend.courses, selection.courseId))
                backend.selectCourse(Number(selection.courseId))

            var studentForm = state.studentForm || {}
            lastName.text = studentForm.lastName || ""
            firstName.text = studentForm.firstName || ""
            documentNumber.text = studentForm.documentNumber || ""
            phones.text = studentForm.phones || ""

            var enrollmentForm = state.enrollmentForm || {}
            studentSelect.currentIndex = appWindow.optionIndex(
                backend.studentOptions,
                enrollmentForm.studentId || ""
            )
            courseSelect.currentIndex = appWindow.optionIndex(
                backend.courseOptions,
                enrollmentForm.courseId || ""
            )
            enrollmentDate.text = enrollmentForm.date || ""
            enrollmentFee.text = enrollmentForm.enrollmentFee || ""
            monthlyFee.text = enrollmentForm.monthlyFee || ""
            appWindow.showEnrollmentEditor = state.showEnrollmentEditor === true
                                              && Boolean(backend.selectedEnrollment.id)

            var courseForm = state.courseForm || {}
            appWindow.editingCourse = state.editingCourse === true
                                      && Boolean(backend.selectedCourse.id)
            appWindow.loadCourseForm()
            if (appWindow.editingCourse) {
                courseNameEdit.text = courseForm.name || courseNameEdit.text
                courseScheduleEdit.text = courseForm.schedule || courseScheduleEdit.text
                courseGroupEdit.text = courseForm.group || courseGroupEdit.text
                courseCapacityEdit.text = courseForm.capacity || courseCapacityEdit.text
                courseStartDateEdit.text = courseForm.startDate || courseStartDateEdit.text
                courseEnrollmentFeeEdit.text = courseForm.enrollmentFee
                                              || courseEnrollmentFeeEdit.text
                courseMonthlyFeeEdit.text = courseForm.monthlyFee
                                           || courseMonthlyFeeEdit.text
                courseActiveEdit.checked = courseForm.active !== undefined
                                           ? courseForm.active
                                           : courseActiveEdit.checked
            }

            var campusForm = state.campusForm || {}
            newCampusNameInput.text = campusForm.name || ""
            newCampusAddressInput.text = campusForm.address || ""
            appWindow.creatingCampus = state.creatingCampus === true

            courseWizardDialog.restoreSessionState(state.courseWizard)
            enrollmentWizardDialog.restoreSessionState(state.enrollmentWizard)
        }

        appWindow.restoringSession = false
        appWindow.sessionTrackingEnabled = true
    }

    function collectSessionState() {
        return {
            version: 1,
            campusPath: appWindow.activeCampusPath(),
            currentPage: appWindow.currentPage,
            darkMode: appWindow.darkMode,
            window: {
                x: appWindow.x,
                y: appWindow.y,
                width: appWindow.width,
                height: appWindow.height
            },
            creatingCampus: appWindow.creatingCampus,
            showEnrollmentEditor: appWindow.showEnrollmentEditor,
            editingCourse: appWindow.editingCourse,
            selection: {
                studentId: backend.selectedStudent.id || "",
                enrollmentId: backend.selectedEnrollment.id || "",
                courseId: backend.selectedCourse.id || ""
            },
            campusForm: {
                name: newCampusNameInput.text,
                address: newCampusAddressInput.text
            },
            studentForm: {
                lastName: lastName.text,
                firstName: firstName.text,
                documentNumber: documentNumber.text,
                phones: phones.text
            },
            enrollmentForm: {
                studentId: studentSelect.currentValue,
                courseId: courseSelect.currentValue,
                date: enrollmentDate.text,
                enrollmentFee: enrollmentFee.text,
                monthlyFee: monthlyFee.text
            },
            courseForm: {
                name: courseNameEdit.text,
                schedule: courseScheduleEdit.text,
                group: courseGroupEdit.text,
                capacity: courseCapacityEdit.text,
                startDate: courseStartDateEdit.text,
                enrollmentFee: courseEnrollmentFeeEdit.text,
                monthlyFee: courseMonthlyFeeEdit.text,
                active: courseActiveEdit.checked
            },
            courseWizard: courseWizardDialog.sessionState(),
            enrollmentWizard: enrollmentWizardDialog.sessionState()
        }
    }

    function persistSessionState() {
        if (!sessionStore.saveState(JSON.stringify(appWindow.collectSessionState())))
            console.error("No se pudo guardar el estado de sesión:", sessionStore.errorMessage)
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
    }

    function loadCourseForm() {
        var course = backend.selectedCourse
        courseNameEdit.text = course.name || ""
        courseScheduleEdit.text = course.schedule || ""
        courseGroupEdit.text = course.group || ""
        courseCapacityEdit.text = course.capacity ? String(course.capacity) : ""
        courseStartDateEdit.text = course.start_date || ""
        courseEnrollmentFeeEdit.text = course.enrollment_fee || ""
        courseMonthlyFeeEdit.text = course.monthly_fee || ""
        courseActiveEdit.checked = course.active !== false
    }

    function beginCourseEdit() {
        if (!backend.selectedCourse.id)
            return
        appWindow.loadCourseForm()
        appWindow.editingCourse = true
    }

    function cancelCourseEdit() {
        appWindow.editingCourse = false
        appWindow.loadCourseForm()
    }

    function saveCourseEdit() {
        if (!backend.saveCourse(
                Number(backend.selectedCourse.id),
                courseNameEdit.text,
                courseScheduleEdit.text,
                courseGroupEdit.text,
                courseStartDateEdit.text,
                courseEnrollmentFeeEdit.text,
                courseMonthlyFeeEdit.text,
                courseCapacityEdit.text,
                courseActiveEdit.checked
            ))
            return
        appWindow.editingCourse = false
    }

    function saveEnrollment() {
        backend.saveEnrollment(backend.selectedEnrollment.id || "", {
            student_id: studentSelect.currentValue,
            course_id: courseSelect.currentValue,
            enrollment_date: enrollmentDate.text,
            enrollment_fee: enrollmentFee.text,
            monthly_fee: monthlyFee.text
        })
    }

    function openCourseDialog() {
        courseWizardDialog.openWizard()
    }

    function openEnrollmentWizard() {
        enrollmentWizardDialog.openWizard()
    }

    Component.onCompleted: Qt.callLater(appWindow.restoreSessionState)
    onClosing: appWindow.persistSessionState()
    onSessionSnapshotChanged: {
        if (appWindow.sessionTrackingEnabled && !appWindow.restoringSession)
            sessionSaveTimer.restart()
    }

    Timer {
        id: sessionSaveTimer
        objectName: "sessionSaveTimer"
        interval: 300
        repeat: false
        onTriggered: appWindow.persistSessionState()
    }

    FileDialog {
        id: openDialog
        title: "Importar paquete de sede"
        fileMode: FileDialog.OpenFile
        nameFilters: ["EduTrack (*.edutrack *.zip)", "Todos los archivos (*)"]
        onAccepted: {
            appWindow.pendingPackagePath = selectedFile.toString()
            appWindow.pendingDatabaseAction = "import"
            databasePathDialog.open()
        }
    }

    FileDialog {
        id: databasePathDialog
        title: appWindow.pendingDatabaseAction === "create"
               ? "Guardar la base de datos de la nueva sede"
               : "Guardar la base de datos de la sede importada"
        fileMode: FileDialog.SaveFile
        currentFile: appWindow.pendingDatabaseAction === "create"
                     ? backend.suggestedDatabaseFileName(newCampusNameInput.text)
                     : "edutrack-sede-importada.sqlite3"
        nameFilters: ["Base de datos SQLite (*.sqlite3)"]
        onAccepted: {
            var databasePath = selectedFile.toString()
            var succeeded = false
            if (appWindow.pendingDatabaseAction === "create") {
                succeeded = backend.createWorkspace(
                    newCampusNameInput.text,
                    newCampusAddressInput.text,
                    databasePath
                )
            } else if (appWindow.pendingDatabaseAction === "import") {
                if (backend.isRegisteredDatabase(databasePath)) {
                    appWindow.pendingDatabasePath = databasePath
                    replaceImportDialog.open()
                } else {
                    succeeded = backend.openPackage(
                        appWindow.pendingPackagePath,
                        databasePath
                    )
                }
            }
            if (succeeded) {
                appWindow.creatingCampus = false
                appWindow.currentPage = 0
                appWindow.pendingPackagePath = ""
                newCampusNameInput.text = ""
                newCampusAddressInput.text = ""
            }
            appWindow.pendingDatabaseAction = ""
        }
        onRejected: appWindow.pendingDatabaseAction = ""
    }

    Dialog {
        id: replaceImportDialog
        title: "Actualizar los datos de esta sede"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        Label {
            text: "Se reemplazarán los datos locales de la sede elegida con el contenido del paquete. Continúa solo si ya importaste y confirmaste la sincronización en la web."
            wrapMode: Text.Wrap
        }
        onAccepted: {
            if (backend.openPackage(
                    appWindow.pendingPackagePath,
                    appWindow.pendingDatabasePath,
                    true
                )) {
                appWindow.creatingCampus = false
                appWindow.currentPage = 0
                newCampusNameInput.text = ""
                newCampusAddressInput.text = ""
            }
            appWindow.pendingPackagePath = ""
            appWindow.pendingDatabasePath = ""
        }
        onRejected: {
            appWindow.pendingPackagePath = ""
            appWindow.pendingDatabasePath = ""
        }
    }

    Dialog {
        id: closeCampusDialog
        title: "Cerrar sede activa"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        Label {
            text: "La sede se cerrará en Desktop, pero su base de datos y sus datos se conservarán. Podrás volver a abrirla desde el selector de sedes."
            wrapMode: Text.Wrap
        }
        onAccepted: {
            if (backend.closeCampus()) {
                appWindow.creatingCampus = false
                appWindow.currentPage = 0
            }
        }
    }

    FileDialog {
        id: localDatabaseDialog
        title: "Abrir una base de datos de sede"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Base de datos SQLite (*.sqlite3 *.db)", "Todos los archivos (*)"]
        onAccepted: {
            if (backend.openLocalDatabase(selectedFile.toString())) {
                appWindow.creatingCampus = false
                appWindow.currentPage = 0
            }
        }
    }

    FileDialog {
        id: saveDialog
        title: "Guardar archivo de sincronización"
        fileMode: FileDialog.SaveFile
        currentFile: backend.isNewCampus
                     ? "edutrack-sede-inicial.edutrack"
                     : "edutrack-sincronizacion.edutrack"
        nameFilters: ["EduTrack (*.edutrack)"]
        onAccepted: backend.exportPackage(selectedFile.toString())
    }

    CourseWizardDialog {
        id: courseWizardDialog
        objectName: "courseWizardDialog"
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
            appWindow.loadCourseForm()
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
                IconTextButton {
                    text: "Importar paquete"
                    symbolName: "folder_open"
                    symbolColor: appTheme.headerText
                    flat: true
                    Material.foreground: appTheme.headerText
                    onClicked: openDialog.open()
                }
                ComboBox {
                    id: campusSelector
                    Layout.preferredWidth: 190
                    visible: backend.campuses.length > 0 && !appWindow.creatingCampus
                    model: backend.campuses
                    textRole: "campus_name"
                    currentIndex: backend.activeCampusIndex
                    onActivated: function(index) {
                        if (backend.switchCampus(backend.campuses[index].path))
                            appWindow.currentPage = 0
                    }
                }
                IconTextButton {
                    text: "Nueva sede"
                    symbolName: "add"
                    symbolColor: appTheme.headerText
                    flat: true
                    visible: backend.hasWorkspace
                    Material.foreground: appTheme.headerText
                    onClicked: {
                        appWindow.creatingCampus = true
                        newCampusNameInput.text = ""
                        newCampusAddressInput.text = ""
                    }
                }
                IconTextButton {
                    text: "Abrir base"
                    symbolName: "folder_open"
                    symbolColor: appTheme.headerText
                    flat: true
                    visible: backend.hasWorkspace
                    Material.foreground: appTheme.headerText
                    onClicked: localDatabaseDialog.open()
                }
                Button {
                    text: "Cerrar sede"
                    flat: true
                    visible: backend.hasWorkspace
                    Material.foreground: appTheme.headerText
                    onClicked: closeCampusDialog.open()
                }
                IconTextButton {
                    text: appWindow.darkMode ? "Modo claro" : "Modo nocturno"
                    symbolName: appWindow.darkMode ? "light_mode" : "dark_mode"
                    symbolColor: appTheme.headerText
                    flat: true
                    Material.foreground: appTheme.headerText
                    onClicked: appWindow.darkMode = !appWindow.darkMode
                }
                IconTextButton {
                    id: exportButton
                    text: backend.isNewCampus
                          ? "Exportar sede inicial"
                          : "Exportar sincronización"
                    symbolName: "ios_share"
                    symbolColor: appTheme.headerText
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
            visible: !backend.hasWorkspace || appWindow.creatingCampus
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
                    text: "Ingresa los datos básicos y elige dónde guardar la base SQLite de esta sede. Cada sede conserva sus propios cursos, estudiantes y matrículas."
                    horizontalAlignment: Text.AlignHCenter
                    color: appWindow.secondaryTextColor
                    font.pixelSize: 15
                    wrapMode: Text.Wrap
                }
                UppercaseTextField {
                    id: newCampusNameInput
                    Layout.fillWidth: true
                    placeholderText: "Nombre de la sede"
                    maximumLength: 120
                }
                UppercaseTextField {
                    id: newCampusAddressInput
                    Layout.fillWidth: true
                    placeholderText: "Dirección (opcional)"
                    maximumLength: 200
                }
                IconTextButton {
                    id: createWorkspaceButton
                    Layout.alignment: Qt.AlignHCenter
                    text: "Elegir ubicación y crear sede"
                    symbolName: "add"
                    symbolColor: appTheme.headerText
                    Material.foreground: appTheme.headerText
                    highlighted: true
                    background: Rectangle {
                        implicitWidth: 250
                        implicitHeight: 44
                        radius: 8
                        color: createWorkspaceButton.down
                               ? appTheme.createButtonPressed : appTheme.createButton
                    }
                    onClicked: {
                        appWindow.pendingDatabaseAction = "create"
                        databasePathDialog.open()
                    }
                }
                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: "Importar paquete de sede"
                    flat: true
                    onClicked: openDialog.open()
                }
                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: "Abrir una base existente"
                    flat: true
                    onClicked: localDatabaseDialog.open()
                }
                Button {
                    Layout.alignment: Qt.AlignHCenter
                    visible: backend.hasWorkspace
                    text: "Volver a la sede abierta"
                    flat: true
                    onClicked: appWindow.creatingCampus = false
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16
            visible: backend.hasWorkspace && !appWindow.creatingCampus

            Rectangle {
                Layout.preferredWidth: 214
                Layout.fillHeight: true
                radius: 14
                color: appWindow.surfaceColor
                border.color: appWindow.borderColor
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10
                    Label {
                        Layout.leftMargin: 4
                        Layout.bottomMargin: 2
                        text: "GESTIÓN"
                        color: appWindow.secondaryTextColor
                        font.pixelSize: 11
                        font.bold: true
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 1
                        rowSpacing: 8
                        Button {
                            id: studentsNavigationButton
                            objectName: "studentsNavigationButton"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 84
                            text: "Estudiantes"
                            font.pixelSize: 11
                            padding: 4
                            spacing: 5
                            property bool selected: appWindow.currentPage === 0
                            contentItem: ColumnLayout {
                                spacing: studentsNavigationButton.spacing
                                MaterialSymbol {
                                    Layout.alignment: Qt.AlignHCenter
                                    symbolName: "groups"
                                    symbolSize: 38
                                    symbolColor: studentsNavigationButton.selected
                                                 ? appTheme.headerText
                                                 : appWindow.primaryTextColor
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: studentsNavigationButton.text
                                    font: studentsNavigationButton.font
                                    color: studentsNavigationButton.Material.foreground
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                            background: Rectangle {
                                radius: 4
                                color: studentsNavigationButton.selected
                                       ? appTheme.primary : appWindow.nestedSurfaceColor
                                border.color: studentsNavigationButton.selected
                                             ? appTheme.primary : appWindow.borderColor
                            }
                            Material.foreground: studentsNavigationButton.selected
                                                  ? appTheme.headerText : appTheme.primaryTextColor
                            onClicked: appWindow.currentPage = 0
                        }
                        Button {
                            id: enrollmentsNavigationButton
                            objectName: "enrollmentsNavigationButton"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 84
                            text: "Matrículas"
                            font.pixelSize: 11
                            padding: 4
                            spacing: 5
                            property bool selected: appWindow.currentPage === 1
                            contentItem: ColumnLayout {
                                spacing: enrollmentsNavigationButton.spacing
                                MaterialSymbol {
                                    Layout.alignment: Qt.AlignHCenter
                                    symbolName: "assignment"
                                    symbolSize: 38
                                    symbolColor: enrollmentsNavigationButton.selected
                                                 ? appTheme.headerText
                                                 : appWindow.primaryTextColor
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: enrollmentsNavigationButton.text
                                    font: enrollmentsNavigationButton.font
                                    color: enrollmentsNavigationButton.Material.foreground
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                            background: Rectangle {
                                radius: 4
                                color: enrollmentsNavigationButton.selected
                                       ? appTheme.primary : appWindow.nestedSurfaceColor
                                border.color: enrollmentsNavigationButton.selected
                                             ? appTheme.primary : appWindow.borderColor
                            }
                            Material.foreground: enrollmentsNavigationButton.selected
                                                  ? appTheme.headerText : appTheme.primaryTextColor
                            onClicked: appWindow.currentPage = 1
                        }
                        Button {
                            id: coursesNavigationButton
                            objectName: "coursesNavigationButton"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 84
                            text: "Cursos"
                            font.pixelSize: 11
                            padding: 4
                            spacing: 5
                            property bool selected: appWindow.currentPage === 2
                            contentItem: ColumnLayout {
                                spacing: coursesNavigationButton.spacing
                                MaterialSymbol {
                                    Layout.alignment: Qt.AlignHCenter
                                    symbolName: "menu_book"
                                    symbolSize: 38
                                    symbolColor: coursesNavigationButton.selected
                                                 ? appTheme.headerText
                                                 : appWindow.primaryTextColor
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: coursesNavigationButton.text
                                    font: coursesNavigationButton.font
                                    color: coursesNavigationButton.Material.foreground
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                            background: Rectangle {
                                radius: 4
                                color: coursesNavigationButton.selected
                                       ? appTheme.primary : appWindow.nestedSurfaceColor
                                border.color: coursesNavigationButton.selected
                                             ? appTheme.primary : appWindow.borderColor
                            }
                            Material.foreground: coursesNavigationButton.selected
                                                  ? appTheme.headerText : appTheme.primaryTextColor
                            onClicked: appWindow.currentPage = 2
                        }
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
                        objectName: "studentScroll"
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
                            Label {
                                Layout.fillWidth: true
                                horizontalAlignment: Text.AlignRight
                                text: backend.students.length + " registros"
                                color: appWindow.secondaryTextColor
                            }
                            ListView {
                                objectName: "studentList"
                                Layout.fillWidth: true
                                Layout.preferredHeight: backend.selectedStudent.id
                                                             ? 170
                                                             : Math.max(170, studentScroll.availableHeight - 50)
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
                                objectName: "studentEditor"
                                visible: Boolean(backend.selectedStudent.id)
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: 10
                                Label { text: "Apellidos" }
                                UppercaseTextField {
                                    id: lastName
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                             && Boolean(backend.selectedStudent.id)
                                    placeholderText: "Apellidos"
                                }
                                Label { text: "Nombres" }
                                UppercaseTextField {
                                    id: firstName
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                             && Boolean(backend.selectedStudent.id)
                                    placeholderText: "Nombres"
                                }
                                Label { text: "DNI" }
                                UppercaseTextField {
                                    id: documentNumber
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                             && Boolean(backend.selectedStudent.id)
                                    placeholderText: "Opcional"
                                }
                                Label { text: "Celulares" }
                                UppercaseTextField {
                                    id: phones
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                             && Boolean(backend.selectedStudent.id)
                                    placeholderText: "9 dígitos, separados por coma"
                                }
                            }
                        }
                    }
                    Button {
                        objectName: "studentSaveButton"
                        visible: Boolean(backend.selectedStudent.id)
                        text: "Guardar cambios"
                        enabled: backend.hasWorkspace
                        onClicked: backend.saveStudent(
                            backend.selectedStudent.id,
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
                                IconTextButton {
                                    text: "Nueva matrícula guiada"
                                    symbolName: "assignment"
                                    symbolColor: appWindow.primaryTextColor
                                    enabled: backend.hasWorkspace
                                    onClicked: appWindow.openEnrollmentWizard()
                                }
                                IconTextButton {
                                    text: "Nuevo curso"
                                    symbolName: "add"
                                    symbolColor: appWindow.primaryTextColor
                                    enabled: backend.hasWorkspace
                                    onClicked: appWindow.openCourseDialog()
                                }
                                IconTextButton {
                                    visible: backend.hasWorkspace
                                             && Boolean(backend.selectedEnrollment.id)
                                    text: appWindow.showEnrollmentEditor
                                          ? "Ocultar edición" : "Editar seleccionada"
                                    symbolName: "assignment"
                                    symbolColor: appWindow.primaryTextColor
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
                                DatePickerField {
                                    id: enrollmentDate
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    placeholderText: "AAAA-MM-DD"
                                }
                                Label { text: "Costo matrícula" }
                                UppercaseTextField {
                                    id: enrollmentFee
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                                }
                                Label { text: "Mensualidad" }
                                UppercaseTextField {
                                    id: monthlyFee
                                    Layout.fillWidth: true
                                    enabled: backend.hasWorkspace
                                    inputMethodHints: Qt.ImhFormattedNumbersOnly
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
                                            IconTextButton {
                                                text: "Nuevo curso"
                                                symbolName: "add"
                                                symbolColor: appTheme.headerText
                                                highlighted: true
                                                enabled: backend.hasWorkspace
                                                onClicked: appWindow.openCourseDialog()
                                            }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 220
                                            Layout.minimumHeight: 180
                                            Layout.maximumHeight: 260
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
                                                            onClicked: {
                                                                appWindow.editingCourse = false
                                                                backend.selectCourse(modelData.id)
                                                            }
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
                                                    RowLayout {
                                                        Layout.fillWidth: true
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
                                                        Button {
                                                            objectName: "editCourseButton"
                                                            visible: Boolean(backend.selectedCourse.id)
                                                                     && !appWindow.editingCourse
                                                            text: "Editar curso"
                                                            onClicked: appWindow.beginCourseEdit()
                                                        }
                                                    }
                                                    Label {
                                                        Layout.fillWidth: true
                                                        visible: Boolean(backend.selectedCourse.id)
                                                                 && !appWindow.editingCourse
                                                        text: backend.selectedCourse.id
                                                              ? backend.selectedCourse.schedule
                                                                + " · Grupo " + backend.selectedCourse.group
                                                                + " · Capacidad " + backend.selectedCourse.capacity
                                                              : ""
                                                        color: appWindow.secondaryTextColor
                                                        wrapMode: Text.Wrap
                                                    }
                                                    ScrollView {
                                                        id: courseEditorScroll
                                                        objectName: "courseEditorScroll"
                                                        visible: appWindow.editingCourse
                                                                 && Boolean(backend.selectedCourse.id)
                                                        Layout.fillWidth: true
                                                        Layout.fillHeight: true
                                                        Layout.preferredHeight: 220
                                                        Layout.minimumHeight: 100
                                                        clip: true
                                                        contentWidth: availableWidth

                                                        GridLayout {
                                                            id: courseEditor
                                                            objectName: "courseEditor"
                                                            width: courseEditorScroll.availableWidth
                                                            columns: 2
                                                            columnSpacing: 10
                                                            rowSpacing: 6
                                                            Label { text: "Nombre" }
                                                            UppercaseTextField {
                                                                id: courseNameEdit
                                                                objectName: "courseNameEdit"
                                                                Layout.fillWidth: true
                                                                placeholderText: "Nombre del curso"
                                                            }
                                                            Label { text: "Horario" }
                                                            UppercaseTextField {
                                                                id: courseScheduleEdit
                                                                objectName: "courseScheduleEdit"
                                                                Layout.fillWidth: true
                                                                placeholderText: "Horario"
                                                            }
                                                            Label { text: "Grupo" }
                                                            UppercaseTextField {
                                                                id: courseGroupEdit
                                                                objectName: "courseGroupEdit"
                                                                Layout.fillWidth: true
                                                                inputMethodHints: Qt.ImhDigitsOnly
                                                                placeholderText: "Grupo"
                                                            }
                                                            Label { text: "Capacidad" }
                                                            UppercaseTextField {
                                                                id: courseCapacityEdit
                                                                objectName: "courseCapacityEdit"
                                                                Layout.fillWidth: true
                                                                inputMethodHints: Qt.ImhDigitsOnly
                                                                placeholderText: "Capacidad"
                                                            }
                                                            Label { text: "Fecha de inicio" }
                                                            DatePickerField {
                                                                id: courseStartDateEdit
                                                                objectName: "courseStartDateEdit"
                                                                Layout.fillWidth: true
                                                                placeholderText: "AAAA-MM-DD"
                                                            }
                                                            Label { text: "Costo de matrícula" }
                                                            UppercaseTextField {
                                                                id: courseEnrollmentFeeEdit
                                                                objectName: "courseEnrollmentFeeEdit"
                                                                Layout.fillWidth: true
                                                                inputMethodHints: Qt.ImhFormattedNumbersOnly
                                                                placeholderText: "Costo de matrícula"
                                                            }
                                                            Label { text: "Mensualidad" }
                                                            UppercaseTextField {
                                                                id: courseMonthlyFeeEdit
                                                                objectName: "courseMonthlyFeeEdit"
                                                                Layout.fillWidth: true
                                                                inputMethodHints: Qt.ImhFormattedNumbersOnly
                                                                placeholderText: "Mensualidad"
                                                            }
                                                            CheckBox {
                                                                id: courseActiveEdit
                                                                objectName: "courseActiveEdit"
                                                                Layout.columnSpan: 2
                                                                text: "Curso activo"
                                                            }
                                                        }
                                                    }
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        visible: appWindow.editingCourse
                                                                 && Boolean(backend.selectedCourse.id)
                                                        Button {
                                                            objectName: "saveCourseButton"
                                                            text: "Guardar cambios"
                                                            enabled: backend.hasWorkspace
                                                            onClicked: appWindow.saveCourseEdit()
                                                        }
                                                        Button {
                                                            objectName: "cancelCourseButton"
                                                            text: "Cancelar"
                                                            onClicked: appWindow.cancelCourseEdit()
                                                        }
                                                    }
                                                    Rectangle {
                                                        Layout.fillWidth: true
                                                        height: 1
                                                        color: appWindow.dividerColor
                                                        visible: !appWindow.editingCourse
                                                    }
                                                    Label {
                                                        text: backend.courseStudents.length + " estudiantes"
                                                        color: appWindow.secondaryTextColor
                                                        font.bold: true
                                                        visible: !appWindow.editingCourse
                                                    }
                                                    ListView {
                                                        Layout.fillWidth: true
                                                        Layout.fillHeight: true
                                                        visible: !appWindow.editingCourse
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
                                                                 && !appWindow.editingCourse
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
