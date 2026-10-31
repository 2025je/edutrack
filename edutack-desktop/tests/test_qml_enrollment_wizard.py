import asyncio
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, QUrl, Qt
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

from edutrack_desktop.presentation.backend import DesktopBackend
from edutrack_desktop.presentation.session_settings import SessionSettings


@pytest.fixture
def enrollment_wizard(tmp_path, gui_application):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Test Campus", "")
    backend.createCourse(
        "English",
        "Morning",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    backend.saveStudent("", "PEREZ", "ANA", "12345678", "987654321")

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
        str(qml_directory / "pages" / "EnrollmentWizardPage.qml")
    )
    page_component = QQmlComponent(view.engine(), page_url)
    root = page_component.createWithInitialProperties(
        {"backendObject": backend, "theme": theme}
    )
    assert root is not None, [
        error.toString() for error in page_component.errors()
    ]

    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setContent(page_url, page_component, root)
    view.resize(1200, 900)
    view.show()
    gui_application.processEvents()
    QTest.qWait(50)
    root.begin()

    try:
        yield view, root, backend
    finally:
        view.close()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())


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


def _find_visual_item(window, object_name):
    pending = list(window.contentItem().childItems())
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
    raise AssertionError(f"QML item {object_name!r} was not found.")


def _qml_texts(root):
    items = [root]
    items.extend(root.findChildren(QObject))
    return [
        str(item.property("text"))
        for item in items
        if item.property("text") is not None
    ]


def test_qml_wizard_search_selection_validation_and_keyboard_save(
    enrollment_wizard, gui_application
):
    view, root, backend = enrollment_wizard
    search = _item(root, "enrollmentStudentSearch")
    search.setProperty("text", "perez ana")
    QTest.qWait(300)
    gui_application.processEvents()

    results = root.property("searchResults")
    assert len(results) == 1
    option = _item(root, "enrollmentStudentOption")
    _click(view, option)
    assert root.property("selectedStudent")["id"] == backend.students[0]["id"]

    _click(view, _item(root, "enrollmentContinueToCourseButton"))
    assert root.property("currentStep") == 2
    enrollment_fee = _item(root, "newEnrollmentFee")
    monthly_fee = _item(root, "newEnrollmentMonthlyFee")
    assert enrollment_fee.property("text") == "100.00"
    assert monthly_fee.property("text") == "80.00"
    _click(view, _item(root, "newEnrollmentFeeIncrementButton"))
    assert enrollment_fee.property("text") == "100.01"
    _click(view, _item(root, "newEnrollmentFeeDecrementButton"))
    assert enrollment_fee.property("text") == "100.00"
    QTest.keyClick(
        view,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.ControlModifier,
    )
    QTest.keyClick(view, Qt.Key.Key_1)
    assert enrollment_fee.property("text") == "1"
    QTest.keyClick(view, Qt.Key.Key_Up)
    assert enrollment_fee.property("text") == "1.01"
    QTest.keyClick(view, Qt.Key.Key_Down)
    assert enrollment_fee.property("text") == "1.00"
    enrollment_fee.setProperty("text", "100.00")
    assert root.findChild(QObject, "newEnrollmentRecordCode") is None
    assert not any(
        "Código de ficha" in text or text == "Promotores"
        for text in _qml_texts(root)
    )

    date_field = _item(root, "newEnrollmentDate")
    assert date_field.property("valid") is True
    date_field.setProperty("value", "invalid-date")
    assert date_field.property("valid") is False
    _click(view, _item(root, "enrollmentContinueToSummaryButton"))
    assert root.property("currentStep") == 2
    assert "fecha válida" in root.property("errorText")

    date_field.setProperty("value", "2026-01-02")
    assert date_field.property("displayText") == "02/01/2026"
    _click(view, _item(root, "newEnrollmentDateOpenButton"))
    QTest.qWait(100)
    date_option = _find_visual_item(
        view,
        "newEnrollmentDateDay_2026-01-02",
    )
    _click(view, date_option)
    assert date_field.property("value") == "2026-01-02"
    assert date_field.property("popupOpen") is False
    QTest.qWait(250)

    monthly_fee.forceActiveFocus()
    monthly_fee.setProperty("text", "80.7")
    _click(view, _item(root, "enrollmentContinueToSummaryButton"))
    assert root.property("currentStep") == 3, root.property("errorText")
    assert monthly_fee.property("text") == "80.70"
    assert not any(
        "Código de ficha" in text or text == "Promotores"
        for text in _qml_texts(root)
    )

    QTest.keyClick(
        view,
        Qt.Key.Key_S,
        Qt.KeyboardModifier.ControlModifier,
    )
    QTest.qWait(50)
    gui_application.processEvents()

    assert root.property("currentStep") == 4
    assert len(backend.manifest["enrollments"]) == 1
    assert root.property("savedResult").toVariant()["student"] == "PEREZ ANA"
    assert backend.manifest["enrollments"][0]["record_code"] is None
    assert backend.manifest["enrollments"][0]["promoter_ids"] == []
    assert backend.manifest["enrollments"][0]["monthly_fee"] == "80.70"
    assert not any(
        "Código de ficha" in text or text == "Promotores"
        for text in _qml_texts(root)
    )
    assert backend.errorMessage == "Matrícula guardada en este dispositivo."


