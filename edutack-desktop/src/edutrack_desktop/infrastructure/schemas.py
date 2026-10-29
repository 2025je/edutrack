from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictStr


class SessionState(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: Literal[1]


class CampusCatalogHeader(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: Literal[1]
    campuses: list[Any]
    active_path: Any = ""


class CampusCatalogRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: StrictStr
    campus_name: StrictStr


class ManifestEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    format: Literal["edutrack-offline"]
    version: Literal[2, 3]
    campus_id: Any = None
    campus_name: Any
    campus_address: Any = ""
    campus_mode: Any = None
    students: list[Any]
    enrollments: list[Any]
    courses: list[Any]
    promoters: list[Any]


class StudentManifestRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: StrictStr
    phone_numbers: list[Any]


class EnrollmentManifestRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: StrictStr

