import pytest

from pokemon_to_linux import APP_NAME
from pokemon_to_linux.config import AppPaths

pytestmark = pytest.mark.integration


@pytest.fixture
def window(qapp, tmp_path):
    from pokemon_to_linux.ui.main_window import MainWindow

    paths = AppPaths.from_environment(env={}, home=tmp_path)
    win = MainWindow(paths, log_file=str(tmp_path / "app.log"))
    yield win
    win.close()
    win.deleteLater()


def test_window_title_contains_app_name(window):
    assert APP_NAME in window.windowTitle()


def test_navigation_has_one_page_per_entry(window):
    assert window.nav.count() == window.pages.count() == 3
    assert window.pages.currentIndex() == 0


def test_navigation_switches_pages(window):
    window.nav.setCurrentRow(2)
    assert window.pages.currentIndex() == 2

    window.nav.setCurrentRow(1)
    assert window.pages.currentIndex() == 1


def test_window_shows_without_errors(window, qapp):
    window.show()
    qapp.processEvents()
    assert window.isVisible()