def test_qml_wizard_validates_new_student_and_cancels_with_escape(
    enrollment_wizard, gui_application
):
    view, root, _backend = enrollment_wizard
    canceled = []
    root.cancelRequested.connect(lambda: canceled.append(True))

    _click(view, _item(root, "enrollmentCreateStudentButton"))
    assert root.property("creatingStudent") is True
    _click(view, _item(root, "enrollmentContinueToCourseButton"))
    assert root.property("currentStep") == 1
    assert "Completa apellidos, nombres" in root.property("errorText")

    QTest.keyClick(view, Qt.Key.Key_Escape)
    QTest.qWait(20)
    assert canceled == [True]


def test_qml_wizard_creates_student_without_leaving_enrollment(
    enrollment_wizard, gui_application
):
    view, root, backend = enrollment_wizard
    _click(view, _item(root, "enrollmentCreateStudentButton"))
    last_name = _item(root, "newEnrollmentStudentLastName")
    last_name.setProperty("text", "PEREZ")
    first_name = _item(root, "newEnrollmentStudentFirstName")
    first_name.setProperty("text", "ANA")
    QTest.qWait(350)
    gui_application.processEvents()
    assert len(root.property("duplicateCandidates")) == 1

    last_name.setProperty("text", "ROJAS")
    first_name.setProperty("text", "LUCIA")
    _item(root, "newEnrollmentStudentPhones").setProperty("text", "912345678")
    QTest.qWait(350)
    gui_application.processEvents()
    assert root.property("duplicateCandidates") == []

    _click(view, _item(root, "enrollmentContinueToCourseButton"))
    assert root.property("currentStep") == 2
    _click(view, _item(root, "enrollmentContinueToSummaryButton"))
    assert root.property("currentStep") == 3
    _click(view, _item(root, "enrollmentSaveButton"))

    assert root.property("currentStep") == 4
    assert len(backend.manifest["students"]) == 2
    assert len(backend.manifest["enrollments"]) == 1
    assert backend.manifest["students"][-1]["last_name"] == "ROJAS"
    assert backend.manifest["students"][-1]["first_name"] == "LUCIA"


def test_main_ctrl_m_opens_enrollment_wizard_after_lazy_loading(
    tmp_path, gui_application
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Test Campus", "")
    session_store = SessionSettings(tmp_path / "session.ini")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("sessionStore", session_store)
    main_url = QUrl.fromLocalFile(
        str(
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "presentation"
            / "qml"
            / "Main.qml"
        )
    )
    try:
        engine.load(main_url)
        root = engine.rootObjects()[0] if engine.rootObjects() else None
        assert root is not None
        window_flags = root.flags()
        assert not (window_flags & Qt.WindowType.FramelessWindowHint)
        assert window_flags & Qt.WindowType.WindowTitleHint
        assert window_flags & Qt.WindowType.WindowSystemMenuHint
        assert window_flags & Qt.WindowType.WindowMinimizeButtonHint
        assert window_flags & Qt.WindowType.WindowMaximizeButtonHint
        assert window_flags & Qt.WindowType.WindowCloseButtonHint
        assert root.width() == root.minimumWidth()
        assert root.height() == root.minimumHeight()
        root.setProperty("visible", True)
        QTest.qWait(200)
        gui_application.processEvents()

        QTest.keyClick(
            root,
            Qt.Key.Key_M,
            Qt.KeyboardModifier.ControlModifier,
        )
        QTest.qWait(350)
        gui_application.processEvents()

        assert root.property("selectedWorkspaceSection") == "Matrículas"
        wizard = _find_visual_item(root, "enrollmentWizardPage")
        assert wizard.property("currentStep") == 1
    finally:
        root_objects = engine.rootObjects()
        if root_objects:
            root_objects[0].close()
        engine.deleteLater()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())


