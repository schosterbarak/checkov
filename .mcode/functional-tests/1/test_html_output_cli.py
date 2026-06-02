"""Functional / end-to-end tests for the new ``checkov -o html`` output format.

These tests exercise the real ``checkov`` CLI binary in subprocesses; they do
not import checkov directly. The intent is to verify the user-facing contract:

    checkov -d <iac-folder> -o html --output-file-path <out-dir>
    -> writes <out-dir>/results_report.html, a valid HTML document.

The tests cover the eight cases described in the milestone delegation:

    1. CLI dispatch produces results_report.html in the output directory.
    2. The rendered HTML mentions at least one CKV_* check id and the
       ``aws_s3_bucket`` resource that appears in the terraform fixtures.
    3. Multi-format invocation ``-o cli -o html`` does not crash and still
       writes the HTML file.
    4. Scanning an empty directory still produces a valid HTML report.
    5. HTML escaping: a terraform file with ``<script>`` in a string is
       rendered with ``&lt;script&gt;`` and never as raw ``<script>``.
    6. ``checkov --help`` (or an invalid -o value) advertises ``html`` as
       a valid output choice.
    7. ``OUTPUT_CHOICES`` from the runner registry contains ``html``.
    8. The ``HTML`` class can be used as a library: ``HTML([]).get_html()``
       returns a string starting with ``<!DOCTYPE html>``.
"""
from __future__ import annotations

import html.parser
import os
import subprocess
import sys
import textwrap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A generous timeout: checkov loads the entire check registry on every CLI
# invocation, which can take 20+ seconds in CI sandboxes.
CHECKOV_TIMEOUT = 240


def run_checkov(checkov_binary, *args, cwd=None, check=False):
    """Invoke checkov as a subprocess and capture its output."""
    cmd = [checkov_binary, *args]
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=CHECKOV_TIMEOUT,
        check=check,
    )


class _HtmlValidityParser(html.parser.HTMLParser):
    """Tiny html.parser subclass that raises on malformed markup.

    ``html.parser`` is intentionally lenient, but it still raises on truly
    broken input. The default behaviour (silently fixing things up) is what we
    want — we only assert the parser doesn't *raise*. This mirrors the
    in-repo unit test pattern used in ``tests/common/output/test_html_report.py``.
    """

    def error(self, message):  # pragma: no cover - never expected
        raise AssertionError(f"HTML parser error: {message}")


def parse_html(html_text):
    """Feed ``html_text`` through ``html.parser.HTMLParser`` to check it parses."""
    parser = _HtmlValidityParser(convert_charrefs=True)
    parser.feed(html_text)
    parser.close()


# ---------------------------------------------------------------------------
# 1. CLI dispatch writes results_report.html
# ---------------------------------------------------------------------------

class TestCliDispatchProducesHtmlFile:
    def test_cli_writes_results_report_html(self, checkov_binary, tf_fixtures_dir, tmp_path, checkov_repo_dir):
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = run_checkov(
            checkov_binary,
            "-d", tf_fixtures_dir,
            "-o", "html",
            "--output-file-path", str(out_dir),
            cwd=checkov_repo_dir,
        )

        # checkov exits non-zero when there are failed checks, which is fine
        # for this test — we care that the HTML file was produced.
        report_path = out_dir / "results_report.html"
        assert report_path.exists(), (
            f"results_report.html not found in {out_dir}; "
            f"checkov stdout=\n{result.stdout}\n"
            f"checkov stderr=\n{result.stderr}"
        )

        size = report_path.stat().st_size
        assert size > 0, f"results_report.html is empty (size=0); stderr={result.stderr}"

        report_text = report_path.read_text(encoding="utf-8")
        assert report_text.startswith("<!DOCTYPE html>"), (
            f"Report does not start with <!DOCTYPE html>; first 80 chars: {report_text[:80]!r}"
        )
        assert "</html>" in report_text, "Report missing closing </html> tag"

        # Should parse without raising.
        parse_html(report_text)


# ---------------------------------------------------------------------------
# 2. Content fidelity - check IDs and scanned resources appear in the report
# ---------------------------------------------------------------------------

class TestContentFidelity:
    def test_html_contains_checkov_ids_and_resource_name(
        self, checkov_binary, tf_fixtures_dir, tmp_path, checkov_repo_dir
    ):
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        run_checkov(
            checkov_binary,
            "-d", tf_fixtures_dir,
            "-o", "html",
            "--output-file-path", str(out_dir),
            cwd=checkov_repo_dir,
        )

        report_path = out_dir / "results_report.html"
        assert report_path.exists()
        report_text = report_path.read_text(encoding="utf-8")

        # At least one CKV_AWS_* id must be present (the fixtures scan terraform
        # AWS resources so AWS-prefixed CKV ids are guaranteed by checkov's
        # check registry).
        assert "CKV_AWS_" in report_text, (
            "No CKV_AWS_* check id appears in the rendered HTML; the report is "
            "supposed to list the checks that ran against the AWS S3 fixtures."
        )

        # The scanned resource type must appear somewhere in the rendered HTML.
        assert "aws_s3_bucket" in report_text, (
            "The rendered HTML should reference the aws_s3_bucket resource "
            "that the terraform fixtures define."
        )


# ---------------------------------------------------------------------------
# 3. Multi-format invocation: -o cli -o html
# ---------------------------------------------------------------------------

