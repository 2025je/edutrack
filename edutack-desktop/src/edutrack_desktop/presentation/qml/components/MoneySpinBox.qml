import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var theme
    property alias text: amountInput.text
    property alias acceptableInput: amountInput.acceptableInput
    readonly property double minimumCents: 1
    readonly property double maximumCents: 9999999999
    signal editingFinished()

    implicitWidth: 220
    implicitHeight: 40

    function centsFromText(value) {
        var match = /^([0-9]+)(?:[.,]([0-9]{0,2}))?$/.exec(
            String(value).trim()
        )
        if (!match)
            return -1

        var decimalPart = match[2] || ""
        while (decimalPart.length < 2)
            decimalPart += "0"
        var cents = Number(match[1]) * 100 + Number(decimalPart)
        return isFinite(cents) && cents <= root.maximumCents ? cents : -1
    }

    function textFromCents(cents) {
        var whole = Math.floor(cents / 100)
        var fraction = String(100 + cents % 100).slice(-2)
        return whole + "." + fraction
    }

    function normalizeText() {
        var cents = root.centsFromText(amountInput.text)
        if (cents < root.minimumCents || cents > root.maximumCents)
            return false
        amountInput.text = root.textFromCents(cents)
        return true
    }

    function stepBy(direction) {
        var cents = root.centsFromText(amountInput.text)
        if (cents < 0)
            cents = direction > 0 ? 0 : root.minimumCents
        cents = Math.max(
            root.minimumCents,
            Math.min(root.maximumCents, cents + direction)
        )
        amountInput.text = root.textFromCents(cents)
        amountInput.forceActiveFocus()
    }

    Rectangle {
        anchors.fill: parent
        radius: 5
        color: root.theme ? root.theme.surface : "transparent"
        border.color: amountInput.activeFocus && root.theme
                      ? root.theme.accent
                      : root.theme ? root.theme.outline : "transparent"
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 1
        spacing: 0

        TextField {
            id: amountInput
            objectName: root.objectName + "Input"
            Layout.fillWidth: true
            Layout.fillHeight: true
            maximumLength: 11
            inputMethodHints: Qt.ImhFormattedNumbersOnly
            font.family: "Roboto"
            font.pixelSize: 14
            leftPadding: 12
            rightPadding: 8
            validator: RegularExpressionValidator {
                regularExpression: /^[0-9]+([.,][0-9]{0,2})?$/
            }
            background: Item {}

            onEditingFinished: {
                root.normalizeText()
                root.editingFinished()
            }

            Keys.onUpPressed: function(event) {
                root.stepBy(1)
                event.accepted = true
            }
            Keys.onDownPressed: function(event) {
                root.stepBy(-1)
                event.accepted = true
            }
        }

        ColumnLayout {
            Layout.fillHeight: true
            Layout.preferredWidth: 30
            spacing: 0

            ToolButton {
                objectName: root.objectName + "IncrementButton"
                Layout.fillWidth: true
                Layout.fillHeight: true
                focusPolicy: Qt.NoFocus
                text: "▲"
                font.pixelSize: 10
                padding: 0
                background: Rectangle {
                    color: parent.down ? root.theme.accentSurface
                                       : parent.hovered
                                         ? root.theme.raisedSurface
                                         : "transparent"
                }
                onClicked: root.stepBy(1)
            }

            ToolButton {
                objectName: root.objectName + "DecrementButton"
                Layout.fillWidth: true
                Layout.fillHeight: true
                focusPolicy: Qt.NoFocus
                text: "▼"
                font.pixelSize: 10
                padding: 0
                background: Rectangle {
                    color: parent.down ? root.theme.accentSurface
                                       : parent.hovered
                                         ? root.theme.raisedSurface
                                         : "transparent"
                }
                onClicked: root.stepBy(-1)
            }
        }
    }
}