def test_main_restores_and_persists_selected_workspace_section(
    tmp_path, gui_application
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Test Campus", "")
    course_id = backend.createCourse(
        "English",
        "Morning",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    backend.saveStudent("", "PEREZ", "ANA", "12345678", "987654321")
    student_id = backend.selectedStudent["id"]
    assert backend.saveEnrollment(
        "",
        {
            "student_id": student_id,
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
        },
    )
    enrollment_id = backend.selectedEnrollment["id"]
    session_store = SessionSettings(tmp_path / "session.ini")
    main_url = QUrl.fromLocalFile(
        str(
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "presentation"
            / "qml"
            / "Main.qml"
        )
    )
    engines = []

    def open_main_window():
        engine = QQmlApplicationEngine()
        engines.append(engine)
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("sessionStore", session_store)
        engine.load(main_url)
        root = engine.rootObjects()[0] if engine.rootObjects() else None
        assert root is not None
        root.setProperty("visible", True)
        QTest.qWait(250)
        gui_application.processEvents()
        return root

    try:
        first_root = open_main_window()
        courses_button = _find_visual_item(
            first_root,
            "workspaceSectionButton_Cursos",
        )
        _click(first_root, courses_button)
        QTest.qWait(350)
        assert first_root.property("selectedWorkspaceSection") == "Cursos"

        first_root.close()
        gui_application.processEvents()
        saved_state = json.loads(session_store.loadState())
        assert saved_state["selectedWorkspaceSection"] == "Cursos"

        second_root = open_main_window()
        QTest.qWait(250)
        assert second_root.property("selectedWorkspaceSection") == "Cursos"
        _find_visual_item(second_root, "coursesPanel")
        courses_button = _find_visual_item(
            second_root,
            "workspaceSectionButton_Cursos",
        )
        assert courses_button.property("selected") is True

        students_button = _find_visual_item(
            second_root,
            "workspaceSectionButton_Estudiantes",
        )
        _click(second_root, students_button)
        QTest.qWait(350)
        assert _find_visual_item(second_root, "studentRow_" + student_id)

        students_page = _find_visual_item(second_root, "studentsPage")
        student_search = _find_visual_item(second_root, "studentSearch")
        status_filter = _find_visual_item(second_root, "studentStatusFilter")
        course_filter = _find_visual_item(second_root, "studentCourseFilter")
        student_search.setProperty("text", "sin coincidencia")
        QTest.qWait(80)
        assert backend.studentListModel.matchingCount == 1
        QTest.qWait(250)
        assert backend.studentListModel.matchingCount == 0

        student_search.setProperty("text", "")
        status_filter.setProperty("currentIndex", 2)
        assert QMetaObject.invokeMethod(students_page, "applyStudentFilters")
        assert backend.studentListModel.matchingCount == 0

        status_filter.setProperty("currentIndex", 1)
        course_filter.setProperty("currentIndex", 1)
        assert QMetaObject.invokeMethod(students_page, "applyStudentFilters")
        assert backend.studentListModel.matchingCount == 1

        status_filter.setProperty("currentIndex", 0)
        course_filter.setProperty("currentIndex", 0)
        assert QMetaObject.invokeMethod(students_page, "applyStudentFilters")

        enrollments_button = _find_visual_item(
            second_root,
            "workspaceSectionButton_Matrículas",
        )
        _click(second_root, enrollments_button)
        QTest.qWait(350)
        assert _find_visual_item(second_root, "enrollmentRow_" + enrollment_id)

        sync_button = _find_visual_item(
            second_root,
            "workspaceSectionButton_Sincronización",
        )
        _click(second_root, sync_button)
        QTest.qWait(350)
        sync_page = second_root.findChild(QObject, "syncPage")
        confirm_import_button = second_root.findChild(
            QObject,
            "syncConfirmImportButton",
        )
        assert sync_page is not None
        assert confirm_import_button is not None
        assert confirm_import_button.property("enabled") is False

        students_button = _find_visual_item(
            second_root,
            "workspaceSectionButton_Estudiantes",
        )
        _click(second_root, students_button)
        QTest.qWait(350)
        students_list = _find_visual_item(second_root, "studentsList")
        assert students_list.property("compactLayout") is True
        edit_button_name = (
            "editStudentButtonCompact"
            if students_list.property("compactLayout")
            else "editStudentButton"
        )
        edit_student_button = _find_visual_item(second_root, edit_button_name)
        _click(second_root, edit_student_button)
        QTest.qWait(100)
        students_page = _find_visual_item(second_root, "studentsPage")
        assert students_page.property("currentView") == "edit"
        student_last_name = _find_visual_item(
            second_root,
            "studentLastNameField",
        )
        assert student_last_name.property("text") == "PEREZ"
    finally:
        for engine in engines:
            root_objects = engine.rootObjects()
            if root_objects:
                root_objects[0].close()
            engine.deleteLater()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())


def test_main_starts_at_minimum_size_without_saved_window_geometry(
    tmp_path, gui_application
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Test Campus", "")
    session_store = SessionSettings(tmp_path / "session.ini")
    assert session_store.saveState(
        json.dumps(
            {
                "version": 1,
            }
        )
    )
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("sessionStore", session_store)
    main_url = QUrl.fromLocalFile(
        str(
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "presentation"
            / "qml"
            / "Main.qml"
        )
    )
    try:
        engine.load(main_url)
        root = engine.rootObjects()[0] if engine.rootObjects() else None
        assert root is not None
        root.setProperty("visible", True)
        QTest.qWait(250)
        gui_application.processEvents()

        sidebar_scroll = root.findChild(QObject, "workspaceSidebarScroll")
        panel_scroll = root.findChild(QObject, "workspacePanelScroll")
        assert sidebar_scroll is not None
        assert panel_scroll is not None
        assert sidebar_scroll.property("contentHeight") > sidebar_scroll.property("height")
        assert panel_scroll.property("contentHeight") > panel_scroll.property("height")
        for section in (
            "Matrículas",
            "Estudiantes",
            "Cursos",
            "Sincronización",
            "Respaldos",
            "Resumen",
        ):
            button = _find_visual_item(
                root,
                "workspaceSectionButton_" + section,
            )
            label = _find_visual_item(
                root,
                "workspaceSectionLabel_" + section,
            )
            label_top = label.mapToItem(button, QPointF(0, 0)).y()
            assert label_top >= 0
            assert label_top + label.height() <= button.height()

        screen_geometry = root.screen().geometry()
        max_width = max(root.minimumWidth(), screen_geometry.width())
        max_height = max(root.minimumHeight(), screen_geometry.height())
        expected_x = screen_geometry.x() + max(
            0, (screen_geometry.width() - root.width()) / 2
        )
        expected_y = screen_geometry.y() + max(
            0, (screen_geometry.height() - root.height()) / 2
        )
        assert root.width() == root.minimumWidth()
        assert root.height() == root.minimumHeight()
        assert abs(root.x() - expected_x) <= 4
        assert abs(root.y() - expected_y) <= 4
        assert root.x() >= screen_geometry.x() - 4
        assert root.y() >= screen_geometry.y() - 4
        assert root.x() + root.width() <= screen_geometry.x() + max_width + 4
        assert root.y() + root.height() <= screen_geometry.y() + max_height + 4
    finally:
        root_objects = engine.rootObjects()
        if root_objects:
            root_objects[0].close()
        engine.deleteLater()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())


def test_main_persists_window_geometry_across_restarts(tmp_path, gui_application):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Test Campus", "")
    session_store = SessionSettings(tmp_path / "session.ini")
    main_url = QUrl.fromLocalFile(
        str(
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "presentation"
            / "qml"
            / "Main.qml"
        )
    )
    engines = []

    def open_main_window():
        engine = QQmlApplicationEngine()
        engines.append(engine)
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("sessionStore", session_store)
        engine.load(main_url)
        root = engine.rootObjects()[0] if engine.rootObjects() else None
        assert root is not None
        root.setProperty("visible", True)
        QTest.qWait(250)
        gui_application.processEvents()
        return root

    try:
        first_root = open_main_window()
        first_root.setProperty("x", 60)
        first_root.setProperty("y", 70)
        first_root.setProperty("width", 1120)
        first_root.setProperty("height", 740)
        gui_application.processEvents()
        saved_geometry = {
            "x": first_root.x(),
            "y": first_root.y(),
            "width": first_root.width(),
            "height": first_root.height(),
        }

        first_root.close()
        gui_application.processEvents()
        saved_state = json.loads(session_store.loadState())
        assert saved_state["window"] == saved_geometry

        second_root = open_main_window()
        assert second_root.x() == saved_geometry["x"]
        assert second_root.y() == saved_geometry["y"]
        assert second_root.width() == saved_geometry["width"]
        assert second_root.height() == saved_geometry["height"]
    finally:
        for engine in engines:
            root_objects = engine.rootObjects()
            if root_objects:
                root_objects[0].close()
            engine.deleteLater()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())


