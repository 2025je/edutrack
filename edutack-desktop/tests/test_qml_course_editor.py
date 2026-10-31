import asyncio
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QUrl, Qt
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

from edutrack_desktop.presentation.backend import DesktopBackend


def _item(root, object_name):
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
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


def test_course_fees_use_two_decimal_spinboxes(tmp_path, gui_application):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    backend.createCourse(
        "English",
        "Morning",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )

    qml_directory = (
        Path(__file__).parents[1]
        / "src"
        / "edutrack_desktop"
        / "presentation"
        / "qml"
    )
    view = QQuickView()
    theme_url = QUrl.fromLocalFile(
        str(qml_directory / "components" / "AppTheme.qml")
    )
    theme_component = QQmlComponent(view.engine(), theme_url)
    theme = theme_component.create()
    assert theme is not None, [
        error.toString() for error in theme_component.errors()
    ]

    page_url = QUrl.fromLocalFile(
        str(qml_directory / "pages" / "CourseEditorPage.qml")
    )
    page_component = QQmlComponent(view.engine(), page_url)
    root = page_component.createWithInitialProperties(
        {
            "backendObject": backend,
            "course": backend.courses[0],
            "theme": theme,
        }
    )
    assert root is not None, [
        error.toString() for error in page_component.errors()
    ]

    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setContent(page_url, page_component, root)
    view.resize(1000, 800)
    view.show()
    gui_application.processEvents()

    try:
        enrollment_fee = _item(root, "courseEnrollmentFee")
        monthly_fee = _item(root, "courseMonthlyFee")
        assert enrollment_fee.property("text") == "100.00"
        assert monthly_fee.property("text") == "80.00"
        _click(view, _item(root, "courseMonthlyFeeIncrementButton"))
        assert monthly_fee.property("text") == "80.01"
    finally:
        view.close()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())
