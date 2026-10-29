import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "../components"

RowLayout {
    id: workspaceNavigation
    property var backendObject
    property var windowController
    property var theme
    property real statusBarHeight: 38
    property alias studentSearchText: studentsPage.studentSearchText
                anchors.fill: parent
                anchors.margins: 16
                anchors.bottomMargin: statusBarHeight + 32
                spacing: 16
                visible: backendObject.hasWorkspace && !windowController.creatingCampus

                Rectangle {
                    id: workspaceSidebar
                    Layout.preferredWidth: 152
                    Layout.fillHeight: true
                    radius: 0
                    color: windowController.surfaceColor
                    border.color: windowController.borderColor
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8

                        Repeater {
                            model: [
                                { label: "Matrículas", symbol: "assignment" },
                                { label: "Estudiantes", symbol: "groups" },
                                { label: "Cursos", symbol: "menu_book" },
                                { label: "Resumen", symbol: "event" }
                            ]

                            delegate: Button {
                                id: sectionButton
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(
                                    80,
                                    Math.min(112, (workspaceNavigation.height - 44) / 4)
                                )
                                property bool selected: windowController.selectedWorkspaceSection
                                                        === modelData.label
                                Material.foreground: windowController.primaryTextColor
                                contentItem: ColumnLayout {
                                    spacing: 6
                                    MaterialSymbol {
                                        Layout.alignment: Qt.AlignHCenter
                                        symbolName: sectionButton.modelData.symbol
                                        symbolSize: 36
                                        symbolColor: sectionButton.selected
                                                      ? windowController.accentTextColor
                                                      : windowController.secondaryTextColor
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: sectionButton.modelData.label
                                        horizontalAlignment: Text.AlignHCenter
                                        color: windowController.primaryTextColor
                                        font.family: "Roboto"
                                        font.pixelSize: 16
                                        font.bold: sectionButton.selected
                                        elide: Text.ElideRight
                                    }
                                }
                                background: Rectangle {
                                    radius: 12
                                    color: sectionButton.selected
                                           ? windowController.accentSurfaceColor
                                           : sectionButton.down
                                             ? windowController.accentSurfaceColor
                                             : sectionButton.hovered
                                               ? windowController.nestedSurfaceColor
                                               : windowController.surfaceColor
                                    border.color: sectionButton.selected
                                                  ? windowController.accentTextColor
                                                  : windowController.borderColor
                                }
                                onClicked: windowController.selectedWorkspaceSection =
                                               sectionButton.modelData.label
                            }
                        }

                        Item {
                            Layout.fillHeight: true
                        }
                    }
                }

                StudentsPage {
                    id: studentsPage
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    backendObject: workspaceNavigation.backendObject
                    windowController: workspaceNavigation.windowController
                    theme: workspaceNavigation.theme
                }

                EnrollmentsPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    backendObject: workspaceNavigation.backendObject
                    windowController: workspaceNavigation.windowController
                    theme: workspaceNavigation.theme
                }

                CoursesPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    backendObject: workspaceNavigation.backendObject
                    windowController: workspaceNavigation.windowController
                    theme: workspaceNavigation.theme
                }

                SummaryPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    backendObject: workspaceNavigation.backendObject
                    windowController: workspaceNavigation.windowController
                    theme: workspaceNavigation.theme
                }
            }
