import asyncio

import pytest

from benchmark_data import (
    build_course_search_manifest,
    build_enrollment_search_manifest,
    build_manifest,
)
from edutrack_desktop.domain.record_service import RecordMutation
from edutrack_desktop.infrastructure.store import LocalStore
from edutrack_desktop.infrastructure.transfer import read_package, write_package

DATASET_SIZES = (1_000, 10_000, 50_000)
PACKAGE_STUDENT_COUNT = 2_000
BENCHMARK_ROUNDS = 20


@pytest.fixture(scope="module")
def benchmark_loop():
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(
    scope="module",
    params=DATASET_SIZES,
    ids=lambda size: f"{size}-students",
)
def student_store(request, benchmark_loop, tmp_path_factory):
    size = request.param
    manifest = build_manifest(size)
    store = LocalStore(
        tmp_path_factory.mktemp(f"student-search-{size}") / "workspace.sqlite3"
    )
    try:
        benchmark_loop.run_until_complete(store.save(manifest))
        yield size, manifest, store
    finally:
        benchmark_loop.run_until_complete(store.dispose())


@pytest.fixture(
    scope="module",
    params=DATASET_SIZES,
    ids=lambda size: f"{size}-courses",
)
def course_store(request, benchmark_loop, tmp_path_factory):
    size = request.param
    manifest = build_course_search_manifest(size)
    store = LocalStore(
        tmp_path_factory.mktemp(f"course-search-{size}") / "workspace.sqlite3"
    )
    try:
        benchmark_loop.run_until_complete(store.save(manifest))
        yield size, manifest, store
    finally:
        benchmark_loop.run_until_complete(store.dispose())


@pytest.fixture(
    scope="module",
    params=DATASET_SIZES,
    ids=lambda size: f"{size}-enrollments",
)
def enrollment_store(request, benchmark_loop, tmp_path_factory):
    size = request.param
    manifest = build_enrollment_search_manifest(size)
    store = LocalStore(
        tmp_path_factory.mktemp(f"enrollment-search-{size}") / "workspace.sqlite3"
    )
    try:
        benchmark_loop.run_until_complete(store.save(manifest))
        yield size, store
    finally:
        benchmark_loop.run_until_complete(store.dispose())


@pytest.mark.performance
@pytest.mark.benchmark(group="student-search")
def test_benchmark_student_search(benchmark, benchmark_loop, student_store):
    size, _, store = student_store
    query = f"APELLIDO{size:05d}"

    def search():
        return benchmark_loop.run_until_complete(store.search_students(query))

    assert len(search()) == 1
    benchmark.pedantic(
        search,
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="student-page-search")
def test_benchmark_student_page_search(benchmark, benchmark_loop, student_store):
    size, _, store = student_store

    def search_page():
        return benchmark_loop.run_until_complete(
            store.student_page(f"APELLIDO{size:05d}", 0, 0, 0, 50)
        )

    rows, total_count, matching_count = search_page()
    assert len(rows) == matching_count == 1
    assert total_count == size
    benchmark.pedantic(
        search_page,
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="incremental-save")
def test_benchmark_incremental_student_save(benchmark, benchmark_loop, student_store):
    size, manifest, store = student_store
    student = manifest["students"][-1]
    student["first_name"] = "ACTUALIZADO"
    mutations = {"students": [RecordMutation(size - 1, student)]}

    def save_record():
        benchmark_loop.run_until_complete(store.save_records(manifest, mutations))

    save_record()
    benchmark.pedantic(
        save_record,
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="course-search")
def test_benchmark_course_search(benchmark, benchmark_loop, course_store):
    size, manifest, store = course_store
    student_id = manifest["students"][0]["id"]
    query = f"CURSO {size:05d}"

    def search_course():
        return benchmark_loop.run_until_complete(store.student_page(query, 0, 0, 0, 50))

    rows, _, matching_count = search_course()
    assert matching_count == 1
    assert rows[0]["id"] == student_id
    benchmark.pedantic(
        search_course,
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="course-list-page")
def test_benchmark_course_list_page_search(benchmark, benchmark_loop, course_store):
    size, _, store = course_store
    query = f"CURSO {size:05d}"

    def search_course_page():
        return benchmark_loop.run_until_complete(store.course_page(query, 0, 50))

    rows, total_count, matching_count = search_course_page()
    assert total_count == size
    assert matching_count == 1
    assert len(rows) == 1
    assert rows[0]["id"] == size
    benchmark.pedantic(
        search_course_page,
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="enrollment-list-page")
def test_benchmark_enrollment_list_page_search(
    benchmark,
    benchmark_loop,
    enrollment_store,
):
    size, store = enrollment_store

    def search_enrollment_page():
        return benchmark_loop.run_until_complete(
            store.enrollment_page("curso benchmark", 0, 0, 0, 50)
        )

    rows, total_count, matching_count = search_enrollment_page()
    assert total_count == matching_count == size
    assert len(rows) == 50
    assert rows[0]["pending_student"] is False
    assert rows[0]["pending_course"] is False
    benchmark.pedantic(
        search_enrollment_page,
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="package-export")
def test_benchmark_package_export(benchmark, tmp_path):
    manifest = build_manifest(PACKAGE_STUDENT_COUNT)
    package_path = tmp_path / "benchmark.edutrack"
    write_package(package_path, manifest)
    assert len(read_package(package_path)["students"]) == PACKAGE_STUDENT_COUNT

    benchmark.pedantic(
        lambda: write_package(package_path, manifest),
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="package-import")
def test_benchmark_package_import(benchmark, tmp_path):
    manifest = build_manifest(PACKAGE_STUDENT_COUNT)
    package_path = tmp_path / "benchmark.edutrack"
    write_package(package_path, manifest)
    assert len(read_package(package_path)["students"]) == PACKAGE_STUDENT_COUNT

    benchmark.pedantic(
        lambda: read_package(package_path),
        rounds=BENCHMARK_ROUNDS,
        iterations=1,
        warmup_rounds=3,
    )
