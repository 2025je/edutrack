import QtQuick

Text {
    property string symbolName: ""
    property color symbolColor: "white"
    property real symbolSize: 24

    text: symbolName
    font.family: "Material Symbols Outlined"
    font.pixelSize: symbolSize
    font.weight: Font.Normal
    color: symbolColor
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
}
