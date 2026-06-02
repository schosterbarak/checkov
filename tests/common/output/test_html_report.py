"""Tests for :class:`checkov.common.output.html.HTML` and the HTML output
format wiring in :mod:`checkov.common.runners.runner_registry`.

The tests construct :class:`Report` and :class:`Record` objects directly to
keep execution fast and deterministic; they do not invoke any actual checkov
runners.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from typing import Any

import pytest

from checkov.common.bridgecrew.severities import BcSeverities, Severities
from checkov.common.models.enums import CheckResult
from checkov.common.output.html import HTML
from checkov.common.output.record import Record
from checkov.common.output.report import Report
from checkov.common.runners.runner_registry import OUTPUT_CHOICES, RunnerRegistry
from checkov.common.util.banner import banner
from checkov.runner_filter import RunnerFilter


# ---------------------------------------------------------------------------
# Module-level helpers.
# ---------------------------------------------------------------------------


def _make_record(
    *,
    check_id: str = "CKV_TEST_1",
    check_name: str = "test check",
    resource: str = "aws_x.y",
    file_path: str = "/iac/file.tf",
    file_line_range: list[int] | None = None,
    code_block: list[tuple[int, str]] | None = None,
    severity=None,
    guideline: str | None = None,
    result: CheckResult = CheckResult.PASSED,
    file_abs_path: str | None = None,
    check_class: str = "test_check_class",
    evaluations: dict[str, Any] | None = None,
    bc_check_id: str | None = None,
    caller_file_path: str | None = None,
    resource_address: str | None = None,
    description: str | None = None,
    short_description: str | None = None,
    details: list[str] | None = None,
) -> Record:
    """Build a :class:`Record` with sensible defaults; only overrides matter."""

    if file_line_range is None:
        file_line_range = [1, 3]
    if code_block is None:
        code_block = [(1, f'resource "{resource}" {{\n'), (2, "}\n")]
    if file_abs_path is None:
        file_abs_path = "/abs" + file_path

    record = Record(
        check_id=check_id,
        check_name=check_name,
        check_result={"result": result},
        code_block=code_block,
        file_path=file_path,
        file_line_range=file_line_range,
        resource=resource,
        evaluations=evaluations,
        check_class=check_class,
        file_abs_path=file_abs_path,
        bc_check_id=bc_check_id,
        severity=severity,
        caller_file_path=caller_file_path,
        resource_address=resource_address,
        description=description,
        short_description=short_description,
        details=details,
    )
    if guideline is not None:
        record.set_guideline(guideline)
    return record


def _make_report(
    *,
    check_type: str = "terraform",
    passed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    parsing_errors: list[str] | None = None,
) -> Report:
    report = Report(check_type)
    for i in range(passed):
        report.add_record(
            _make_record(
                check_id=f"CKV_{check_type.upper()}_PASS_{i}",
                check_name=f"{check_type} pass {i}",
                resource=f"{check_type}.pass_{i}",
                file_path=f"/iac/{check_type}/pass_{i}.tf",
                result=CheckResult.PASSED,
            )
        )
    for i in range(failed):
        report.add_record(
            _make_record(
                check_id=f"CKV_{check_type.upper()}_FAIL_{i}",
                check_name=f"{check_type} fail {i}",
                resource=f"{check_type}.fail_{i}",
                file_path=f"/iac/{check_type}/fail_{i}.tf",
                result=CheckResult.FAILED,
            )
        )
    for i in range(skipped):
        report.add_record(
            _make_record(
                check_id=f"CKV_{check_type.upper()}_SKIP_{i}",
                check_name=f"{check_type} skip {i}",
                resource=f"{check_type}.skip_{i}",
                file_path=f"/iac/{check_type}/skip_{i}.tf",
                result=CheckResult.SKIPPED,
            )
        )
    for err in parsing_errors or []:
        report.add_parsing_error(err)
    return report


class _ParseTracker(HTMLParser):
    """Trivial subclass that just records that parsing completed."""

    def __init__(self) -> None:
        super().__init__()
        self.tags_started: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags_started.append(tag)


def _parses_cleanly(html_str: str) -> _ParseTracker:
    parser = _ParseTracker()
    # ``HTMLParser`` raises on extremely malformed input only; tolerant by
    # design, so we drive it through ``feed`` + ``close`` and assert the
    # close completes.
    parser.feed(html_str)
    parser.close()
    return parser


def _build_namespace(**overrides: Any) -> argparse.Namespace:
    """Build the minimum config namespace that ``print_reports`` reads."""

    defaults: dict[str, Any] = dict(
        output=["html"],
        output_file_path=None,
        quiet=False,
        compact=False,
        output_bc_ids=False,
        soft_fail=False,
        soft_fail_on=[],
        hard_fail_on=[],
        use_enforcement_rules=False,
        summary_position="top",
        skip_resources_without_violations=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# 1. Structural validity tests.
# ---------------------------------------------------------------------------


def test_empty_reports_render_valid_html() -> None:
    html_out = HTML([]).get_html()

    assert isinstance(html_out, str)
    assert "<!DOCTYPE html>" in html_out
    assert "<html" in html_out
    assert "<head" in html_out
    assert "<body" in html_out
    assert "<title" in html_out
    assert "</html>" in html_out

    tracker = _parses_cleanly(html_out)
    assert "html" in tracker.tags_started
    assert "body" in tracker.tags_started


def test_single_report_renders_valid_html() -> None:
    report = _make_report(check_type="terraform", passed=1, failed=1)
    html_out = HTML([report]).get_html()

    _parses_cleanly(html_out)
    assert "CKV_TERRAFORM_PASS_0" in html_out
    assert "CKV_TERRAFORM_FAIL_0" in html_out


def test_required_sections_present() -> None:
    report = _make_report(check_type="terraform", passed=1, failed=1, skipped=1)
    html_out = HTML([report]).get_html()

    assert "Checkov" in html_out
    # Case-insensitive — template uses "Passed" / "passed" in different places.
    lowered = html_out.lower()
    assert "passed" in lowered
    assert "failed" in lowered
    assert "skipped" in lowered
    assert "total checks" in lowered


def test_html_has_doctype_and_charset() -> None:
    html_out = HTML([]).get_html()
    lowered = html_out.lower()
    assert "<!doctype html>" in lowered
    assert 'charset="utf-8"' in lowered or "charset='utf-8'" in lowered or 'charset=utf-8' in lowered


# ---------------------------------------------------------------------------
# 2. Data accuracy tests.
# ---------------------------------------------------------------------------


def test_check_ids_appear_in_output() -> None:
    record = _make_record(check_id="CKV_AWS_TEST_1", result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()
    assert "CKV_AWS_TEST_1" in html_out


def test_check_names_appear_in_output() -> None:
    record = _make_record(check_name="A very specific check name xyz123", result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()
    assert "A very specific check name xyz123" in html_out


def test_resource_names_appear_in_output() -> None:
    record = _make_record(resource="aws_s3_bucket.my_bucket_xyz", result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()
    assert "aws_s3_bucket.my_bucket_xyz" in html_out


def test_file_paths_appear_in_output() -> None:
    record = _make_record(file_path="/iac/specific_file_test_123.tf", result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()
    assert "/iac/specific_file_test_123.tf" in html_out


def test_code_block_appears_in_output() -> None:
    record = _make_record(
        result=CheckResult.FAILED,
        code_block=[
            (1, 'resource "aws_s3_bucket" "x" {\n'),
            (2, '  bucket = "y"\n'),
            (3, "}\n"),
        ],
    )
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    # Jinja2 autoescape will replace ``"`` with ``&#34;`` and ``<``/``>`` with
    # their entities; the substring without quotes still has to appear.
    assert "aws_s3_bucket" in html_out
    assert "bucket =" in html_out


def test_severity_badge_appears_in_output() -> None:
    record = _make_record(
        severity=Severities[BcSeverities.HIGH],
        result=CheckResult.FAILED,
    )
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()
    # The badge label is rendered lower-cased.
    assert "high" in html_out.lower()


def test_summary_counts_match_record_counts() -> None:
    report = _make_report(check_type="terraform", passed=3, failed=5, skipped=2)
    renderer = HTML([report])

    context = renderer._build_context()
    assert context["total_passed"] == 3
    assert context["total_failed"] == 5
    assert context["total_skipped"] == 2
    assert context["total_checks"] == 10

    html_out = renderer.get_html()
    assert "3" in html_out
    assert "5" in html_out
    assert "2" in html_out
    assert "10" in html_out


def test_total_checks_aggregates_across_reports() -> None:
    r1 = _make_report(check_type="terraform", passed=2, failed=1)
    r2 = _make_report(check_type="cloudformation", passed=1, failed=2, skipped=1)
    renderer = HTML([r1, r2])
    context = renderer._build_context()
    assert context["total_passed"] == 3
    assert context["total_failed"] == 3
    assert context["total_skipped"] == 1
    assert context["total_checks"] == 7


# ---------------------------------------------------------------------------
# 3. Edge case tests.
# ---------------------------------------------------------------------------


def test_empty_report_produces_zero_counts() -> None:
    renderer = HTML([])
    context = renderer._build_context()
    assert context["total_checks"] == 0
    assert context["total_passed"] == 0
    assert context["total_failed"] == 0
    assert context["total_skipped"] == 0

    html_out = renderer.get_html()
    assert "0" in html_out


def test_only_passed_records() -> None:
    report = _make_report(check_type="terraform", passed=3)
    html_out = HTML([report]).get_html()
    _parses_cleanly(html_out)
    assert "CKV_TERRAFORM_PASS_0" in html_out


def test_only_failed_records() -> None:
    report = _make_report(check_type="terraform", failed=2)
    html_out = HTML([report]).get_html()
    _parses_cleanly(html_out)
    assert "CKV_TERRAFORM_FAIL_0" in html_out
    # Failed-row details accordion is emitted.
    assert "details-row" in html_out


def test_only_skipped_records() -> None:
    report = _make_report(check_type="terraform", skipped=2)
    html_out = HTML([report]).get_html()
    _parses_cleanly(html_out)
    assert "CKV_TERRAFORM_SKIP_0" in html_out


def test_parsing_errors_section_rendered() -> None:
    report = _make_report(
        check_type="terraform",
        parsing_errors=["/bad/file1.tf", "/bad/file2.tf"],
    )
    html_out = HTML([report]).get_html()
    assert "Parsing Errors" in html_out
    assert "/bad/file1.tf" in html_out
    assert "/bad/file2.tf" in html_out


def test_html_escaping_for_xss_resource_name() -> None:
    record = _make_record(resource="<script>alert(1)</script>", result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out


def test_html_escaping_for_xss_file_path() -> None:
    record = _make_record(
        file_path="<img src=x onerror=alert(1)>",
        file_abs_path="/abs/foo.tf",
        result=CheckResult.FAILED,
    )
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    assert "<img src=x onerror=alert(1)>" not in html_out
    assert "&lt;img" in html_out
    assert "&gt;" in html_out


def test_html_escaping_for_xss_code_block() -> None:
    record = _make_record(
        result=CheckResult.FAILED,
        code_block=[(1, "<script>alert('xss')</script>\n")],
    )
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    assert "<script>alert('xss')</script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_html_escaping_for_check_name() -> None:
    record = _make_record(check_name="<b>injected</b>", result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    assert "<b>injected</b>" not in html_out
    assert "&lt;b&gt;injected&lt;/b&gt;" in html_out


def test_javascript_uri_in_guideline_is_suppressed() -> None:
    """Regression: ``javascript:`` URIs in ``guideline`` must not reach the rendered href.

    Jinja2 autoescape protects against HTML-character injection but does NOT
    sanitize protocol-level injection in ``href`` attributes. ``record.guideline``
    is attacker-influenceable via Bridgecrew custom policies. ``_safe_url`` in
    ``html.py`` must drop non-``http(s)`` schemes so the template's
    ``{% if record.guideline %}`` guard suppresses the link entirely.
    """

    record = _make_record(
        guideline="javascript:alert(document.cookie)",
        result=CheckResult.FAILED,
    )
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    # The raw ``javascript:`` URI must never appear in the rendered output.
    assert "javascript:" not in html_out
    # Because the guideline was suppressed, the "View guideline" link is gone.
    assert "View guideline" not in html_out


def test_data_uri_in_guideline_is_suppressed() -> None:
    """Same defense as ``test_javascript_uri_in_guideline_is_suppressed`` for ``data:`` URIs."""

    record = _make_record(
        guideline="data:text/html,<script>alert(1)</script>",
        result=CheckResult.FAILED,
    )
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    assert "data:text/html" not in html_out
    assert "View guideline" not in html_out


def test_https_guideline_is_preserved() -> None:
    """Sanity check: an ``https://`` guideline URL is rendered as a clickable link."""

    record = _make_record(
        guideline="https://docs.checkov.io/some-page",
        result=CheckResult.FAILED,
    )
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    assert "https://docs.checkov.io/some-page" in html_out
    assert "View guideline" in html_out


