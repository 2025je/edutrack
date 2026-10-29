import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "summaryPage"
    property var backendObject
    property var windowController
    property var theme
    readonly property var students: backendObject ? backendObject.students : []
    readonly property var courses: backendObject ? backendObject.courses : []
    readonly property var enrollments: backendObject ? backendObject.enrollments : []
    readonly property int activeStudents: students.filter(function(student) {
        return student.active
    }).length
    readonly property int activeCourses: courses.filter(function(course) {
        return course.active
    }).length
    readonly property int activeEnrollments: enrollments.filter(function(enrollment) {
        return enrollment.active
               && !enrollment.pending_student
               && !enrollment.pending_course
    }).length
    readonly property int pendingEnrollments: enrollments.filter(function(enrollment) {
        return enrollment.pending_student || enrollment.pending_course
    }).length
    readonly property int fullCourses: courses.filter(function(course) {
        return course.capacity > 0 && course.student_count >= course.capacity
    }).length
    readonly property var summaryCards: [
        {
            title: "Estudiantes",
            value: students.length,
            detail: activeStudents + " activos · "
                    + (students.length - activeStudents) + " inactivos"
        },
        {
            title: "Cursos",
            value: courses.length,
            detail: activeCourses + " activos · " + fullCourses + " completos"
        },
        {
            title: "Matrículas",
            value: enrollments.length,
            detail: activeEnrollments + " activas · "
                    + pendingEnrollments + " pendientes"
        }
    ]
    readonly property var courseOccupancyRows: {
        var rows = courses.slice()
        rows.sort(function(left, right) {
            return right.student_count - left.student_count
        })
        return rows.slice(0, 6)
    }
    readonly property var recentEnrollments: {
        var rows = enrollments.slice()
        rows.sort(function(left, right) {
            return String(right.enrollment_date).localeCompare(
                String(left.enrollment_date)
            )
        })
        return rows.slice(0, 6)
    }

    radius: 0
    color: theme.surface
    border.color: theme.outline
    visible: windowController.selectedWorkspaceSection === "Resumen"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Label {
                    text: "Resumen general"
                    color: root.theme.primaryText
                    font.family: "Roboto"
                    font.pixelSize: 24
                    font.bold: true
                }

                Label {
                    text: root.backendObject.campusName
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                    font.pixelSize: 13
                }
            }

            Label {
                text: "Datos de esta sede"
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 13
            }

            Button {
                text: "Exportar Registro"
                highlighted: true
                font.family: "Roboto"
                onClicked: registerExportDialog.open()
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 12
            rowSpacing: 12

            Repeater {
                model: root.summaryCards

                delegate: Rectangle {
                    id: summaryCard
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 104
                    radius: 10
                    color: root.theme.raisedSurface
                    border.color: root.theme.outline

                    Rectangle {
                        width: 4
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        radius: 2
                        color: root.theme.accent
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 18
                        anchors.rightMargin: 14
                        anchors.topMargin: 12
                        anchors.bottomMargin: 12
                        spacing: 2

                        Label {
                            text: summaryCard.modelData.title
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 13
                        }

                        Label {
                            text: String(summaryCard.modelData.value)
                            color: root.theme.primaryText
                            font.family: "Roboto"
                            font.pixelSize: 24
                            font.bold: true
                        }

                        Label {
                            Layout.fillWidth: true
                            text: summaryCard.modelData.detail
                            color: root.theme.secondaryText
                            font.family: "Roboto"
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                    }
                }

            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 0
                radius: 10
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    Label {
                        text: "Ocupación de cursos"
                        color: root.theme.primaryText
                        font.family: "Roboto"
                        font.pixelSize: 16
                        font.bold: true
                    }

                    Label {
                        text: root.fullCourses + " cursos completos"
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 12
                    }

                    ListView {
                        id: courseList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: root.courseOccupancyRows.length > 0
                        clip: true
                        spacing: 10
                        model: root.courseOccupancyRows

                        delegate: ColumnLayout {
                            id: courseRow
                            required property var modelData
                            width: courseList.width
                            spacing: 4

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: courseRow.modelData.label
                                    color: root.theme.primaryText
                                    font.family: "Roboto"
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                                Label {
                                    text: courseRow.modelData.student_count + " / "
                                          + courseRow.modelData.capacity
                                    color: root.theme.secondaryText
                                    font.family: "Roboto"
                                    font.pixelSize: 12
                                }
                            }

                            Rectangle {
                                id: occupancyTrack
                                Layout.fillWidth: true
                                height: 6
                                radius: 3
                                color: root.theme.divider

                                Rectangle {
                                    width: occupancyTrack.width
                                           * (courseRow.modelData.capacity > 0
                                              ? Math.min(
                                                    1,
                                                    courseRow.modelData.student_count
                                                    / courseRow.modelData.capacity
                                                )
                                              : 0)
                                    height: parent.height
                                    radius: parent.radius
                                    color: courseRow.modelData.capacity > 0
                                           && courseRow.modelData.student_count
                                              >= courseRow.modelData.capacity
                                           ? root.theme.error
                                           : root.theme.accent
                                }
                            }
                        }

                    }

                    Label {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: root.courseOccupancyRows.length === 0
                        text: "No hay cursos registrados."
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                FileDialog {
                    id: registerExportDialog
                    title: "Exportar registro de cursos"
                    fileMode: FileDialog.SaveFile
                    acceptLabel: "Exportar"
                    rejectLabel: "Cancelar"
                    defaultSuffix: "xlsx"
                    nameFilters: ["Libro de Excel (*.xlsx)"]
                    onAccepted: root.backendObject.exportRegister(selectedFile.toString())
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 0
                radius: 10
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    Label {
                        text: "Matrículas recientes"
                        color: root.theme.primaryText
                        font.family: "Roboto"
                        font.pixelSize: 16
                        font.bold: true
                    }

                    ListView {
                        id: recentList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: root.recentEnrollments.length > 0
                        clip: true
                        spacing: 4
                        model: root.recentEnrollments

                        delegate: Rectangle {
                            id: recentRow
                            required property var modelData
                            width: recentList.width
                            height: 50
                            color: "transparent"

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 2

                                Label {
                                    Layout.fillWidth: true
                                    text: recentRow.modelData.student_label
                                    color: root.theme.primaryText
                                    font.family: "Roboto"
                                    font.pixelSize: 12
                                    font.bold: true
                                    elide: Text.ElideRight
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        Layout.fillWidth: true
                                        text: recentRow.modelData.course_label
                                        color: root.theme.secondaryText
                                        font.family: "Roboto"
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: recentRow.modelData.enrollment_date
                                        color: root.theme.secondaryText
                                        font.family: "Roboto"
                                        font.pixelSize: 11
                                    }
                                }
                            }
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: root.recentEnrollments.length === 0
                        text: "No hay matrículas registradas."
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }
}
