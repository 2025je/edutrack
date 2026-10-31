import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property string value: ""
    property var theme
    readonly property bool valid: root.dateFromIso(root.value) !== null
    readonly property bool popupOpen: calendarPopup.opened
    readonly property string displayText: root.formatDisplayDate(root.value)
    readonly property var monthNames: [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    signal dateSelected(string value)

    implicitWidth: 220
    implicitHeight: 40

    function dateFromIso(text) {
        var dateText = String(text || "")
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText))
            return null
        var parts = dateText.split("-")
        var parsed = new Date(
            Number(parts[0]),
            Number(parts[1]) - 1,
            Number(parts[2])
        )
        if (parsed.getFullYear() !== Number(parts[0])
                || parsed.getMonth() !== Number(parts[1]) - 1
                || parsed.getDate() !== Number(parts[2]))
            return null
        return parsed
    }

    function isoDate(date) {
        var month = ("0" + (date.getMonth() + 1)).slice(-2)
        var day = ("0" + date.getDate()).slice(-2)
        return date.getFullYear() + "-" + month + "-" + day
    }

    function formatDisplayDate(text) {
        var date = root.dateFromIso(text)
        if (!date)
            return ""
        var day = ("0" + date.getDate()).slice(-2)
        var month = ("0" + (date.getMonth() + 1)).slice(-2)
        return day + "/" + month + "/" + date.getFullYear()
    }

    function openCalendar() {
        var date = root.dateFromIso(root.value) || new Date()
        calendarPopup.displayedYear = date.getFullYear()
        calendarPopup.displayedMonth = date.getMonth()
        calendarPopup.open()
    }

    function changeMonth(offset) {
        var date = new Date(
            calendarPopup.displayedYear,
            calendarPopup.displayedMonth + offset,
            1
        )
        calendarPopup.displayedYear = date.getFullYear()
        calendarPopup.displayedMonth = date.getMonth()
    }

    function selectDate(date) {
        root.value = root.isoDate(date)
        root.dateSelected(root.value)
        calendarPopup.close()
    }

    Rectangle {
        anchors.fill: parent
        radius: 5
        color: root.theme ? root.theme.surface : "transparent"
        border.color: dateButton.activeFocus && root.theme
                      ? root.theme.accent
                      : root.theme ? root.theme.outline : "transparent"
    }

    Button {
        id: dateButton
        objectName: root.objectName + "OpenButton"
        anchors.fill: parent
        flat: true
        onClicked: root.openCalendar()

        contentItem: RowLayout {
            spacing: 8

            Label {
                Layout.fillWidth: true
                text: root.displayText || "DD/MM/AAAA"
                color: root.displayText
                       ? root.theme.primaryText
                       : root.theme.secondaryText
                font.family: "Roboto"
                horizontalAlignment: Text.AlignLeft
                verticalAlignment: Text.AlignVCenter
            }

            MaterialSymbol {
                symbolName: "event"
                symbolColor: root.theme.secondaryText
                symbolSize: 20
            }
        }

        background: Rectangle {
            radius: 4
            color: dateButton.down ? root.theme.accentSurface
                  : dateButton.hovered ? root.theme.raisedSurface
                  : "transparent"
        }
    }

    Popup {
        id: calendarPopup
        objectName: root.objectName + "Popup"
        modal: true
        focus: true
        width: 360
        height: 410
        padding: 12
        anchors.centerIn: Overlay.overlay
        property int displayedYear: new Date().getFullYear()
        property int displayedMonth: new Date().getMonth()
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 8
            color: root.theme.surface
            border.color: root.theme.outline
        }

        contentItem: ColumnLayout {
            spacing: 8

            RowLayout {
                Layout.fillWidth: true

                ToolButton {
                    objectName: root.objectName + "PreviousMonthButton"
                    text: "‹"
                    font.pixelSize: 24
                    onClicked: root.changeMonth(-1)
                }

                Label {
                    Layout.fillWidth: true
                    text: root.monthNames[calendarPopup.displayedMonth]
                          + " " + calendarPopup.displayedYear
                    horizontalAlignment: Text.AlignHCenter
                    color: root.theme.primaryText
                    font.family: "Roboto"
                    font.bold: true
                }

                ToolButton {
                    objectName: root.objectName + "NextMonthButton"
                    text: "›"
                    font.pixelSize: 24
                    onClicked: root.changeMonth(1)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 0

                Repeater {
                    model: ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

                    delegate: Label {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        horizontalAlignment: Text.AlignHCenter
                        color: root.theme.secondaryText
                        font.family: "Roboto"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }

            MonthGrid {
                id: dateCalendar
                Layout.fillWidth: true
                Layout.preferredHeight: 260
                month: calendarPopup.displayedMonth
                year: calendarPopup.displayedYear
                locale: Qt.locale("es_PE")

                delegate: Button {
                    required property var model
                    objectName: root.objectName + "Day_" + root.isoDate(model.date)
                    implicitWidth: 40
                    implicitHeight: 36
                    text: String(model.day)
                    enabled: model.month === dateCalendar.month
                    flat: true
                    highlighted: root.isoDate(model.date) === root.value
                    onClicked: root.selectDate(model.date)
                }
            }
        }
    }
}
