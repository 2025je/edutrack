import asyncio
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickView

from edutrack_desktop.presentation.backend import DesktopBackend


def test_backup_page_formats_timestamp_for_local_display(tmp_path, gui_application):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    qml_directory = (
        Path(__file__).parents[1] / "src" / "edutrack_desktop" / "presentation" / "qml"
    )
    view = QQuickView()
    try:
        theme_component = QQmlComponent(
            view.engine(),
            QUrl.fromLocalFile(str(qml_directory / "components" / "AppTheme.qml")),
        )
        theme = theme_component.create()
        assert theme is not None, [
            error.toString() for error in theme_component.errors()
        ]

        page_url = QUrl.fromLocalFile(str(qml_directory / "pages" / "BackupsPage.qml"))
        page_component = QQmlComponent(view.engine(), page_url)
        root = page_component.createWithInitialProperties(
            {
                "backendObject": backend,
                "windowController": None,
                "theme": theme,
            }
        )
        assert root is not None, [error.toString() for error in page_component.errors()]

        timestamp = "2026-10-31T14:26:40+00:00"
        formatted = root.formatModifiedAt(timestamp)
        expected = (
            datetime.fromisoformat(timestamp).astimezone().strftime("%d/%m/%Y %H:%M")
        )
        assert re.fullmatch(r"\d{2}/\d{2}/2026 \d{2}:\d{2}", formatted)
        assert formatted == expected
        assert root.formatModifiedAt("") == "Fecha desconocida"
    finally:
        view.close()
        gui_application.processEvents()
        asyncio.run(backend.store.dispose())
