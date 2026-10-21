"""Pruebas de humo de interfaz con Playwright contra un EduTrack ya levantado.

Variables de entorno: E2E_URL (por defecto http://localhost:8080), E2E_USER y E2E_PASSWORD
(un usuario con permisos de llamadas y una sede asignada). Se omiten si faltan las credenciales.
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("E2E_URL", "http://localhost:8080").rstrip("/")
USER = os.environ.get("E2E_USER")
PASSWORD = os.environ.get("E2E_PASSWORD")

needs_login = pytest.mark.skipif(
    not (USER and PASSWORD), reason="Defina E2E_USER y E2E_PASSWORD para ejecutar esta prueba"
)


@pytest.fixture
def logged_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/cuentas/ingresar/")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASSWORD)
    page.click("form button")
    page.wait_for_load_state("networkidle")
    assert "/ingresar" not in page.url, "No se pudo iniciar sesión con las credenciales E2E"
    chooser = page.locator("main select")
    page.goto(f"{BASE_URL}/llamadas/asignacion/")
    if chooser.count() and page.get_by_role("button", name="Continuar").count():
        chooser.first.select_option(index=1)
        page.get_by_role("button", name="Continuar").click()
        page.wait_for_load_state("networkidle")
    return page


def test_health_endpoint(page: Page):
    response = page.request.get(f"{BASE_URL}/salud/")
    assert response.ok
    assert response.json() == {"status": "ok"}


@needs_login
def test_search_shortcut_focuses_global_search(logged_page: Page):
    logged_page.goto(f"{BASE_URL}/")
    logged_page.keyboard.press("/")
    expect(logged_page.locator(".header-search input[name=q]")).to_be_focused()


@needs_login
def test_call_list_filters(logged_page: Page):
    logged_page.goto(f"{BASE_URL}/llamadas/asignacion/")
    expect(logged_page.locator("select[name=orden]")).to_be_visible()


@needs_login
def test_table_headers_are_sticky(logged_page: Page):
    logged_page.goto(f"{BASE_URL}/llamadas/asignacion/")
    header = logged_page.locator("main .table-wrap thead th").first
    expect(header).to_have_css("position", re.compile("sticky"))


@needs_login
def test_sidebar_navigation_keeps_the_layout(logged_page: Page):
    logged_page.goto(f"{BASE_URL}/")
    link = logged_page.locator("#slide-out a[href*='/llamadas/']").first
    if link.count():
        link.click()
        logged_page.wait_for_load_state("networkidle")
        expect(logged_page.locator("main")).to_be_visible()
