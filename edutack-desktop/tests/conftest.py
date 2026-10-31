import os

import pytest
from PySide6.QtGui import QGuiApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def gui_application():
    application = QGuiApplication.instance() or QGuiApplication([])
    yield application
