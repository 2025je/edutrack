import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: control
    property string symbolName: ""
    property color symbolColor: palette.buttonText
    property real symbolSize: 20

    contentItem: RowLayout {
        spacing: control.spacing

        MaterialSymbol {
            symbolName: control.symbolName
            symbolColor: control.symbolColor
            symbolSize: control.symbolSize
            visible: control.symbolName.length > 0
        }

        Label {
            Layout.fillWidth: true
            text: control.text
            font: control.font
            color: control.Material.foreground
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }
}
