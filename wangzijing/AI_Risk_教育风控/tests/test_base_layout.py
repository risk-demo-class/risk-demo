"""新版浅色教育风控工作台的静态结构回归测试。"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BASE_HTML = ROOT / "templates" / "base.html"
DASHBOARD_HTML = ROOT / "templates" / "dashboard.html"


@pytest.fixture(scope="module")
def base_html() -> str:
    return BASE_HTML.read_text(encoding="utf-8")


class TestModernWorkspaceLayout:
    def test_reference_palette_is_present(self, base_html):
        """浅灰画布、白色表面和柠檬绿强调色必须保留。"""
        for token in ["--canvas:", "--workspace:", "--surface:", "--lime:"]:
            assert token in base_html
        assert "#c7f45a" in base_html.lower()

    def test_rounded_workspace_shell(self, base_html):
        css = re.search(r"\.app-shell\s*\{([^}]*)\}", base_html, re.DOTALL)
        assert css
        block = css.group(1)
        assert "display: flex" in block
        assert "border-radius: 30px" in block
        assert "overflow: hidden" in block

    def test_sidebar_is_light_flex_column(self, base_html):
        css = re.search(r"\.sidebar\s*\{([^}]*)\}", base_html, re.DOTALL)
        assert css
        block = css.group(1)
        assert "display: flex" in block
        assert "flex-direction: column" in block
        assert "background: var(--surface)" in block
        assert "overflow-y: auto" in block

    def test_active_navigation_uses_lime(self, base_html):
        css = re.search(r"\.sidebar \.nav-link\.active\s*\{([^}]*)\}", base_html, re.DOTALL)
        assert css
        assert "background: var(--lime)" in css.group(1)

    def test_page_scroll_is_independent(self, base_html):
        css = re.search(r"\.page-scroll\s*\{([^}]*)\}", base_html, re.DOTALL)
        assert css
        block = css.group(1)
        assert "overflow-y: auto" in block
        assert "flex: 1 1 auto" in block

    def test_mobile_navigation_becomes_horizontal(self, base_html):
        media = re.search(
            r"@media\s*\(max-width:\s*767\.98px\)\s*\{(.+?)\n\s*\}\n\s*</style>",
            base_html,
            re.DOTALL,
        )
        assert media
        css = media.group(1)
        assert re.search(r"\.sidebar\s*\{[^}]*width:\s*100%", css)
        assert re.search(r"\.sidebar \.nav\s*\{[^}]*flex-direction:\s*row", css)
        assert re.search(r"\.page-scroll\s*\{[^}]*overflow:\s*visible", css)

    def test_sidebar_uses_role_based_navigation(self, base_html):
        nav = re.search(r'<nav class="nav flex-column">(.*?)</nav>', base_html, re.DOTALL)
        assert nav
        html = nav.group(1)
        assert "current_user.role == 'ADMIN'" in html
        assert "{% else %}" in html
        for path in ["/dashboard", "/users", "/rules", "/cases", "/assessments", "/risk-check", "/blacklist"]:
            assert f'href="{path}"' in html
        assert 'href="/chat"' in html

    def test_topbar_and_operator_identity_exist(self, base_html):
        assert 'class="app-topbar"' in base_html
        assert "智慧教育风险管理" in base_html
        assert "风控管理员" in base_html
        assert "规则 + XGBoost 双轨引擎" in base_html

    def test_pagination_stays_visible_and_styled(self, base_html):
        block = re.search(r"\.pagination-bottom\s*\{([^}]*)\}", base_html, re.DOTALL)
        assert block
        css = block.group(1)
        assert "position: sticky" in css
        assert "bottom: -1px" in css
        assert ".pagination-bottom .active .page-link" in base_html

    def test_all_list_pages_keep_shared_pagination(self):
        pages = [
            ("cases.html", "loadCases"),
            ("assessments.html", "loadAssessments"),
            ("rules.html", "loadRules"),
            ("blacklist.html", "loadList"),
        ]
        for filename, load_function in pages:
            html = (ROOT / "templates" / filename).read_text(encoding="utf-8")
            assert 'class="pagination-bottom"' in html
            assert 'id="pagination"' in html
            assert "buildPaginationHtml(" in html
            assert f"'{load_function}'" in html

    def test_case_page_supports_small_demo_page_sizes(self):
        html = (ROOT / "templates" / "cases.html").read_text(encoding="utf-8")
        assert '<option value="5">5 条</option>' in html
        assert '<option value="10">10 条</option>' in html
        assert "const DEFAULT_PAGE_SIZE = '5'" in html
        assert "cases_pageSize_v2" in html

    def test_dashboard_uses_four_pastel_metric_cards(self):
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
        for css_class in ["metric-violet", "metric-blue", "metric-mint", "metric-peach"]:
            assert css_class in html
        assert html.count("metric-card") == 4

    def test_dashboard_keeps_live_api_and_chart(self):
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
        assert "/api/dashboard/overview" in html
        assert 'id="trendChart"' in html
        assert "规则 + XGBoost" in html
