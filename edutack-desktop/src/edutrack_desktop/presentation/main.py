import asyncio
import os
import sys
from threading import Event
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QRunnable,
    QStandardPaths,
    QThreadPool,
    QTimer,
    QUrl,
)
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

    backend = DesktopBackend(settings=settings, defer_initialize=True)
    backend.moveToThread(ui_thread)
    return backend


class _BackendInitializationWorker(QRunnable):
    def __init__(self, ui_thread):
        super().__init__()
        self.setAutoDelete(False)
        self._ui_thread = ui_thread
        self.backend = None
        self.error = None
        self.completed = Event()

    def run(self):
        try:
            self.backend = _initialize_backend(self._ui_thread)
        except Exception as exc:
            self.error = exc
        finally:
            self.completed.set()


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
    import PySide6.QtAsyncio as QtAsyncio
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlIncubator
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtQuickControls2 import QQuickStyle

    from .session_settings import SessionSettings
    from .startup_splash import StartupSplash

    logger = structlog.get_logger(__name__)
    splash = StartupSplash(icon_path)
    splash.show()
    app.processEvents()
    exit_code = 0
    engine = None
    component = None
    incubator = None
    root_window = None
    backend = None
    backend_ready = False
    startup_started = False
    startup_timer = QTimer(app)
    startup_timer.setInterval(50)

    def fail_startup(event, message, error_type="StartupError"):
        nonlocal exit_code
        exit_code = 1
        startup_timer.stop()
        splash.close_splash()
        logger.error(event, error_type=error_type)
        QMessageBox.critical(None, "No se pudo iniciar EduTrack", message)
        app.exit(1)

    async def initialize_backend():
        nonlocal backend, backend_ready
        try:
            worker = _BackendInitializationWorker(app.thread())
            QThreadPool.globalInstance().start(worker)
            while not worker.completed.is_set():
                await asyncio.sleep(0.05)
            if worker.error is not None:
                raise worker.error
            if worker.backend is None:
                raise RuntimeError("No se pudo crear el backend de la aplicación.")
            backend = worker.backend
            await backend.initialize()
        except Exception as exc:
            fail_startup(
                "desktop.startup_failed",
                str(exc) or type(exc).__name__,
                type(exc).__name__,
            )
            return
        backend_ready = True

    def finish_startup():
        nonlocal component, engine, incubator, root_window, startup_started

        if engine is None:
            if not startup_started:
                startup_started = True
                asyncio.create_task(initialize_backend())
                return
            if not backend_ready:
                return
            if backend is None:
                fail_startup(
                    "desktop.startup_failed",
                    "No se pudo inicializar el backend de la aplicación.",
                )
                return
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
            splash.close_splash()
            QTimer.singleShot(500, app.quit)
        else:
            root_window.setProperty("visible", True)
            splash.close_splash()

    startup_timer.timeout.connect(finish_startup)
    startup_timer.start()
    QtAsyncio.run()
    logger.info("desktop.stopped", exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
