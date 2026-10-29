from pydantic import ValidationError
import pytest

from edutrack_desktop.infrastructure.app_settings import DesktopSettings


def test_desktop_settings_reads_environment(monkeypatch, tmp_path):
    database_path = tmp_path / "workspace.sqlite3"
    monkeypatch.setenv("EDUTRACK_DESKTOP_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("EDUTRACK_DESKTOP_QT_MATERIAL_VARIANT", "Normal")
    monkeypatch.setenv("EDUTRACK_DESKTOP_LOG_LEVEL", "DEBUG")

    settings = DesktopSettings()

    assert settings.database_path == database_path
    assert settings.qt_material_variant == "Normal"
    assert settings.log_level == "DEBUG"


def test_desktop_settings_rejects_unsupported_material_variant(monkeypatch):
    monkeypatch.setenv("EDUTRACK_DESKTOP_QT_MATERIAL_VARIANT", "Compact")

    with pytest.raises(ValidationError):
        DesktopSettings()
