"""银行风险运营工作台壳层与共享分页的静态契约测试。"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BASE_HTML = ROOT / "templates" / "base.html"
APP_CSS = ROOT / "static" / "app.css"


@pytest.fixture(scope="module")
def base_html() -> str:
    return BASE_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_css() -> str:
    return APP_CSS.read_text(encoding="utf-8")


class TestBaseLayout:
    """锁住重设计后的固定导航、内容避让和移动抽屉行为。"""

    def test_shared_stylesheet_is_loaded(self, base_html):
        assert '/static/app.css?v=' in base_html

    def test_sidebar_position_fixed_and_scoped_width(self, app_css):
        assert "--sidebar-width: 248px" in app_css
        sidebar = app_css.split(".app-sidebar {", 1)[1].split("}", 1)[0]
        assert "position: fixed" in sidebar
        assert "width: var(--sidebar-width)" in sidebar

    def test_sidebar_navigation_can_scroll(self, app_css):
        nav = app_css.split(".app-nav {", 1)[1].split("}", 1)[0]
        assert "overflow-y: auto" in nav

    def test_main_content_avoids_sidebar(self, app_css):
        main = app_css.split(".app-main {", 1)[1].split("}", 1)[0]
        assert "min-height: 100vh" in main
        assert "margin-left: var(--sidebar-width)" in main

    def test_responsive_mobile_drawer(self, app_css, base_html):
        assert "@media (max-width: 991.98px)" in app_css
        mobile = app_css.split("@media (max-width: 991.98px)", 1)[1]
        assert ".app-sidebar.is-open" in mobile
        assert "transform: translateX(0)" in mobile
        assert ".app-main { margin-left: 0" in mobile
        assert 'id="menu-button"' in base_html
        assert "aria-expanded" in base_html
        assert "event.key === 'Escape'" in base_html

    def test_design_tokens_are_defined(self, app_css):
        for token, value in [
            ("--brand-900", "#0B1F3A"),
            ("--brand-700", "#18518A"),
            ("--canvas", "#F4F7FB"),
            ("--success", "#137A55"),
            ("--danger", "#B42318"),
        ]:
            assert f"{token}: {value}" in app_css

    def test_accessibility_basics(self, base_html, app_css):
        assert 'class="skip-link"' in base_html
        assert 'aria-label="主导航"' in base_html
        assert ":focus-visible" in app_css
        assert "min-height: 44px" in app_css

    def test_pagination_bottom_sticky_and_visible(self, app_css):
        pagination = app_css.split(".pagination-bottom {", 1)[1].split("}", 1)[0]
        assert "position: sticky" in pagination
        assert "bottom: 0" in pagination
        page_link = app_css.split(".pagination-bottom .page-link {", 1)[1].split("}", 1)[0]
        assert "min-width: 36px" in page_link
        assert "color:" in page_link

    def test_all_list_pages_use_shared_pagination(self):
        pages = [
            ("cases.html", "loadCases"),
            ("assessments.html", "loadAssessments"),
            ("rules.html", "loadRules"),
            ("blacklist.html", "loadList"),
        ]
        for filename, load_fn in pages:
            html = (ROOT / "templates" / filename).read_text(encoding="utf-8")
            assert 'class="pagination-bottom"' in html
            assert 'id="pagination"' in html
            assert "buildPaginationHtml(" in html
            assert f"'{load_fn}'" in html

    def test_sidebar_html_structure_and_bank_order(self, base_html):
        assert base_html.count('class="nav-link') == 7
        positions = [base_html.index(f'href="{path}"') for path in [
            "/", "/risk-check", "/rules", "/blacklist", "/cases", "/assessments", "/chat"
        ]]
        assert positions == sorted(positions)
        assert "银行风险运营工作台" in base_html
        assert "教学 · 虚构数据" in base_html

    def test_main_content_semantics(self, base_html):
        assert '<main class="app-main" id="main-content"' in base_html
        assert "{% block content %}" in base_html
