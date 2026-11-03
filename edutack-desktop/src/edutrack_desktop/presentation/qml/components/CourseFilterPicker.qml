import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "courseFilterPicker"
    implicitWidth: 240
    implicitHeight: 40
    property var backendObject
    property var theme
    property int selectedCourseId: 0
    property string selectedCourseLabel: "Todos los cursos"
    property var searchResults: []
    property int searchRequestId: 0
    property bool searchPending: false
    property string searchQuery: ""
    property string errorText: ""
    readonly property bool popupVisible: coursePicker.visible
    signal courseSelected(int courseId)

    readonly property var filteredOptions: {
        var options = [{ id: 0, label: "Todos los cursos" }]
        for (var index = 0; index < root.searchResults.length; index++)
            options.push(root.searchResults[index])
        if (root.selectedCourseId > 0
                && !options.some(function(option) {
                    return Number(option.id) === root.selectedCourseId
                })) {
            options.push({
                id: root.selectedCourseId,
                label: root.selectedCourseLabel
            })
        }
        var query = root.searchQuery.trim().toLowerCase()
        return options.filter(function(option) {
            return Number(option.id) === 0
                    || String(option.label || "").toLowerCase().indexOf(query) >= 0
        })
    }

    function resetSelection() {
        root.selectedCourseId = 0
        root.selectedCourseLabel = "Todos los cursos"
    }

    function chooseCourse(option) {
        root.selectedCourseId = Number(option.id) || 0
        root.selectedCourseLabel = option.label
        root.courseSelected(root.selectedCourseId)
        coursePicker.close()
    }

    function refreshSearch() {
        if (!root.backendObject) {
            root.searchPending = false
            root.errorText = "No se pudieron cargar los cursos desde la base local."
            return
        }
        root.searchPending = true
        root.searchRequestId = root.backendObject.searchCourseOptionsAsync(
            root.searchQuery,
            true,
            50
        )
    }

    Timer {
        id: searchTimer
        interval: 180
        repeat: false
        onTriggered: root.refreshSearch()
    }

    Connections {
        target: root.backendObject
        function onCourseSearchFinished(requestId, courses, error) {
            if (requestId !== root.searchRequestId)
                return
            root.searchPending = false
            if (error.length > 0) {
                root.searchResults = []
                root.errorText = error
            } else {
                root.searchResults = courses
                root.errorText = ""
            }
        }
    }

    Button {
        objectName: root.objectName + "Button"
        anchors.fill: parent
        text: root.selectedCourseLabel
        padding: 10
        contentItem: RowLayout {
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: root.selectedCourseLabel
                color: root.theme.primaryText
                font.family: "Roboto"
                elide: Text.ElideRight
            }
            Label {
                text: "▼"
                color: root.theme.secondaryText
                font.family: "Roboto"
            }
        }
        background: Rectangle {
            radius: 6
            color: root.theme.surface
            border.color: root.theme.outline
        }
        onClicked: coursePicker.open()
    }

    Popup {
        id: coursePicker
        objectName: root.objectName + "Popup"
        modal: true
        focus: true
        width: Math.min(Overlay.overlay.width - 48, Math.max(root.width, 420))
        height: Math.min(Overlay.overlay.height - 48, 480)
        padding: 16
        anchors.centerIn: Overlay.overlay
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        onOpened: {
            root.searchQuery = ""
            searchField.text = ""
            searchTimer.stop()
            root.searchResults = []
            root.errorText = ""
            root.refreshSearch()
            searchField.forceActiveFocus()
        }

        contentItem: ColumnLayout {
            spacing: 10
            Label {
                text: "Filtrar por curso"
                color: root.theme.primaryText
                font.family: "Roboto"
                font.pixelSize: 17
                font.bold: true
            }

            TextField {
                id: searchField
                objectName: root.objectName + "Search"
                Layout.fillWidth: true
                placeholderText: "Buscar por nombre, horario o grupo..."
                onTextChanged: {
                    root.searchQuery = text
                    root.searchRequestId = 0
                    root.searchResults = []
                    root.errorText = ""
                    root.searchPending = true
                    searchTimer.restart()
                }
            }

            ListView {
                id: courseResultList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 4
                model: root.filteredOptions

                delegate: Button {
                    objectName: root.objectName + "Option_" + String(modelData.id)
                    required property var modelData
                    width: courseResultList.width
                    height: 48
                    text: modelData.label
                    onClicked: root.chooseCourse(modelData)
                    background: Rectangle {
                        radius: 6
                        color: Number(modelData.id) === root.selectedCourseId
                               ? root.theme.accentSurface
                               : root.theme.raisedSurface
                        border.color: Number(modelData.id) === root.selectedCourseId
                                      ? root.theme.accent
                                      : root.theme.outline
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                visible: !root.searchPending && root.searchResults.length === 0
                text: root.errorText.length > 0
                      ? root.errorText
                      : "No se encontraron cursos."
                color: root.errorText.length > 0
                       ? root.theme.error
                       : root.theme.secondaryText
                font.family: "Roboto"
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }

            Label {
                Layout.fillWidth: true
                visible: root.searchPending
                text: "Buscando cursos..."
                color: root.theme.secondaryText
                font.family: "Roboto"
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
