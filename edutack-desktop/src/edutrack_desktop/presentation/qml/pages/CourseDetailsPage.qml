import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "courseDetailsPage"
    property var course
    property var students: []
    property var theme
    signal backRequested()

    radius: 0
    color: theme.surface
    border.color: theme.outline

    Shortcut {
        sequence: "Esc"
        enabled: root.visible
        onActivated: root.backRequested()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Button {
                text: "Volver a cursos"
                onClicked: root.backRequested()
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Label {
                    Layout.fillWidth: true
                    text: root.course ? root.course.name : ""
                    color: root.theme.primaryText
                    font.family: "Roboto"
                    font.pixelSize: 22
                    font.bold: true
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.course
                          ? root.course.schedule + " · Grupo " + root.course.group
                          : ""
                    color: root.theme.secondaryText
                    font.family: "Roboto"
                    font.pixelSize: 14
                    elide: Text.ElideRight
                }
            }

            Label {
                Layout.preferredWidth: 160
                text: root.course
                      ? root.students.length + " / " + root.course.capacity + " alumnos"
                      : root.students.length + " alumnos"
                color: root.course
                       && root.students.length >= root.course.capacity
                       ? root.theme.success
                       : root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 14
                font.bold: root.course
                           && root.students.length >= root.course.capacity
                horizontalAlignment: Text.AlignRight
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: root.theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Label {
                Layout.fillWidth: true
                text: "ALUMNO"
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
            }

            Label {
                Layout.preferredWidth: 180
                text: "DOCUMENTO"
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
            }

            Label {
                Layout.preferredWidth: 230
                text: "TELÉFONO"
                color: root.theme.secondaryText
                font.family: "Roboto"
                font.pixelSize: 12
                font.bold: true
            }
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.students.length === 0
            text: "Este curso no tiene alumnos matriculados."
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: root.theme.secondaryText
            font.family: "Roboto"
            font.pixelSize: 16
        }

        ListView {
            id: studentsList
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.students.length > 0
            clip: true
            spacing: 8
            model: root.students
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: Rectangle {
                required property var modelData
                width: studentsList.width
                height: 64
                radius: 8
                color: root.theme.raisedSurface
                border.color: root.theme.outline

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 16

                    Label {
                        Layout.fillWidth: true
                        text: modelData.label
                        color: root.theme.primaryText
                        font.family: "Roboto"
                        font.pixelSize: 14
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.preferredWidth: 180
                        text: modelData.document_number || "Sin documento"
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.preferredWidth: 230
                        text: modelData.phone_numbers && modelData.phone_numbers.length
                              ? modelData.phone_numbers.join(", ")
                              : "Sin teléfono"
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
}