def test_main_close_button_waits_for_active_operation(
    tmp_path, gui_application
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Test Campus", "")
    session_store = SessionSettings(tmp_path / "session.ini")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("sessionStore", session_store)
    main_url = QUrl.fromLocalFile(
        str(
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "presentation"
            / "qml"
            / "Main.qml"
        )
    )
    try:
        engine.load(main_url)
        root = engine.rootObjects()[0] if engine.rootObjects() else None
        assert root is not None
        root.setProperty("visible", True)
        QTest.qWait(250)
        gui_application.processEvents()

        backend._save_in_progress = True
        backend.activityStateChanged.emit()
        gui_application.processEvents()
        root.close()

        assert root.isVisible()
        assert root.property("closeAfterCurrentOperation") is True

        backend._save_in_progress = False
        backend.activityStateChanged.emit()
        QTest.qWait(50)
        gui_application.processEvents()

        assert root.isVisible() is False
    finally:
        root_objects = engine.rootObjects()
        if root_objects:
            root_objects[0].close()
        engine.deleteLater()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())


def test_main_can_close_while_startup_overlay_is_visible(
    tmp_path, gui_application
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Test Campus", "")
    session_store = SessionSettings(tmp_path / "session.ini")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("sessionStore", session_store)
    main_url = QUrl.fromLocalFile(
        str(
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "presentation"
            / "qml"
            / "Main.qml"
        )
    )
    try:
        engine.load(main_url)
        root = engine.rootObjects()[0] if engine.rootObjects() else None
        assert root is not None
        root.setProperty("visible", True)
        root.setProperty("startupComplete", False)
        gui_application.processEvents()

        root.close()

        assert root.isVisible() is False
    finally:
        root_objects = engine.rootObjects()
        if root_objects:
            root_objects[0].close()
        engine.deleteLater()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())


