from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, PackageLoader, TemplateNotFound, select_autoescape

from checkov.version import version

if TYPE_CHECKING:
    from checkov.common.output.record import Record
    from checkov.common.output.report import Report


# Constants for the HTML report metadata that should be exposed to the template.
_TOOL_NAME = "Checkov"
_TOOL_URL = "https://www.checkov.io/"
_DOCS_URL = "https://www.checkov.io/2.Basics/Installing%20Checkov.html"
_TEMPLATE_NAME = "html_report.jinja2"


class HTML:
    """Render a list of :class:`Report` objects as a self-contained HTML document.

    Mirrors the shape of :class:`checkov.common.output.sarif.Sarif` and
    :class:`checkov.common.output.gitlab_sast.GitLabSast`: takes ``list[Report]``
    in ``__init__`` and exposes :meth:`get_html` which returns the rendered HTML
    string.

    Rendering uses a Jinja2 :class:`~jinja2.Environment` with the ``checkov``
    package's template loader. Autoescape is enabled to defend against
    untrusted scan data being interpreted as HTML; callers and templates MUST
    NOT use the ``|safe`` filter on user-controlled fields.

    Record objects are projected into a normalized dict view (see
    :meth:`_record_view`) so the template is insulated from changes in the
    :class:`Record` class itself. The same approach is taken for reports (see
    :meth:`_report_view`).
    """

    def __init__(self, reports: list[Report]) -> None:
        self.reports = reports

        # Build the Jinja2 environment up front so any configuration errors
        # surface during construction rather than at render time. ``autoescape``
        # is enabled for ``html`` / ``jinja2`` file extensions which covers the
        # template we ship. ``keep_trailing_newline`` produces a cleaner final
        # newline in the rendered output.
        self.env = Environment(
            loader=PackageLoader("checkov.common.output", "templates"),
            autoescape=select_autoescape(["html", "jinja2"]),
            keep_trailing_newline=True,
        )

    def get_html(self) -> str:
        """Render the HTML report and return it as a string.

        NOTE: This requires the template ``html_report.jinja2`` to exist in
        the ``checkov.common.output.templates`` package. That template is
        created in a sibling task; if it is missing, this method will raise
        :class:`jinja2.TemplateNotFound`. The full code path is implemented
        regardless so that once the template lands, this method works without
        further changes.
        """

        try:
            template = self.env.get_template(_TEMPLATE_NAME)
        except TemplateNotFound:
            # Re-raise to make the cause obvious for callers; the template is
            # expected to ship alongside this module.
            raise

        context = self._build_context()
        return template.render(**context)

    # ------------------------------------------------------------------
    # Context builders (kept as internal helpers to ease unit testing).
    # ------------------------------------------------------------------

    def _build_context(self) -> dict[str, Any]:
        """Compute the full render context for the template.

        Returns a plain ``dict`` so tests can inspect the projection without
        actually rendering a template.
        """

        report_views = [self._report_view(report) for report in self.reports]

        total_passed = sum(rv["passed_count"] for rv in report_views)
        total_failed = sum(rv["failed_count"] for rv in report_views)
        total_skipped = sum(rv["skipped_count"] for rv in report_views)
        total_parsing_errors = sum(len(rv["parsing_errors"]) for rv in report_views)
        total_resources = sum(rv["resource_count"] for rv in report_views)
        total_checks = total_passed + total_failed + total_skipped

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "reports": report_views,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "total_parsing_errors": total_parsing_errors,
            "total_resources": total_resources,
            "total_checks": total_checks,
            "checkov_version": version,
            "generated_at": generated_at,
            "tool_name": _TOOL_NAME,
            "tool_url": _TOOL_URL,
            "docs_url": _DOCS_URL,
        }

    def _report_view(self, report: Report) -> dict[str, Any]:
        """Project a :class:`Report` into the dict view consumed by the template."""

        passed = [self._record_view(record, "passed") for record in report.passed_checks]
        failed = [self._record_view(record, "failed") for record in report.failed_checks]
        skipped = [self._record_view(record, "skipped") for record in report.skipped_checks]

        return {
            "check_type": report.check_type,
            "passed_count": len(report.passed_checks),
            "failed_count": len(report.failed_checks),
            "skipped_count": len(report.skipped_checks),
            "parsing_errors": list(report.parsing_errors),
            "resource_count": len(report.resources),
            # Failed first so the most actionable findings appear at the top
            # of any per-report listing in the template.
            "records": failed + passed + skipped,
        }

    def _record_view(self, record: Record, status: str) -> dict[str, Any]:
        """Project a :class:`Record` into the dict view consumed by the template.

        ``status`` is one of ``"passed"``, ``"failed"`` or ``"skipped"`` and is
        stamped onto the projection so the template doesn't need to know about
        :class:`checkov.common.models.enums.CheckResult`.
        """

        # Severity is a ``Severity`` dataclass-like object; only its ``.name``
        # attribute is required here. Normalize to lowercase to match the
        # convention used by ``sarif.py`` and ``gitlab_sast.py``.
        severity = ""
        if record.severity is not None:
            severity = record.severity.name.lower()

        # ``record.file_line_range`` is conventionally ``[start, end]`` but
        # defensive parsing keeps the projection robust for malformed records.
        file_line_start: int | None = None
        file_line_end: int | None = None
        file_line_range_str = ""

        line_range = getattr(record, "file_line_range", None) or []
        if len(line_range) >= 1:
            try:
                file_line_start = int(line_range[0])
            except (TypeError, ValueError):
                file_line_start = None
        if len(line_range) >= 2:
            try:
                file_line_end = int(line_range[1])
            except (TypeError, ValueError):
                file_line_end = None

        if file_line_start is not None and file_line_end is not None:
            if file_line_start == file_line_end:
                file_line_range_str = f"{file_line_start}"
            else:
                file_line_range_str = f"{file_line_start}-{file_line_end}"
        elif file_line_start is not None:
            file_line_range_str = f"{file_line_start}"

        # ``record.code_block`` is a list of ``(line_num, line)`` tuples; join
        # the line strings to produce a single block of source code. The
        # original newlines are preserved because individual lines retain their
        # trailing ``\n`` characters.
        code_block_pairs = list(record.code_block or [])
        code_block = "".join(line for _line_num, line in code_block_pairs)

        return {
            "status": status,
            "check_id": record.check_id,
            "bc_check_id": record.bc_check_id,
            "check_name": record.check_name,
            "check_class": record.check_class,
            "resource": record.resource,
            "file_path": record.file_path,
            "file_line_range_str": file_line_range_str,
            "file_line_start": file_line_start,
            "file_line_end": file_line_end,
            "severity": severity,
            "code_block": code_block,
            "code_block_lines": code_block_pairs,
            "guideline": record.guideline,
            "evaluations": record.evaluations,
            "description": record.description,
            "short_description": record.short_description,
            "details": list(record.details or []),
            "caller_file_path": record.caller_file_path,
            "resource_address": record.resource_address,
        }
