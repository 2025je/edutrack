import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox


def _initialize_backend(ui_thread):
    import structlog

    from ..infrastructure.app_settings import DesktopSettings
    from ..infrastructure.logging_config import configure_logging
    from .backend import DesktopBackend

    settings = DesktopSettings()
    os.environ.setdefault(
        "QT_QUICK_CONTROLS_MATERIAL_VARIANT", settings.qt_material_variant
    )
    app_data_dir = settings.data_dir or Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    )
    if not app_data_dir:
        raise RuntimeError("No se pudo determinar la carpeta de datos de EduTrack.")
    configure_logging(
        settings.log_level,
        app_data_dir / "logs" / "edutrack-desktop.jsonl",
    )
    logger = structlog.get_logger(__name__)
    logger.info("desktop.starting")

    backend = DesktopBackend(settings=settings)
    backend.moveToThread(ui_thread)
    return backend


def main():
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        sys.argv.remove("--smoke-test")
    QCoreApplication.setOrganizationName("EduTrack")
    QCoreApplication.setApplicationName("EduTrack Desktop")
    app = QApplication(sys.argv)
    resource_dir = Path(__file__).resolve().parent / "qml"
    icon_path = resource_dir / "icons" / "logo.svg"

    import structlog

    import PySide6
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlIncubator
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtQuickControls2 import QQuickStyle

    from .session_settings import SessionSettings

    logger = structlog.get_logger(__name__)
    engine = None
    component = None
    incubator = None
    root_window = None
    startup_pool = ThreadPoolExecutor(max_workers=1)
    startup_future = startup_pool.submit(_initialize_backend, app.thread())
    startup_timer = QTimer(app)
    startup_timer.setInterval(50)

    def fail_startup(event, message):
        startup_timer.stop()
        logger.error(event, error=message)
        QMessageBox.critical(None, "No se pudo iniciar EduTrack", message)
        app.exit(1)

    def finish_startup():
        nonlocal component, engine, incubator, root_window

        if engine is None:
            if not startup_future.done():
                return
            error = startup_future.exception()
            if error is not None:
                fail_startup(
                    "desktop.startup_failed",
                    str(error) or type(error).__name__,
                )
                return

            backend = startup_future.result()
            backend.setParent(app)

            app_icon = QIcon(str(icon_path))
            if app_icon.isNull():
                fail_startup(
                    "desktop.icon_load_failed",
                    f"No se pudo cargar el logo de EduTrack: {icon_path}",
                )
                return
            app.setWindowIcon(app_icon)
            QQuickStyle.setStyle("Material")
            font_path = resource_dir / "fonts" / "Roboto[wdth,wght].ttf"
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if (
                font_id < 0
                or "Roboto" not in QFontDatabase.applicationFontFamilies(font_id)
            ):
                fail_startup(
                    "desktop.font_load_failed",
                    f"No se pudo cargar la fuente Roboto: {font_path}",
                )
                return
            symbols_path = resource_dir / "fonts" / "MaterialSymbolsOutlined.ttf"
            symbols_font_id = QFontDatabase.addApplicationFont(str(symbols_path))
            if (
                symbols_font_id < 0
                or "Material Symbols Outlined"
                not in QFontDatabase.applicationFontFamilies(symbols_font_id)
            ):
                fail_startup(
                    "desktop.symbols_font_load_failed",
                    f"No se pudo cargar la fuente de iconos: {symbols_path}",
                )
                return
            app.setFont(QFont("Roboto"))

            engine = QQmlApplicationEngine()
            session_settings = SessionSettings(parent=app)
            engine.rootContext().setContextProperty("backend", backend)
            engine.rootContext().setContextProperty("sessionStore", session_settings)
            qml_import_path = Path(PySide6.__file__).resolve().parent / "qml"
            if qml_import_path.exists():
                engine.addImportPath(str(qml_import_path))
            qml_path = resource_dir / "Main.qml"
            component = QQmlComponent(engine)
            component.loadUrl(
                QUrl.fromLocalFile(str(qml_path)),
                QQmlComponent.CompilationMode.Asynchronous,
            )
            return

        if component is None or engine is None:
            return
        component_status = component.status()
        if component_status == QQmlComponent.Status.Loading:
            return
        if component_status == QQmlComponent.Status.Error:
            errors = "; ".join(error.toString() for error in component.errors())
            fail_startup(
                "desktop.qml_load_failed",
                errors or "No se pudo cargar la interfaz de la aplicación.",
            )
            return
        if component_status != QQmlComponent.Status.Ready:
            fail_startup(
                "desktop.qml_load_failed",
                "La interfaz no pudo completar su carga.",
            )
            return

        if incubator is None:
            incubator = QQmlIncubator(QQmlIncubator.IncubationMode.Asynchronous)
            component.create(incubator, engine.rootContext())
            return

        incubator_status = incubator.status()
        if incubator_status == QQmlIncubator.Status.Loading:
            return
        if incubator_status == QQmlIncubator.Status.Error:
            errors = "; ".join(error.toString() for error in incubator.errors())
            fail_startup(
                "desktop.qml_creation_failed",
                errors or "No se pudo crear la ventana de la aplicación.",
            )
            return
        if incubator_status != QQmlIncubator.Status.Ready:
            fail_startup(
                "desktop.qml_creation_failed",
                "La ventana de la aplicación no pudo completar su creación.",
            )
            return

        root_window = incubator.object()
        if not isinstance(root_window, QQuickWindow):
            fail_startup(
                "desktop.qml_root_is_not_window",
                "La interfaz no creó una ventana válida.",
            )
            return
        if smoke_test:
            root_window.setProperty("visible", False)
            QTimer.singleShot(500, app.quit)
        else:
            root_window.setProperty("visible", True)

    startup_timer.timeout.connect(finish_startup)
    startup_timer.start()
    exit_code = app.exec()
    startup_pool.shutdown(wait=False)
    logger.info("desktop.stopped", exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
