"""
Unit tests for the HTML report generation module.

Validates that ``get_html_report_string()`` correctly transforms
:class:`Report` objects into complete, well-formed, Material Design 3
styled HTML documents.
"""

import os
import unittest

from checkov.common.models.enums import CheckResult
from checkov.common.output.record import Record
from checkov.common.output.report import Report
from checkov.common.output.html_report import get_html_report_string


class TestHtmlReport(unittest.TestCase):
    """Comprehensive tests for the Checkov HTML report generation feature."""

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _create_record(self, check_id, check_name, result, resource,
                       file_path, code_block=None, guideline=None):
        """Create a mock :class:`Record` with the given test parameters.

        Args:
            check_id: The check identifier (e.g. ``"CKV_AWS_1"``).
            check_name: Human-readable check description.
            result: A dict such as ``{"result": CheckResult.PASSED}`` or
                ``{"result": CheckResult.SKIPPED, "suppress_comment": "..."}``
            resource: Resource identifier string.
            file_path: Relative file path for the record.
            code_block: Optional list of ``(line_num, line_text)`` tuples.
                Defaults to an empty string (no code block).
            guideline: Optional URL string; set via
                ``record.set_guideline()`` after construction.

        Returns:
            A fully constructed :class:`Record` instance.
        """
        if code_block is None:
            code_block = ""

        record = Record(
            check_id=check_id,
            check_name=check_name,
            check_result=result,
            code_block=code_block,
            file_path=file_path,
            file_line_range=[1, 10],
            resource=resource,
            evaluations=None,
            check_class="checkov.test.TestCheck",
            file_abs_path=os.path.abspath(file_path),
            entity_tags=None,
        )

        if guideline is not None:
            record.set_guideline(guideline)

        return record

    def _create_report_with_checks(self, check_type="terraform"):
        """Create a populated :class:`Report` with a mix of check outcomes.

        The report contains:
        * 2 passed checks  (CKV_AWS_1, CKV_AWS_2)
        * 2 failed checks  (CKV_AWS_3, CKV_AWS_4) with code blocks
        * 1 skipped check  (CKV_AWS_5)
        * 1 parsing error  (``/path/to/bad_file.tf``)

        Args:
            check_type: The framework identifier passed to the Report
                constructor.  Defaults to ``"terraform"``.

        Returns:
            A fully populated :class:`Report` instance.
        """
        report = Report(check_type)

        # Passed checks
        report.add_record(self._create_record(
            check_id="CKV_AWS_1",
            check_name="Ensure S3 bucket versioning is enabled",
            result={"result": CheckResult.PASSED},
            resource="aws_s3_bucket.example1",
            file_path="/main.tf",
        ))
        report.add_record(self._create_record(
            check_id="CKV_AWS_2",
            check_name="Ensure S3 bucket has access logging",
            result={"result": CheckResult.PASSED},
            resource="aws_s3_bucket.example2",
            file_path="/main.tf",
        ))

        # Failed checks (with code blocks)
        report.add_record(self._create_record(
            check_id="CKV_AWS_3",
            check_name="Ensure S3 bucket encryption is enabled",
            result={"result": CheckResult.FAILED},
            resource="aws_s3_bucket.example3",
            file_path="/main.tf",
            code_block=[
                (1, 'resource "aws_s3_bucket" "example3" {\n'),
                (2, '  bucket = "my-bucket"\n'),
                (3, '}\n'),
            ],
        ))
        report.add_record(self._create_record(
            check_id="CKV_AWS_4",
            check_name="Ensure S3 bucket policy is set",
            result={"result": CheckResult.FAILED},
            resource="aws_s3_bucket.example4",
            file_path="/storage.tf",
            code_block=[
                (5, 'resource "aws_s3_bucket" "example4" {\n'),
                (6, '  bucket = "other-bucket"\n'),
                (7, '}\n'),
            ],
            guideline="https://docs.checkov.io/en/latest/checks/aws/CKV_AWS_4",
        ))

        # Skipped check
        report.add_record(self._create_record(
            check_id="CKV_AWS_5",
            check_name="Ensure S3 bucket MFA delete is enabled",
            result={
                "result": CheckResult.SKIPPED,
                "suppress_comment": "Not applicable",
            },
            resource="aws_s3_bucket.example5",
            file_path="/main.tf",
        ))

        # Parsing error
        report.add_parsing_error("/path/to/bad_file.tf")

        return report

    # ------------------------------------------------------------------
    # Test Methods
    # ------------------------------------------------------------------

    def test_html_structure_valid(self):
        """HTML output must contain required structural elements."""
        report = self._create_report_with_checks()
        html = get_html_report_string([report])

        self.assertIsInstance(html, str)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<html", html)
        self.assertIn("<head>", html)
        self.assertIn("<body>", html)
        self.assertIn("</html>", html)
        self.assertIn("</body>", html)
        self.assertIn("</head>", html)

    def test_summary_counts_in_html(self):
        """Summary dashboard must display the correct aggregate counts."""
        report = self._create_report_with_checks()
        html = get_html_report_string([report])

        # The summary uses <div class="card-count"> elements.  We verify
        # the expected counts appear within the summary-dashboard region.
        summary = report.get_summary()
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["parsing_errors"], 1)

        # Each count is rendered inside a card-count div.  We verify the
        # raw count values appear in the generated HTML.
        self.assertIn(">2<", html)  # passed and failed counts
        self.assertIn(">1<", html)  # skipped and parsing errors counts

    def test_check_ids_in_html(self):
        """Every check ID and resource name must appear in the output."""
        report = self._create_report_with_checks()
        html = get_html_report_string([report])

        # Check IDs
        for check_id in ("CKV_AWS_1", "CKV_AWS_2", "CKV_AWS_3",
                         "CKV_AWS_4", "CKV_AWS_5"):
            self.assertIn(check_id, html)

        # Resource names
        for resource in ("aws_s3_bucket.example1", "aws_s3_bucket.example2",
                         "aws_s3_bucket.example3", "aws_s3_bucket.example4",
                         "aws_s3_bucket.example5"):
            self.assertIn(resource, html)

    def test_empty_report_produces_valid_html(self):
        """An empty report must still yield a valid HTML document."""
        report = Report("terraform")
        # Verify the report is indeed empty
        self.assertTrue(report.is_empty())

        html = get_html_report_string([report])

        # Must still return a valid HTML document (even if no framework
        # sections are rendered, the wrapper chrome is present).
        self.assertIsInstance(html, str)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<html", html)
        self.assertIn("<body>", html)
        self.assertIn("</html>", html)

    def test_multi_report_aggregation(self):
        """Reports from different frameworks must be aggregated into one page."""
        tf_report = self._create_report_with_checks(check_type="terraform")
        k8s_report = Report("kubernetes")

        # Add one passed and one failed check to the kubernetes report
        k8s_report.add_record(self._create_record(
            check_id="CKV_K8S_1",
            check_name="Ensure CPU limits are set",
            result={"result": CheckResult.PASSED},
            resource="Deployment.default.nginx",
            file_path="/deployment.yaml",
        ))
        k8s_report.add_record(self._create_record(
            check_id="CKV_K8S_2",
            check_name="Ensure memory limits are set",
            result={"result": CheckResult.FAILED},
            resource="Deployment.default.nginx",
            file_path="/deployment.yaml",
            code_block=[
                (1, "apiVersion: apps/v1\n"),
                (2, "kind: Deployment\n"),
            ],
        ))

        html = get_html_report_string([tf_report, k8s_report])

        # Both framework names must be present
        self.assertIn("terraform", html)
        self.assertIn("kubernetes", html)

        # Checks from both reports must appear
        self.assertIn("CKV_AWS_1", html)
        self.assertIn("CKV_K8S_1", html)
        self.assertIn("CKV_K8S_2", html)

        # Aggregated totals: terraform has 2 passed + k8s has 1 passed = 3
        # The total passed count (3) must appear in the summary dashboard.
        self.assertIn(">3<", html)

    def test_quiet_mode_shows_only_failed(self):
        """Quiet mode must render only failed check details."""
        report = self._create_report_with_checks()
        html = get_html_report_string([report], quiet=True)

        # Failed check IDs MUST be present
        self.assertIn("CKV_AWS_3", html)
        self.assertIn("CKV_AWS_4", html)

        # Passed check IDs must NOT appear (they are excluded in quiet mode)
        self.assertNotIn("CKV_AWS_1", html)
        self.assertNotIn("CKV_AWS_2", html)

        # Skipped check IDs must NOT appear
        self.assertNotIn("CKV_AWS_5", html)

        # The HTML must still be structurally valid
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("</html>", html)

    def test_material_design_css_properties(self):
        """The HTML must include Material Design 3 CSS custom properties."""
        report = self._create_report_with_checks()
        html = get_html_report_string([report])

        # Core M3 colour tokens defined in the :root style block
        self.assertIn("--md-sys-color-primary", html)
        self.assertIn("--md-sys-color-error", html)
        self.assertIn("--md-sys-color-surface", html)
        self.assertIn("--md-sys-color-on-surface", html)

        # Additional M3 tokens the template is expected to include
        self.assertIn("--md-sys-color-primary-container", html)
        self.assertIn("--md-sys-color-error-container", html)
        self.assertIn("--md-sys-color-secondary-container", html)
        self.assertIn("--md-sys-color-tertiary-container", html)
        self.assertIn("--md-sys-color-surface-variant", html)

    def test_html_special_character_escaping(self):
        """User-provided content with HTML entities must be escaped."""
        report = Report("terraform")

        # Code block with HTML-like syntax that must be escaped
        record = self._create_record(
            check_id="CKV_ESCAPE_1",
            check_name="Ensure escaping works",
            result={"result": CheckResult.FAILED},
            resource="aws_s3_bucket.my<test>&bucket",
            file_path="/main.tf",
            code_block=[
                (1, '<div class="test">\n'),
                (2, '  <span>&amp;</span>\n'),
                (3, '</div>\n'),
            ],
        )
        report.add_record(record)

        html = get_html_report_string([report])

        # The resource name's angle brackets and ampersand must be escaped
        # so they do not render as raw HTML tags.
        self.assertIn("&lt;test&gt;", html)
        self.assertIn("&amp;bucket", html)

        # The code block's "<div" must be escaped (not rendered as an
        # actual HTML element).
        self.assertIn("&lt;div", html)

        # The raw unescaped "<div" should NOT be present as an HTML tag
        # within the code block context.  We verify by checking the code
        # is placed inside <pre><code> with escaped content.
        self.assertIn("<pre", html)
        self.assertIn("<code>", html)

    def test_parsing_errors_in_html(self):
        """Parsing error file paths must appear in the report."""
        report = Report("terraform")
        report.add_parsing_error("/path/to/bad1.tf")
        report.add_parsing_error("/path/to/bad2.yaml")

        html = get_html_report_string([report])

        self.assertIn("/path/to/bad1.tf", html)
        self.assertIn("/path/to/bad2.yaml", html)
        # Parsing errors section header must be present
        self.assertIn("Parsing Errors", html)


if __name__ == '__main__':
    unittest.main()
