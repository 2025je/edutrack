import uuid
from typing import Any


def build_manifest(student_count: int) -> dict[str, Any]:
    return {
        "format": "edutrack-offline",
        "version": 2,
        "bundle_id": str(uuid.uuid4()),
        "campus_id": 1,
        "campus_name": "Benchmark local",
        "campus_address": "",
        "students": [
            {
                "id": str(uuid.uuid4()),
                "server_id": None,
                "base_hash": None,
                "last_name": f"APELLIDO{index:05d}",
                "first_name": f"NOMBRE{index:05d}",
                "document_number": f"{10_000_000 + index:08d}",
                "phone_numbers": [f"9{index:08d}"],
                "active": True,
            }
            for index in range(1, student_count + 1)
        ],
        "enrollments": [],
        "courses": [],
        "promoters": [],
    }


def build_course_search_manifest(course_count: int) -> dict[str, Any]:
    manifest = build_manifest(1)
    student_id = manifest["students"][0]["id"]
    manifest["courses"] = [
        {
            "id": index,
            "server_id": None,
            "name": f"CURSO {index:05d}",
            "schedule": "MAÑANA",
            "group": "1",
            "start_date": "2026-01-01",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "capacity": 20,
            "active": True,
        }
        for index in range(1, course_count + 1)
    ]
    manifest["enrollments"] = [
        {
            "id": str(uuid.uuid4()),
            "server_id": None,
            "base_hash": None,
            "student_id": student_id,
            "student_server_id": None,
            "course_id": course_count,
            "enrollment_date": "2026-01-01",
            "promoter_ids": [],
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "record_code": None,
            "active": True,
            "record_image": None,
            "record_image_hash": "",
            "record_image_quality": 80,
        }
    ]
    return manifest


def build_enrollment_search_manifest(enrollment_count: int) -> dict[str, Any]:
    manifest = build_manifest(1)
    manifest["courses"] = [
        {
            "id": 1,
            "server_id": None,
            "name": "CURSO BENCHMARK",
            "schedule": "MAÑANA",
            "group": "1",
            "start_date": "2026-01-01",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "capacity": enrollment_count,
            "active": True,
        }
    ]
    student_id = manifest["students"][0]["id"]
    manifest["enrollments"] = [
        {
            "id": str(uuid.uuid4()),
            "server_id": None,
            "base_hash": None,
            "student_id": student_id,
            "student_server_id": None,
            "course_id": 1,
            "enrollment_date": "2026-01-02",
            "promoter_ids": [],
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "record_code": None,
            "active": True,
            "record_image": None,
            "record_image_hash": "",
            "record_image_quality": 80,
        }
        for _ in range(enrollment_count)
    ]
    return manifest
