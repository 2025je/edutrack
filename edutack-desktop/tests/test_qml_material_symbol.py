from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QFont, QFontDatabase, QTextLayout
from PySide6.QtQuick import QQuickView
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest


@pytest.fixture(scope="module")
def material_symbols_font(gui_application):
    qml_directory = (
        Path(__file__).parents[1]
        / "src"
        / "edutrack_desktop"
        / "presentation"
        / "qml"
    )
    font_path = qml_directory / "fonts" / "MaterialSymbolsOutlined.ttf"
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    assert font_id >= 0
    assert "Material Symbols Outlined" in QFontDatabase.applicationFontFamilies(
        font_id
    )
    return qml_directory


def _glyph_count(symbol_name):
    layout = QTextLayout(symbol_name, QFont("Material Symbols Outlined", 36))
    layout.beginLayout()
    line = layout.createLine()
    line.setLineWidth(1000)
    layout.endLayout()
    return sum(len(run.glyphIndexes()) for run in layout.glyphRuns())


@pytest.mark.parametrize(
    "symbol_name",
    [
        "assignment",
        "groups",
        "menu_book",
        "event",
        "folder_open",
        "add",
        "chevron_right",
        "ios_share",
        "light_mode",
        "dark_mode",
        "close",
        "sync",
        "backup",
    ],
)
def test_material_symbol_font_contains_ligatures(
    material_symbols_font, symbol_name
):
    assert _glyph_count(symbol_name) == 1


@pytest.mark.parametrize(
    "symbol_name", ["sync", "backup", "light_mode", "dark_mode"]
)
def test_material_symbol_renders_font_ligature(
    gui_application, material_symbols_font, symbol_name
):
    qml_url = QUrl.fromLocalFile(
        str(material_symbols_font / "components" / "MaterialSymbol.qml")
    )
    view = QQuickView()
    view.setColor(QColor("black"))
    component = QQmlComponent(view.engine(), qml_url)
    root = component.createWithInitialProperties(
        {
            "symbolName": symbol_name,
            "symbolColor": "red",
            "symbolSize": 36,
        }
    )
    assert root is not None, [error.toString() for error in component.errors()]

    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setContent(qml_url, component, root)
    view.resize(36, 36)
    view.show()
    gui_application.processEvents()
    QTest.qWait(50)

    assert root.property("text") == symbol_name
    assert root.property("font").family() == "Material Symbols Outlined"
    image = view.grabWindow()
    assert any(
        image.pixelColor(x, y).red() > 200
        and image.pixelColor(x, y).green() < 20
        for y in range(image.height())
        for x in range(image.width())
    )

    view.close()