def test_html_escaping_attribute_breakout_in_check_name() -> None:
    """Regression: double-quote attribute breakout payload must be escaped in attribute contexts.

    The ``rule-enable-jinja2-autoescape-always`` rule mandates regression
    coverage for the ``" onerror="x`` attribute-injection vector in addition to
    element-level ``<script>`` injection.
    """

    payload = '" onerror="alert(1)'
    record = _make_record(check_name=payload, result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    # The raw double-quote attribute breakout payload must not appear verbatim.
    assert payload not in html_out
    assert 'onerror="alert(1)' not in html_out
    # The double quote must be HTML-escaped (Jinja2 emits ``&#34;``).
    assert "&#34;" in html_out or "&quot;" in html_out


def test_results_table_headers_are_sortable() -> None:
    """Regression for PROJECT.md +++5+++: each results-table column must be sortable.

    The contract requires the table to be "sortable by columns via minimal
    inline JavaScript". This test verifies the rendered HTML exposes
    ``data-sort-key`` on every results column header and includes a
    ``sortTableBy`` function in the inline JS so the click handler can sort
    rows in place.
    """

    report = _make_report(check_type="terraform", passed=1, failed=1, skipped=1)
    html_out = HTML([report]).get_html()

    # All six columns must declare a sort key.
    for sort_key in ("status", "check-id", "check-name", "resource", "file", "severity"):
        assert f'data-sort-key="{sort_key}"' in html_out, (
            f"Results table header missing data-sort-key={sort_key}"
        )

    # The inline JS must include the sort function and a click handler that
    # binds it to header clicks.
    assert "sortTableBy" in html_out
    assert "onHeaderClick" in html_out
    # The header must be keyboard-accessible (tabindex set in init()).
    assert 'setAttribute("tabindex"' in html_out


def test_multiple_reports_with_different_check_types() -> None:
    r1 = _make_report(check_type="terraform", passed=1)
    r2 = _make_report(check_type="kubernetes", failed=1)
    r3 = _make_report(check_type="cloudformation", skipped=1)
    html_out = HTML([r1, r2, r3]).get_html()

    assert "terraform" in html_out
    assert "kubernetes" in html_out
    assert "cloudformation" in html_out


def test_record_with_no_severity_renders() -> None:
    record = _make_record(severity=None, result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()
    _parses_cleanly(html_out)
    assert "CKV_TEST_1" in html_out


def test_record_with_no_guideline_renders() -> None:
    record = _make_record(guideline=None, result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()
    _parses_cleanly(html_out)
    # Guideline link only rendered when guideline is truthy.
    assert "View guideline" not in html_out


def test_record_with_single_line_range() -> None:
    record = _make_record(file_line_range=[7, 7], result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)
    html_out = HTML([report]).get_html()

    # The single-line range renders as "7" (not "7-7"). We tolerate other
    # "7" occurrences in the document but explicitly assert "7-7" is absent.
    assert ":7" in html_out
    assert "7-7" not in html_out


def test_record_with_unset_line_range() -> None:
    record = _make_record(file_line_range=[], result=CheckResult.FAILED)
    report = Report("terraform")
    report.add_record(record)

    # Should render without raising.
    html_out = HTML([report]).get_html()
    _parses_cleanly(html_out)


# ---------------------------------------------------------------------------
# 4. Internal context-builder tests.
# ---------------------------------------------------------------------------


def test_record_view_projection_shape() -> None:
    record = _make_record(result=CheckResult.FAILED)
    view = HTML([])._record_view(record, "failed")

    expected_keys = {
        "status", "check_id", "bc_check_id", "check_name", "check_class",
        "resource", "file_path", "file_line_range_str", "file_line_start",
        "file_line_end", "severity", "code_block", "code_block_lines",
        "guideline", "evaluations", "description", "short_description",
        "details", "caller_file_path", "resource_address",
    }
    assert expected_keys.issubset(set(view.keys()))
    assert view["status"] == "failed"


def test_record_view_severity_normalization() -> None:
    record = _make_record(severity=Severities[BcSeverities.CRITICAL])
    view = HTML([])._record_view(record, "failed")
    assert view["severity"] == "critical"


def test_record_view_no_severity_returns_empty_string() -> None:
    record = _make_record(severity=None)
    view = HTML([])._record_view(record, "passed")
    assert view["severity"] == ""


def test_record_view_line_range_single() -> None:
    record = _make_record(file_line_range=[5, 5])
    view = HTML([])._record_view(record, "passed")
    assert view["file_line_range_str"] == "5"


def test_record_view_line_range_range() -> None:
    record = _make_record(file_line_range=[5, 10])
    view = HTML([])._record_view(record, "passed")
    assert view["file_line_range_str"] == "5-10"


def test_record_view_line_range_empty() -> None:
    record = _make_record(file_line_range=[])
    view = HTML([])._record_view(record, "passed")
    assert view["file_line_range_str"] == ""


def test_record_view_code_block_joined() -> None:
    record = _make_record(code_block=[(1, "a\n"), (2, "b\n")])
    view = HTML([])._record_view(record, "passed")
    assert view["code_block"] == "a\nb\n"


def test_report_view_counts_match() -> None:
    report = _make_report(check_type="terraform", passed=2, failed=3, skipped=1)
    view = HTML([])._report_view(report)
    assert view["passed_count"] == 2
    assert view["failed_count"] == 3
    assert view["skipped_count"] == 1
    assert len(view["records"]) == 6


def test_report_view_records_ordering() -> None:
    report = _make_report(check_type="terraform", passed=2, failed=3, skipped=1)
    view = HTML([])._report_view(report)
    statuses = [record["status"] for record in view["records"]]

    # Expected order: all "failed" before any "passed" before any "skipped".
    first_passed = statuses.index("passed")
    first_skipped = statuses.index("skipped")
    last_failed = max(i for i, s in enumerate(statuses) if s == "failed")
    last_passed = max(i for i, s in enumerate(statuses) if s == "passed")
    assert last_failed < first_passed
    assert last_passed < first_skipped


def test_build_context_aggregates_totals() -> None:
    r1 = _make_report(check_type="terraform", passed=2, failed=1)
    r2 = _make_report(check_type="cloudformation", passed=3, failed=4, skipped=2)
    context = HTML([r1, r2])._build_context()

    assert context["total_passed"] == 5
    assert context["total_failed"] == 5
    assert context["total_skipped"] == 2
    assert context["total_checks"] == 12
    assert len(context["reports"]) == 2


# ---------------------------------------------------------------------------
# 5. Registry integration tests.
# ---------------------------------------------------------------------------


def test_html_in_output_choices() -> None:
    assert "html" in OUTPUT_CHOICES


def test_print_reports_dispatches_html_to_data_outputs(capsys: pytest.CaptureFixture[str]) -> None:
    report = _make_report(check_type="terraform", failed=1)
    runner_filter = RunnerFilter(framework=None, checks=None, skip_checks=None)
    registry = RunnerRegistry(banner, runner_filter)

    config = _build_namespace(output=["html"])

    exit_code = registry.print_reports(scan_reports=[report], config=config)
    captured = capsys.readouterr()

    assert exit_code in (0, 1)
    assert "<!DOCTYPE html>" in captured.out


def test_file_names_includes_html(tmp_path) -> None:
    """Drive ``print_reports`` with an output file path and verify the
    ``html`` entry of the internal ``file_names`` dict is honoured."""

    report = _make_report(check_type="terraform", failed=1)
    runner_filter = RunnerFilter(framework=None, checks=None, skip_checks=None)
    registry = RunnerRegistry(banner, runner_filter)

    config = _build_namespace(output=["html"], output_file_path=str(tmp_path))
    registry.print_reports(scan_reports=[report], config=config)

    expected = tmp_path / "results_report.html"
    assert expected.exists()


def test_html_with_output_file_path_writes_file(tmp_path) -> None:
    report = _make_report(check_type="terraform", failed=1)
    runner_filter = RunnerFilter(framework=None, checks=None, skip_checks=None)
    registry = RunnerRegistry(banner, runner_filter)

    config = _build_namespace(output=["html"], output_file_path=str(tmp_path))
    registry.print_reports(scan_reports=[report], config=config)

    written = (tmp_path / "results_report.html")
    assert written.exists()
    content = written.read_text()
    assert "<!DOCTYPE html>" in content


def test_html_with_cli_multiformat(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _make_report(check_type="terraform", failed=1, passed=1)
    runner_filter = RunnerFilter(framework=None, checks=None, skip_checks=None)
    registry = RunnerRegistry(banner, runner_filter)

    config = _build_namespace(output=["cli", "html"], output_file_path=str(tmp_path))
    # Should not raise.
    registry.print_reports(scan_reports=[report], config=config)

    # Both output files should exist when output_file_path is set.
    assert (tmp_path / "results_report.html").exists()


# ---------------------------------------------------------------------------
# 6. Fixture-driven test (uses conftest.html_multi_check_type_reports).
# ---------------------------------------------------------------------------


def test_multi_check_type_fixture_renders(html_multi_check_type_reports: list[Report]) -> None:
    renderer = HTML(html_multi_check_type_reports)
    context = renderer._build_context()

    # 2 passed + 1 passed = 3, 2 failed + 1 failed = 3, 1 skipped, 1 parsing
    # error.
    assert context["total_passed"] == 3
    assert context["total_failed"] == 3
    assert context["total_skipped"] == 1
    assert context["total_parsing_errors"] == 1

    html_out = renderer.get_html()
    _parses_cleanly(html_out)
    assert "terraform" in html_out
    assert "cloudformation" in html_out
    assert "kubernetes" in html_out
    assert "/iac/k8s/broken.yaml" in html_out