def test_main_closes_after_opening_and_closing_a_saved_campus(
    tmp_path, gui_application
):
    database_path = tmp_path / "default.sqlite3"
    saved_campus_path = tmp_path / "saved.sqlite3"
    backend = DesktopBackend(
        database_path,
        tmp_path / "campuses.json",
    )
    assert backend.createWorkspace(
        "Sede guardada",
        "",
        str(saved_campus_path),
    )
    assert backend.closeCampus()

    session_store = SessionSettings(tmp_path / "session.ini")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("sessionStore", session_store)
    main_url = QUrl.fromLocalFile(
        str(
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "presentation"
            / "qml"
            / "Main.qml"
        )
    )
    try:
        engine.load(main_url)
        root = engine.rootObjects()[0] if engine.rootObjects() else None
        assert root is not None
        root.setProperty("visible", True)
        QTest.qWait(250)
        gui_application.processEvents()

        campus_setup = root.findChild(QObject, "campusSetupFlick")
        open_button = _find_visual_item(root, "savedCampusOpenButton_0")
        assert campus_setup is not None
        button_bottom = open_button.mapToItem(
            campus_setup,
            QPointF(open_button.width() / 2, open_button.height()),
        ).y()
        if button_bottom > campus_setup.height():
            campus_setup.setProperty(
                "contentY",
                campus_setup.property("contentY")
                + button_bottom
                - campus_setup.height()
                + 1,
            )
            gui_application.processEvents()
        _click(root, open_button)
        QTest.qWait(250)
        assert backend.hasWorkspace

        _click(
            root,
            _find_visual_item(root, "closeCampusButton"),
        )
        dialog = root.findChild(QObject, "closeCampusDialog")
        assert dialog is not None
        assert dialog.property("visible")
        confirm_button = root.findChild(QObject, "confirmCloseCampusButton")
        assert confirm_button is not None
        _click(root, confirm_button)

        assert not backend.hasWorkspace
        assert dialog.property("visible")
        assert dialog.property("modal") is False
        root.close()
        assert root.isVisible() is False
    finally:
        root_objects = engine.rootObjects()
        if root_objects:
            root_objects[0].close()
        engine.deleteLater()
        gui_application.processEvents()
        if backend.store is not None:
            asyncio.run(backend.store.dispose())