class TestMultiFormatInvocation:
    def test_cli_and_html_together_do_not_crash(
        self, checkov_binary, tf_fixtures_dir, tmp_path, checkov_repo_dir
    ):
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = run_checkov(
            checkov_binary,
            "-d", tf_fixtures_dir,
            "-o", "cli",
            "-o", "html",
            "--output-file-path", str(out_dir),
            cwd=checkov_repo_dir,
        )

        # The HTML file should still be written.
        report_path = out_dir / "results_report.html"
        assert report_path.exists(), (
            f"results_report.html missing after -o cli -o html; "
            f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
        )
        assert report_path.stat().st_size > 0

        # checkov should not have crashed with a Python traceback; non-zero
        # exit on failing checks is normal but a traceback on stderr is not.
        assert "Traceback (most recent call last)" not in result.stderr, (
            f"Unexpected traceback in stderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# 4. Empty directory still produces a valid HTML report
# ---------------------------------------------------------------------------

class TestEmptyDirectory:
    def test_empty_input_dir_produces_valid_html(self, checkov_binary, tmp_path, checkov_repo_dir):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = run_checkov(
            checkov_binary,
            "-d", str(empty_dir),
            "-o", "html",
            "--output-file-path", str(out_dir),
            cwd=checkov_repo_dir,
        )

        report_path = out_dir / "results_report.html"
        assert report_path.exists(), (
            f"results_report.html missing after scanning an empty directory; "
            f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
        )

        report_text = report_path.read_text(encoding="utf-8")
        assert report_text.startswith("<!DOCTYPE html>")
        assert "</html>" in report_text

        # html.parser should accept the document.
        parse_html(report_text)


# ---------------------------------------------------------------------------
# 5. HTML escaping regression for raw user input ``<script>``
# ---------------------------------------------------------------------------

class TestHtmlEscaping:
    def test_user_supplied_script_tag_is_escaped(self, checkov_binary, tmp_path, checkov_repo_dir):
        # Build a tiny terraform tree with a bucket name containing a literal
        # "<script>" substring. checkov will not execute it, but Record fields
        # (resource, file_path, code_block, etc.) will surface the string in
        # the rendered HTML.
        tf_dir = tmp_path / "iac"
        tf_dir.mkdir()
        tf_file = tf_dir / "main.tf"
        tf_file.write_text(textwrap.dedent(
            """
            resource "aws_s3_bucket" "evil" {
              bucket = "evil-<script>alert(1)</script>-name"
              acl    = "public-read"
            }
            """
        ).strip() + "\n")

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        run_checkov(
            checkov_binary,
            "-d", str(tf_dir),
            "-o", "html",
            "--output-file-path", str(out_dir),
            cwd=checkov_repo_dir,
        )

        report_path = out_dir / "results_report.html"
        assert report_path.exists()
        report_text = report_path.read_text(encoding="utf-8")

        # The escaped form must appear -- the bucket name should surface in the
        # rendered code block or details.
        assert "&lt;script&gt;" in report_text, (
            "Expected '<script>' to be HTML-escaped to '&lt;script&gt;' in the "
            "rendered report, but it was not present."
        )

        # The raw, executable form must NOT appear anywhere in the rendered
        # HTML body (we tolerate it in <style>/<script> tags that the template
        # itself ships, but the user-controlled payload includes alert(1) which
        # would only come from the bucket name).
        assert "<script>alert(1)</script>" not in report_text, (
            "Raw <script>alert(1)</script> payload appeared unescaped in the "
            "rendered HTML — this is an XSS regression!"
        )


# ---------------------------------------------------------------------------
# 6. checkov advertises ``html`` as a valid -o choice
# ---------------------------------------------------------------------------

class TestHtmlIsAdvertisedChoice:
    def test_invalid_output_error_lists_html(self, checkov_binary, checkov_repo_dir):
        # Pick an output value that's guaranteed not to be valid; the argparse
        # error message lists the legal choices, which must include ``html``.
        result = run_checkov(
            checkov_binary,
            "-d", ".",
            "-o", "this_is_not_a_valid_format",
            cwd=checkov_repo_dir,
        )

        combined = (result.stdout or "") + (result.stderr or "")
        assert "html" in combined, (
            "Expected the 'invalid -o choice' error to advertise 'html' as a "
            f"valid option; got:\nstdout={result.stdout}\nstderr={result.stderr}"
        )


# ---------------------------------------------------------------------------
# 7. OUTPUT_CHOICES contains html (library-level Python check)
# ---------------------------------------------------------------------------

class TestOutputChoicesContainsHtml:
    def test_output_choices_includes_html(self, checkov_repo_dir):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from checkov.common.runners.runner_registry import OUTPUT_CHOICES; "
                "assert 'html' in OUTPUT_CHOICES, OUTPUT_CHOICES",
            ],
            cwd=checkov_repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"OUTPUT_CHOICES does not include 'html'; stderr=\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# 8. HTML class as a library: HTML([]).get_html() starts with <!DOCTYPE html>
# ---------------------------------------------------------------------------

class TestHtmlClassLibraryUse:
    def test_html_class_returns_doctype_prefixed_string(self, checkov_repo_dir):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from checkov.common.output.html import HTML; "
                "print('OK' if HTML([]).get_html().startswith('<!DOCTYPE html>') else 'NO')",
            ],
            cwd=checkov_repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"python -c failed; stderr=\n{result.stderr}"
        assert result.stdout.strip() == "OK", (
            f"HTML([]).get_html() did not start with <!DOCTYPE html>; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
