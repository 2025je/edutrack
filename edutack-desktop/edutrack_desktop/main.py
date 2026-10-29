import os
import sys
from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication, QStandardPaths, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

import structlog

from .app.app_settings import DesktopSettings
from .app.backend import DesktopBackend
from .app.logging_config import configure_logging
from .app.session_settings import SessionSettings

logger = structlog.get_logger(__name__)


def main():
    settings = DesktopSettings()
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        sys.argv.remove("--smoke-test")
    os.environ.setdefault(
        "QT_QUICK_CONTROLS_MATERIAL_VARIANT", settings.qt_material_variant
    )
    QCoreApplication.setOrganizationName("EduTrack")
    QCoreApplication.setApplicationName("EduTrack Desktop")
    app = QGuiApplication(sys.argv)
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
    logger.info("desktop.starting")
    resource_dir = Path(__file__).resolve().parent / "qml"
    icon_path = resource_dir / "icons" / "logo.svg"
    app_icon = QIcon(str(icon_path))
    if app_icon.isNull():
        raise RuntimeError(f"No se pudo cargar el logo de EduTrack: {icon_path}")
    app.setWindowIcon(app_icon)
    QQuickStyle.setStyle("Material")
    font_path = resource_dir / "fonts" / "Roboto[wdth,wght].ttf"
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0 or "Roboto" not in QFontDatabase.applicationFontFamilies(font_id):
        raise RuntimeError(f"No se pudo cargar la fuente Roboto: {font_path}")
    symbols_path = (
        resource_dir
        / "fonts"
        / "MaterialSymbolsOutlined.ttf"
    )
    symbols_font_id = QFontDatabase.addApplicationFont(str(symbols_path))
    if (
        symbols_font_id < 0
        or "Material Symbols Outlined"
        not in QFontDatabase.applicationFontFamilies(symbols_font_id)
    ):
        raise RuntimeError(f"No se pudo cargar la fuente de iconos: {symbols_path}")
    app.setFont(QFont("Roboto"))
    engine = QQmlApplicationEngine()
    backend = DesktopBackend(settings=settings)
    backend.setParent(app)
    session_settings = SessionSettings(parent=app)
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("sessionStore", session_settings)
    qml_import_path = Path(PySide6.__file__).resolve().parent / "qml"
    if qml_import_path.exists():
        engine.addImportPath(str(qml_import_path))
    qml_path = resource_dir / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        logger.error("desktop.qml_load_failed", qml_path=str(qml_path))
        return 1
    if not engine.rootObjects()[0].setProperty("desktopBackend", backend):
        raise RuntimeError("No se pudo conectar el backend con la interfaz.")
    if smoke_test:
        engine.rootObjects()[0].setProperty("visible", False)
        QTimer.singleShot(500, app.quit)
    exit_code = app.exec()
    logger.info("desktop.stopped", exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
