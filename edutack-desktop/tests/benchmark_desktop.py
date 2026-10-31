import asyncio
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from benchmark_data import build_course_search_manifest, build_manifest
from edutrack_desktop.domain.record_service import RecordMutation
from edutrack_desktop.infrastructure.store import LocalStore
from edutrack_desktop.infrastructure.logging_config import configure_logging
from edutrack_desktop.infrastructure.transfer import read_package, write_package


ITERATIONS = 5
DATASET_SIZES = (1_000, 10_000, 50_000)
PACKAGE_STUDENT_COUNT = 2_000


def median_milliseconds(samples: list[float]) -> float:
    return round(statistics.median(samples) * 1_000, 2)


async def benchmark_dataset(size: int, root: Path) -> dict[str, Any]:
    database_path = root / f"students-{size}.sqlite3"
    manifest = build_manifest(size)
    store = LocalStore(database_path)
    try:
        started = time.perf_counter()
        await store.save(manifest)
        initial_save_ms = round((time.perf_counter() - started) * 1_000, 2)

        await store.dispose()
        store = LocalStore(database_path)
        started = time.perf_counter()
        loaded_manifest = await store.load()
        open_and_load_ms = round((time.perf_counter() - started) * 1_000, 2)
        if loaded_manifest is None:
            raise RuntimeError(f"No se cargó el conjunto de {size} estudiantes.")

        await store.load()
        load_samples = []
        for _ in range(ITERATIONS):
            started = time.perf_counter()
            await store.load()
            load_samples.append(time.perf_counter() - started)

        query = f"APELLIDO{size:05d}"
        await store.search_students(query)
        search_samples = []
        for _ in range(ITERATIONS):
            started = time.perf_counter()
            results = await store.search_students(query)
            search_samples.append(time.perf_counter() - started)
            if len(results) != 1:
                raise RuntimeError(
                    f"La búsqueda de prueba devolvió {len(results)} resultados."
                )

        await store.student_page(query, 0, 0, 0, 50)
        student_page_samples = []
        for _ in range(ITERATIONS):
            started = time.perf_counter()
            rows, total_count, matching_count = await store.student_page(
                query,
                0,
                0,
                0,
                50,
            )
            student_page_samples.append(time.perf_counter() - started)
            if len(rows) != 1 or total_count != size or matching_count != 1:
                raise RuntimeError(
                    "La página SQL de estudiantes devolvió resultados inesperados."
                )

        student = manifest["students"][-1]
        incremental_save_samples = []
        for iteration in range(ITERATIONS):
            student["first_name"] = f"ACTUALIZADO{iteration}"
            started = time.perf_counter()
            await store.save_records(
                manifest,
                {
                    "students": [
                        RecordMutation(size - 1, student)
                    ]
                },
            )
            incremental_save_samples.append(time.perf_counter() - started)

        return {
            "students": size,
            "initial_save_ms_including_migrations": initial_save_ms,
            "open_and_load_ms": open_and_load_ms,
            "full_load_median_ms": median_milliseconds(load_samples),
            "indexed_search_median_ms": median_milliseconds(search_samples),
            "student_page_search_median_ms": median_milliseconds(
                student_page_samples
            ),
            "one_record_incremental_save_median_ms": median_milliseconds(
                incremental_save_samples
            ),
        }
    finally:
        await store.dispose()


async def benchmark_course_search(size: int, root: Path) -> dict[str, Any]:
    database_path = root / f"course-search-{size}.sqlite3"
    manifest = build_course_search_manifest(size)
    student_id = manifest["students"][0]["id"]
    store = LocalStore(database_path)
    try:
        await store.save(manifest)
        query = f"CURSO {size:05d}"
        await store.student_page(query, 0, 0, 0, 50)
        samples = []
        for _ in range(ITERATIONS):
            started = time.perf_counter()
            rows, _, matching_count = await store.student_page(
                query,
                0,
                0,
                0,
                50,
            )
            samples.append(time.perf_counter() - started)
            if matching_count != 1 or rows[0]["id"] != student_id:
                raise RuntimeError(
                    "La búsqueda de curso no devolvió al estudiante esperado."
                )
        return {
            "courses": size,
            "course_search_median_ms": median_milliseconds(samples),
        }
    finally:
        await store.dispose()


def benchmark_package(root: Path) -> dict[str, Any]:
    manifest = build_manifest(PACKAGE_STUDENT_COUNT)
    package_path = root / "limit.edutrack"

    write_package(package_path, manifest)
    imported_manifest = read_package(package_path)
    if len(imported_manifest["students"]) != PACKAGE_STUDENT_COUNT:
        raise RuntimeError("La lectura del paquete no conservó todos los estudiantes.")

    export_samples = []
    import_samples = []
    for _ in range(ITERATIONS):
        started = time.perf_counter()
        write_package(package_path, manifest)
        export_samples.append(time.perf_counter() - started)

        started = time.perf_counter()
        imported_manifest = read_package(package_path)
        import_samples.append(time.perf_counter() - started)
        if len(imported_manifest["students"]) != PACKAGE_STUDENT_COUNT:
            raise RuntimeError(
                "La lectura del paquete no conservó todos los estudiantes."
            )

    return {
        "students": PACKAGE_STUDENT_COUNT,
        "package_bytes": package_path.stat().st_size,
        "export_median_ms": median_milliseconds(export_samples),
        "import_median_ms": median_milliseconds(import_samples),
    }


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="edutrack-benchmark-") as directory:
        root = Path(directory)
        configure_logging("WARNING", root / "benchmark.jsonl")
        datasets = [
            await benchmark_dataset(size, root) for size in DATASET_SIZES
        ]
        course_search_datasets = [
            await benchmark_course_search(size, root)
            for size in DATASET_SIZES
        ]
        package = benchmark_package(root)

    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "iterations_per_median": ITERATIONS,
                "datasets": datasets,
                "course_search_datasets": course_search_datasets,
                "package_limit_case": package,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
