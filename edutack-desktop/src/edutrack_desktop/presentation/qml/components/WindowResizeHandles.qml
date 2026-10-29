import QtQuick

Item {
    id: windowResizeHandles
    property var windowController
    anchors.fill: parent
    z: 2000
    enabled: windowController.visibility === Window.Windowed

    MouseArea {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.topMargin: 8
        width: 6
        height: parent.height - 16
        cursorShape: Qt.SizeHorCursor
        onPressed: windowController.startSystemResize(Qt.LeftEdge)
    }

    MouseArea {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 8
        width: 6
        height: parent.height - 16
        cursorShape: Qt.SizeHorCursor
        onPressed: windowController.startSystemResize(Qt.RightEdge)
    }

    MouseArea {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.right: parent.right
        anchors.rightMargin: 8
        height: 6
        cursorShape: Qt.SizeVerCursor
        onPressed: windowController.startSystemResize(Qt.TopEdge)
    }

    MouseArea {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.right: parent.right
        anchors.rightMargin: 8
        height: 6
        cursorShape: Qt.SizeVerCursor
        onPressed: windowController.startSystemResize(Qt.BottomEdge)
    }

    MouseArea {
        anchors.left: parent.left
        anchors.top: parent.top
        width: 8
        height: 8
        cursorShape: Qt.SizeFDiagCursor
        onPressed: windowController.startSystemResize(Qt.TopEdge | Qt.LeftEdge)
    }

    MouseArea {
        anchors.right: parent.right
        anchors.top: parent.top
        width: 8
        height: 8
        cursorShape: Qt.SizeBDiagCursor
        onPressed: windowController.startSystemResize(Qt.TopEdge | Qt.RightEdge)
    }

    MouseArea {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        width: 8
        height: 8
        cursorShape: Qt.SizeBDiagCursor
        onPressed: windowController.startSystemResize(Qt.BottomEdge | Qt.LeftEdge)
    }

    MouseArea {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: 8
        height: 8
        cursorShape: Qt.SizeFDiagCursor
        onPressed: windowController.startSystemResize(Qt.BottomEdge | Qt.RightEdge)
    }
}
