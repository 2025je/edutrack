import asyncio
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, Property, QPoint, QPointF, QUrl, Qt
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

from edutrack_desktop.presentation.backend import DesktopBackend


class _EnrollmentWindowController(QObject):
    @Property(str, constant=True)
    def selectedWorkspaceSection(self):
        return "Matrículas"


def _item(root, object_name):
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
    item = root.findChild(QObject, object_name)
    if item is not None:
        return item
    raise AssertionError(f"QML item {object_name!r} was not found.")


def _wait_for_item(root, object_name, gui_application):
    for _ in range(60):
        gui_application.processEvents()
        try:
            return _item(root, object_name)
        except AssertionError:
            QTest.qWait(50)
    raise AssertionError(f"QML item {object_name!r} was not loaded.")


def _click(view, item):
    center = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    QTest.mouseClick(
        view,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(center.x()), round(center.y())),
    )
    QTest.qWait(20)


def _variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def _wait_for_search(editor, gui_application):
    for _ in range(100):
        gui_application.processEvents()
        if not editor.property("studentSearchPending"):
            return
        QTest.qWait(10)
    raise AssertionError("Timed out waiting for the student search.")


def _wait_for_enrollment_list(backend, gui_application):
    model = backend.enrollmentListModel
    for _ in range(200):
        gui_application.processEvents()
        if not model.isLoading and model.matchingCount == 1:
            QTest.qWait(50)
            gui_application.processEvents()
            return
        QTest.qWait(10)
    raise AssertionError("Timed out waiting for the enrollment list.")


def test_enrollment_editor_defers_and_limits_student_data(tmp_path, gui_application):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Inglés",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "30",
    )
    selected_student_id = ""
    for index in range(21):
        backend.saveStudent(
            "",
            "PEREZ",
            f"NOMBRE{index:02}",
            f"{10000000 + index}",
            f"{912345600 + index}",
        )
        if index == 0:
            selected_student_id = backend.manifest["students"][-1]["id"]

    backend.saveEnrollment(
        "",
        {
            "student_id": selected_student_id,
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
        },
    )
    qml_directory = (
        Path(__file__).parents[1] / "src" / "edutrack_desktop" / "presentation" / "qml"
    )
    view = QQuickView()
    theme_component = QQmlComponent(
        view.engine(),
        QUrl.fromLocalFile(str(qml_directory / "components" / "AppTheme.qml")),
    )
    theme = theme_component.create()
    assert theme is not None, [error.toString() for error in theme_component.errors()]
    enrollments_url = QUrl.fromLocalFile(
        str(qml_directory / "pages" / "EnrollmentsPage.qml")
    )
    enrollments_component = QQmlComponent(view.engine(), enrollments_url)
    window_controller = _EnrollmentWindowController()
    root = enrollments_component.createWithInitialProperties(
        {
            "backendObject": backend,
            "windowController": window_controller,
            "theme": theme,
        }
    )
    assert root is not None, [
        error.toString() for error in enrollments_component.errors()
    ]
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setContent(enrollments_url, enrollments_component, root)
    view.resize(1200, 900)
    view.show()
    gui_application.processEvents()

    try:
        assert backend._student_rows_cache is None
        _wait_for_enrollment_list(backend, gui_application)

        try:
            edit_button = _wait_for_item(
                root,
                "editEnrollmentButton",
                gui_application,
            )
        except AssertionError as error:
            raise AssertionError(
                (
                    backend.enrollmentListModel.totalCount,
                    backend.enrollmentListModel.matchingCount,
                    backend.enrollmentListModel.rowCount(),
                    backend.enrollmentListModel.isLoading,
                    backend.errorMessage,
                    _item(root, "enrollmentList").property("count"),
                    _item(root, "enrollmentList").property("visible"),
                    _item(root, "enrollmentList").property("height"),
                    root.property("filteredEnrollmentCount"),
                )
            ) from error
        _click(view, edit_button)
        editor = _wait_for_item(root, "enrollmentEditorPage", gui_application)
        assert root.property("currentView") == "editor"
        assert editor is not None
        assert backend._student_rows_cache is None
        enrollment_fee = _item(editor, "editEnrollmentFee")
        monthly_fee = _item(editor, "editEnrollmentMonthlyFee")
        assert enrollment_fee.property("text") == "100.00"
        assert monthly_fee.property("text") == "80.00"

        search_responses = []
        backend.studentSearchFinished.connect(
            lambda request_id, rows, error: search_responses.append(
                (request_id, rows, error)
            )
        )
        assert QMetaObject.invokeMethod(editor, "refreshStudentSearch")
        _wait_for_search(editor, gui_application)
        gui_application.processEvents()

        search_results = _variant(editor.property("studentSearchResults"))
        assert len(search_results) == 20, (
            editor.property("errorText"),
            editor.property("studentSearchRequestId"),
            search_responses,
        )
        student_options = []
        for _ in range(100):
            gui_application.processEvents()
            student_options = _variant(editor.property("studentOptions"))
            if len(student_options) == 22:
                break
            QTest.qWait(10)
        assert len(student_options) == 22
        assert any(
            str(option["id"]) == str(selected_student_id) for option in student_options
        )
        assert backend._student_rows_cache is None

        search = _item(editor, "editEnrollmentStudentSearch")
        search.setProperty("text", "NOMBRE20")
        QTest.qWait(250)
        _wait_for_search(editor, gui_application)
        gui_application.processEvents()
        assert [
            student["label"]
            for student in _variant(editor.property("studentSearchResults"))
        ] == ["PEREZ NOMBRE20"]
        assert backend._student_rows_cache is None

        enrollment_fee.setProperty("text", "123.00")
        assert editor.property("hasUnsavedChanges") is True
        _click(view, _item(editor, "cancelEnrollmentEditButton"))
        _wait_for_item(editor, "continueEditingButton", gui_application)
        _click(view, _item(editor, "continueEditingButton"))
        assert enrollment_fee.property("text") == "123.00"
        assert editor.property("hasUnsavedChanges") is True
        _click(view, _item(editor, "cancelEnrollmentEditButton"))
        _wait_for_item(editor, "discardChangesButton", gui_application)
        _click(view, _item(editor, "discardChangesButton"))
        assert root.property("currentView") == "list"
    finally:
        view.close()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())
