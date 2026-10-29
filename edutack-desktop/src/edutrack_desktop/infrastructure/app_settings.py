from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class DesktopSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EDUTRACK_DESKTOP_",
        extra="ignore",
    )

    data_dir: Path | None = None
    database_path: Path | None = None
    campus_catalog_path: Path | None = None
    qt_material_variant: Literal["Dense", "Normal"] = "Dense"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
