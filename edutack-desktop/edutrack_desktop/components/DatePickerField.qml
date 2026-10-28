import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "datePickerField"
    property alias text: dateInput.text
    property alias placeholderText: dateInput.placeholderText
    property int calendarYear: new Date().getFullYear()
    property int calendarMonth: new Date().getMonth()
    readonly property var calendarLocale: Qt.locale("es_PE")
    readonly property bool darkTheme: Material.theme === Material.Dark
    readonly property color calendarBackground: darkTheme ? "#1f2937" : "#ffffff"
    readonly property color calendarBorder: darkTheme ? "#3d4a5e" : "#e1e8f0"
    readonly property color calendarText: darkTheme ? "#f3f4f6" : "#173b5e"
    readonly property color calendarSecondaryText: darkTheme ? "#cbd5e1" : "#667085"
    readonly property color calendarAccent: darkTheme ? "#72d3c3" : "#00796b"
    readonly property color calendarSelectedText: darkTheme ? "#173b5e" : "#ffffff"
    spacing: 4

    function openCalendar() {
        var parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateInput.text)
        if (parts) {
            calendarYear = Number(parts[1])
            calendarMonth = Number(parts[2]) - 1
        } else {
            var today = new Date()
            calendarYear = today.getFullYear()
            calendarMonth = today.getMonth()
        }
        calendarPopup.open()
    }

    function shiftMonth(offset) {
        var nextMonth = calendarMonth + offset
        if (nextMonth < 0) {
            calendarMonth = 11
            calendarYear -= 1
        } else if (nextMonth > 11) {
            calendarMonth = 0
            calendarYear += 1
        } else {
            calendarMonth = nextMonth
        }
    }

    function selectDate(date) {
        dateInput.text = Qt.formatDate(date, "yyyy-MM-dd")
        calendarPopup.close()
    }

    TextField {
        id: dateInput
        objectName: "dateInput"
        Layout.fillWidth: true
        readOnly: true
        onPressed: root.openCalendar()
    }

    ToolButton {
        objectName: "openCalendarButton"
        Accessible.name: "Seleccionar fecha"
        contentItem: MaterialSymbol {
            symbolName: "calendar_month"
            symbolColor: Material.accent
            symbolSize: 20
        }
        onClicked: root.openCalendar()
    }

    Popup {
        id: calendarPopup
        objectName: "calendarPopup"
        x: Math.max(0, root.width - width)
        y: root.height + 4
        width: 320
        padding: 12
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        contentItem: ColumnLayout {
            spacing: 8

            RowLayout {
                Layout.fillWidth: true

                ToolButton {
                    Accessible.name: "Mes anterior"
                    contentItem: MaterialSymbol {
                        symbolName: "chevron_left"
                        symbolColor: root.calendarText
                    }
                    onClicked: root.shiftMonth(-1)
                }

                Label {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: monthGrid.title
                    color: root.calendarText
                }

                ToolButton {
                    Accessible.name: "Mes siguiente"
                    contentItem: MaterialSymbol {
                        symbolName: "chevron_right"
                        symbolColor: root.calendarText
                    }
                    onClicked: root.shiftMonth(1)
                }
            }

            DayOfWeekRow {
                Layout.fillWidth: true
                locale: root.calendarLocale

                delegate: Label {
                    required property string shortName
                    text: shortName
                    color: root.calendarSecondaryText
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            MonthGrid {
                id: monthGrid
                objectName: "calendarMonthGrid"
                Layout.fillWidth: true
                locale: root.calendarLocale
                month: root.calendarMonth
                year: root.calendarYear

                delegate: ItemDelegate {
                    objectName: "calendarDayDelegate"
                    id: dayDelegate
                    required property var model
                    implicitWidth: 40
                    implicitHeight: 38
                    enabled: model.month === monthGrid.month
                    highlighted: dateInput.text
                                  === Qt.formatDate(model.date, "yyyy-MM-dd")

                    background: Rectangle {
                        color: dayDelegate.highlighted ? root.calendarAccent : "transparent"
                        radius: 4
                    }

                    contentItem: Label {
                        text: String(dayDelegate.model.day)
                        color: dayDelegate.highlighted
                               ? root.calendarSelectedText
                               : dayDelegate.enabled
                                 ? root.calendarText : root.calendarSecondaryText
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: root.selectDate(model.date)
                }
            }
        }

        background: Rectangle {
            color: root.calendarBackground
            border.color: root.calendarBorder
            radius: 4
        }
    }
}
