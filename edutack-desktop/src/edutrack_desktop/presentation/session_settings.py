from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QObject, Property, QSettings, Signal, Slot

from ..infrastructure.schemas import SessionState


class SessionSettings(QObject):
    errorChanged = Signal()

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self._settings = (
            QSettings()
            if path is None
            else QSettings(str(Path(path)), QSettings.Format.IniFormat)
        )
        self._error_message = ""

    @Property(str, notify=errorChanged)
    def errorMessage(self):
        return self._error_message

    @Slot(result=str)
    def loadState(self):
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            self._set_error("No se pudo leer el estado guardado de EduTrack Desktop.")
            return ""
        state = self._settings.value("desktop/session-state", "{}")
        if not isinstance(state, str):
            self._set_error("El estado guardado de EduTrack Desktop no es válido.")
            return ""
        self._set_error("")
        return state

    @Slot(str, result=bool)
    def saveState(self, serialized_state):
        try:
            SessionState.model_validate_json(serialized_state)
        except ValidationError as exc:
            self._set_error(f"No se pudo guardar el estado de la sesión: {exc}")
            return False
        self._settings.setValue("desktop/session-state", serialized_state)
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            self._set_error("No se pudo guardar el estado de EduTrack Desktop.")
            return False
        self._set_error("")
        return True

    def _set_error(self, message):
        if message != self._error_message:
            self._error_message = message
            self.errorChanged.emit()
