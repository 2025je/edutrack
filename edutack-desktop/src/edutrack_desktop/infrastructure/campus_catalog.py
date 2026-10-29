import json
from pathlib import Path

from pydantic import ValidationError

from .schemas import CampusCatalogHeader, CampusCatalogRecord


class CampusCatalogError(RuntimeError):
    pass


class CampusCatalog:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.records = []
        self.active_path = ""
        self._read()

    def contains(self, path):
        resolved = str(Path(path).expanduser().resolve())
        return any(record["path"] == resolved for record in self.records)

    def register(self, path, campus_name, activate=True):
        resolved = str(Path(path).expanduser().resolve())
        record = {"path": resolved, "campus_name": campus_name}
        existing = next(
            (item for item in self.records if item["path"] == resolved),
            None,
        )
        if existing is None:
            self.records.append(record)
        else:
            existing["campus_name"] = campus_name
        if activate:
            self.active_path = resolved
        self._write()

    def activate(self, path):
        resolved = str(Path(path).expanduser().resolve())
        if not self.contains(resolved):
            raise CampusCatalogError(
                "La base seleccionada no está registrada en el catálogo local."
            )
        self.active_path = resolved
        self._write()

    def deactivate(self):
        self.active_path = ""
        self._write()

    def _read(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CampusCatalogError(
                f"No se pudo leer el catálogo local de sedes: {exc}"
            ) from exc
        try:
            header = CampusCatalogHeader.model_validate(data)
        except ValidationError as exc:
            raise CampusCatalogError(
                "El catálogo local de sedes tiene un formato no válido."
            ) from exc

        records = []
        paths = set()
        for item in header.campuses:
            try:
                record = CampusCatalogRecord.model_validate(item)
            except ValidationError as exc:
                raise CampusCatalogError(
                    "El catálogo local contiene una sede no válida."
                ) from exc
            if not record.path:
                raise CampusCatalogError(
                    "El catálogo local contiene una sede no válida."
                )
            path = str(Path(record.path).expanduser().resolve())
            if path in paths:
                raise CampusCatalogError(
                    "El catálogo local contiene bases de datos repetidas."
                )
            paths.add(path)
            records.append({"path": path, "campus_name": record.campus_name})

        active_path = header.active_path
        if not isinstance(active_path, str):
            raise CampusCatalogError(
                "El catálogo local contiene una sede activa no válida."
            )
        active_path = (
            str(Path(active_path).expanduser().resolve()) if active_path else ""
        )
        if active_path and active_path not in paths:
            raise CampusCatalogError("La sede activa no aparece en el catálogo local.")
        self.records = records
        self.active_path = active_path

    def _write(self):
        data = {
            "version": 1,
            "active_path": self.active_path,
            "campuses": self.records,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_name(f"{self.path.name}.tmp")
            temporary_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except OSError as exc:
            raise CampusCatalogError(
                f"No se pudo guardar el catálogo local de sedes: {exc}"
            ) from exc
