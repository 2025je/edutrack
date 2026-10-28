import json

from edutrack_desktop.session_settings import SessionSettings


def test_session_settings_round_trip(tmp_path):
    settings = SessionSettings(tmp_path / "session.ini")
    state = {"version": 1, "currentPage": 2, "darkMode": True}

    assert settings.saveState(json.dumps(state))
    assert json.loads(settings.loadState()) == state
    assert settings.errorMessage == ""


def test_session_settings_rejects_invalid_state(tmp_path):
    settings = SessionSettings(tmp_path / "session.ini")

    assert not settings.saveState("{invalid")
    assert "No se pudo guardar" in settings.errorMessage
