from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtQuick import QQuickItem, QQuickView
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest

from edutrack_desktop.presentation.backend import DesktopBackend


def _item(root, object_name):
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
    item = root.findChild(QQuickItem, object_name)
    if item is not None:
        return item
    raise AssertionError(f"QML item {object_name!r} was not found.")


def _click(view, item):
    center = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    QTest.mouseClick(
        view,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(center.x()), round(center.y())),
    )
    QTest.qWait(20)


def test_saved_campus_can_be_removed_from_list_without_deleting_database(
    tmp_path, gui_application
):
    database_path = tmp_path / "default.sqlite3"
    catalog_path = tmp_path / "campuses.json"
    saved_path = tmp_path / "saved.sqlite3"
    active_path = tmp_path / "active.sqlite3"
    backend = DesktopBackend(database_path, catalog_path)
    assert backend.createWorkspace("Sede guardada", "", str(saved_path))
    assert backend.createWorkspace("Sede activa", "", str(active_path))
    assert backend.closeCampus()

    qml_directory = (
        Path(__file__).parents[1]
        / "src"
        / "edutrack_desktop"
        / "presentation"
        / "qml"
    )
    font_path = qml_directory / "fonts" / "MaterialSymbolsOutlined.ttf"
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    assert font_id >= 0

    view = QQuickView()
    controller_component = QQmlComponent(view.engine())
    controller_component.setData(
        b"""import QtQuick
QtObject {
    property bool creatingCampus: false
    property color primaryTextColor: "#173b5e"
    property color secondaryTextColor: "#667085"
    property color accentTextColor: "#00796b"
    property color accentSurfaceColor: "#e3f3f0"
    property color nestedSurfaceColor: "#f8fafc"
    property color surfaceColor: "#ffffff"
    property color borderColor: "#e1e8f0"
    property color dividerColor: "#e7edf3"
    property color headerText: "#ffffff"
    property color createButton: "#00897b"
    property color createButtonPressed: "#00695c"
}""",
        QUrl(),
    )
    controller = controller_component.create()
    assert controller is not None, [
        error.toString() for error in controller_component.errors()
    ]

    page_url = QUrl.fromLocalFile(
        str(qml_directory / "pages" / "CampusSetupPage.qml")
    )
    page_component = QQmlComponent(view.engine(), page_url)
    root = page_component.createWithInitialProperties(
        {
            "backendObject": backend,
            "windowController": controller,
            "theme": controller,
        }
    )
    assert root is not None, [
        error.toString() for error in page_component.errors()
    ]
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setContent(page_url, page_component, root)
    view.resize(900, 700)
    view.show()
    gui_application.processEvents()
    QTest.qWait(50)

    try:
        grid = _item(root, "savedCampusesGrid")
        assert grid.property("count") == 2
        assert grid.isVisible()
        remove_button = _item(root, "savedCampusRemoveButton_0")
        _click(view, remove_button)
        dialog = root.findChild(QObject, "removeCampusDialog")
        assert dialog is not None
        assert dialog.property("visible")
        assert len(backend.campuses) == 2

        cancel_button = _item(root, "cancelRemoveCampusButton")
        _click(view, cancel_button)
        QTest.qWait(250)
        assert not dialog.property("visible")
        assert len(backend.campuses) == 2

        remove_button = _item(root, "savedCampusRemoveButton_0")
        _click(view, remove_button)
        confirm_button = _item(root, "confirmRemoveCampusButton")
        _click(view, confirm_button)
        QTest.qWait(250)

        assert [campus["campus_name"] for campus in backend.campuses] == [
            "Sede activa"
        ]
        assert saved_path.is_file()
        assert active_path.is_file()
    finally:
        view.close()
