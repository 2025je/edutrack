import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "coursesPanel"
    property var backendObject
    property var windowController
    property var theme
    property var selectedCourse: null
    property string currentView: "list"
    property string appliedCourseSearchText: ""
    readonly property var filteredCourses: {
        var query = root.appliedCourseSearchText.trim().toLocaleLowerCase()
        return root.backendObject.courses.filter(function(course) {
            if (!query)
                return true
            return [
                course.name,
                course.schedule,
                course.group,
                course.start_date
            ].join(" ").toLocaleLowerCase().indexOf(query) >= 0
        })
    }

    function focusSearch() {
        courseSearch.forceActiveFocus()
    }

    function parseStartDate(value) {
        var dateText = String(value || "")
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText))
            return null

        var parts = dateText.split("-")
        var parsed = new Date(Date.UTC(
            Number(parts[0]),
            Number(parts[1]) - 1,
            Number(parts[2])
        ))
        if (parsed.getUTCFullYear() !== Number(parts[0])
                || parsed.getUTCMonth() !== Number(parts[1]) - 1
                || parsed.getUTCDate() !== Number(parts[2]))
            return null
        return parsed
    }

    function dateKey(value) {
        var month = ("0" + (value.getUTCMonth() + 1)).slice(-2)
        var day = ("0" + value.getUTCDate()).slice(-2)
        return value.getUTCFullYear() + "-" + month + "-" + day
    }

    function weekRangeLabel(start, end) {
        var months = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]
        var startDay = start.getUTCDate()
        var endDay = end.getUTCDate()
        var startMonth = months[start.getUTCMonth()]
        var endMonth = months[end.getUTCMonth()]
        var startYear = start.getUTCFullYear()
        var endYear = end.getUTCFullYear()

        if (startYear === endYear && start.getUTCMonth() === end.getUTCMonth())
            return startDay + " al " + endDay + " de " + endMonth + " de " + endYear
        if (startYear === endYear)
            return startDay + " de " + startMonth + " al " + endDay + " de "
                    + endMonth + " de " + endYear
        return startDay + " de " + startMonth + " de " + startYear + " al "
                + endDay + " de " + endMonth + " de " + endYear
    }

    readonly property var weeklyGroups: {
        var groupsByDate = {}
        var groups = []
        var ungroupedCourses = []
        var courses = root.filteredCourses

        courses.forEach(function(course) {
            var courseDate = root.parseStartDate(course.start_date)
            if (courseDate === null) {
                ungroupedCourses.push(course)
                return
            }

            var daysSinceMonday = (courseDate.getUTCDay() + 6) % 7
            var weekStart = new Date(courseDate.getTime() - daysSinceMonday * 86400000)
            var weekEnd = new Date(weekStart.getTime() + 6 * 86400000)
            var startKey = root.dateKey(weekStart)
            var group = groupsByDate[startKey]
            if (!group) {
                group = {
                    label: root.weekRangeLabel(weekStart, weekEnd),
                    startDate: startKey,
                    courses: []
                }
                groupsByDate[startKey] = group
                groups.push(group)
            }
            group.courses.push(course)
        })

        var compareCourses = function(left, right) {
            var byStartDate = String(right.start_date || "")
                              .localeCompare(String(left.start_date || ""))
            if (byStartDate !== 0)
                return byStartDate
            var byName = String(left.name).localeCompare(String(right.name))
            if (byName !== 0)
                return byName
            var bySchedule = String(left.schedule).localeCompare(String(right.schedule))
            if (bySchedule !== 0)
                return bySchedule
            return String(left.group).localeCompare(String(right.group))
        }
        groups.sort(function(left, right) {
            return right.startDate.localeCompare(left.startDate)
        })
        groups.forEach(function(group, index) {
            group.label = "SEMANA " + (index + 1) + ": del " + group.label
            group.courses.sort(compareCourses)
        })

        var result = groups
        if (ungroupedCourses.length > 0) {
            ungroupedCourses.sort(compareCourses)
            result.push({
                label: "Semana no definida",
                courses: ungroupedCourses
            })
        }
        return result
    }

    radius: 0
    color: theme.surface
    border.color: theme.outline
    visible: windowController.selectedWorkspaceSection === "Cursos"

    Timer {
        id: courseSearchTimer
        interval: 120
        onTriggered: root.appliedCourseSearchText = courseSearch.text
    }

    ColumnLayout {
        id: coursesListView
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        visible: root.currentView === "list"

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Cursos"
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 24
                font.bold: true
            }

            Item {
                Layout.fillWidth: true
            }

            Label {
                text: root.filteredCourses.length === root.backendObject.courses.length
                      ? root.filteredCourses.length + " cursos"
                      : root.filteredCourses.length + " de "
                        + root.backendObject.courses.length + " cursos"
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 14
            }
        }

        TextField {
            id: courseSearch
            objectName: "courseSearchField"
            Layout.fillWidth: true
            placeholderText: "Buscar por curso, horario, grupo o fecha..."
            onTextChanged: courseSearchTimer.restart()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: root.theme.divider
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredCourses.length === 0
            text: root.backendObject.courses.length === 0
                  ? "No hay cursos registrados."
                  : "No se encontraron cursos con ese filtro."
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: root.theme.secondaryText
            font.family: "Roboto"
            font.pixelSize: 16
        }

        Flickable {
            id: coursesFlickable
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredCourses.length > 0
            clip: true
            contentWidth: width
            contentHeight: coursesContent.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            ColumnLayout {
                id: coursesContent
                width: coursesFlickable.width
                spacing: 20

                Repeater {
                    model: root.weeklyGroups

                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true

                            Label {
                                text: modelData.label
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 13
                                font.bold: true
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: root.theme.divider
                            }

                            Label {
                                text: modelData.courses.length + " cursos"
                                color: root.theme.secondaryText
                                font.family: "Roboto"
                                font.pixelSize: 12
                            }
                        }

                        Repeater {
                            model: modelData.courses

                            delegate: Rectangle {
                                id: courseCard
                                required property var modelData
                                readonly property bool full: modelData.capacity > 0
                                                               && modelData.student_count
                                                                  >= modelData.capacity
                                Layout.fillWidth: true
                                Layout.preferredHeight: 76
                                radius: 10
                                color: full ? root.theme.successSurface
                                            : root.theme.raisedSurface
                                border.color: full ? root.theme.success
                                                   : root.theme.outline

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 16
                                    anchors.rightMargin: 16
                                    spacing: 16

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        spacing: 4

                                        Label {
                                            Layout.fillWidth: true
                                            text: modelData.name
                                            color: root.theme.primaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 15
                                            font.bold: true
                                            elide: Text.ElideRight
                                        }

                                        Label {
                                            Layout.fillWidth: true
                                            text: modelData.schedule
                                            color: root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 13
                                            elide: Text.ElideRight
                                        }
                                    }

                                    Label {
                                        Layout.preferredWidth: 100
                                        Layout.minimumWidth: 100
                                        Layout.maximumWidth: 100
                                        text: "Grupo " + modelData.group
                                        color: root.theme.secondaryText
                                        font.family: "Roboto"
                                        font.pixelSize: 13
                                    }

                                    ColumnLayout {
                                        Layout.preferredWidth: 210
                                        Layout.minimumWidth: 210
                                        Layout.maximumWidth: 210
                                        spacing: 4

                                        Label {
                                            Layout.fillWidth: true
                                            text: "Inicio: " + modelData.start_date
                                            color: root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                            elide: Text.ElideRight
                                        }

                                        Label {
                                            Layout.fillWidth: true
                                            text: modelData.student_count
                                                  + " / "
                                                  + modelData.capacity
                                                  + " estudiantes"
                                            color: courseCard.full
                                                   ? root.theme.success
                                                   : root.theme.secondaryText
                                            font.family: "Roboto"
                                            font.pixelSize: 12
                                            font.bold: courseCard.full
                                            elide: Text.ElideRight
                                        }
                                    }

                                    Label {
                                        Layout.preferredWidth: 80
                                        Layout.minimumWidth: 80
                                        Layout.maximumWidth: 80
                                        text: modelData.active ? "Activo" : "Inactivo"
                                        color: modelData.active
                                               ? root.theme.success
                                               : root.theme.secondaryText
                                        font.family: "Roboto"
                                        font.pixelSize: 12
                                        horizontalAlignment: Text.AlignRight
                                    }

                                    Button {
                                        Layout.preferredWidth: 80
                                        Layout.minimumWidth: 80
                                        Layout.maximumWidth: 80
                                        text: "Ver"
                                        onClicked: {
                                            root.backendObject.selectCourse(
                                                courseCard.modelData.id
                                            )
                                            root.selectedCourse = courseCard.modelData
                                            root.currentView = "details"
                                        }
                                    }

                                    Button {
                                        Layout.preferredWidth: 96
                                        Layout.minimumWidth: 96
                                        Layout.maximumWidth: 96
                                        text: "Editar"
                                        onClicked: {
                                            root.backendObject.selectCourse(
                                                courseCard.modelData.id
                                            )
                                            root.selectedCourse = courseCard.modelData
                                            root.currentView = "edit"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

        }
    }

    CourseDetailsPage {
        anchors.fill: parent
        visible: root.currentView === "details"
        course: root.selectedCourse
        students: root.backendObject.courseStudents
        theme: root.theme
        onBackRequested: {
            root.selectedCourse = null
            root.currentView = "list"
        }
    }

    CourseEditorPage {
        anchors.fill: parent
        visible: root.currentView === "edit"
        backendObject: root.backendObject
        course: root.selectedCourse
        theme: root.theme
        onCancelRequested: {
            root.selectedCourse = null
            root.currentView = "list"
        }
        onSaveSucceeded: {
            root.selectedCourse = null
            root.currentView = "list"
        }
    }
}
