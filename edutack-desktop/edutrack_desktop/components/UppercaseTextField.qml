import QtQuick
import QtQuick.Controls

TextField {
    onTextChanged: {
        var uppercaseText = text.toUpperCase()
        if (uppercaseText === text)
            return

        var caretPosition = text.slice(0, cursorPosition).toUpperCase().length
        text = uppercaseText
        cursorPosition = caretPosition
    }
}
