import os
from pathlib import Path

import PySide6
import pytest
from PySide6.QtGui import QGuiApplication

_PYSIDE_DLL_SEARCH_HANDLES = []
if os.name == "nt":
    _PYSIDE_DLL_SEARCH_HANDLES.append(
        os.add_dll_directory(str(Path(PySide6.__file__).resolve().parent))
    )

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def gui_application():
    application = QGuiApplication.instance() or QGuiApplication([])
    application.setQuitOnLastWindowClosed(False)
    yield application
