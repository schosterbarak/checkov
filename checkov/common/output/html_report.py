"""
HTML report generation module for Checkov.

This module provides the rendering engine for the ``--output html`` CLI option.
It transforms one or more :class:`Report` objects produced by framework runners
into a self-contained HTML document styled with Material Design 3 tokens.

The HTML is generated via Jinja2 templating from the companion template file
located at ``checkov/common/output/templates/html_report.html``.

Functions:
    get_html_report_string: Render reports into a complete HTML string.
    write_html_report: Render reports and write the HTML to a file path.
"""

import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from checkov.common.models.enums import CheckResult
from checkov.version import version as checkov_version

# ---------------------------------------------------------------------------
# Jinja2 template directory — resolved relative to *this* module so it works
# both when running from the repository checkout and when installed as a
# distributable package.
# ---------------------------------------------------------------------------
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')


def _get_template_environment():
    """Create and return a Jinja2 ``Environment`` configured for HTML report
    rendering.

    * **Loader**: ``FileSystemLoader`` pointed at the ``templates/``
      subdirectory adjacent to this module.
    * **Autoescaping**: Enabled for ``.html`` extensions via
      ``select_autoescape`` to prevent XSS when rendering user-provided data
      such as file paths, resource names, and code blocks.

    Returns:
        jinja2.Environment: A ready-to-use template environment.
    """
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(['html']),
    )
    return env


def get_html_report_string(reports, quiet=False, compact=False):
    """Generate a complete HTML report string from a list of Report objects.

    Each :class:`~checkov.common.output.report.Report` in *reports* is
    converted to an HTML-friendly dictionary (retaining raw ``Record``
    objects for direct attribute access in the Jinja2 template) and
    aggregated into a single-page HTML document.

    Empty reports (where :meth:`Report.is_empty` returns ``True``) are
    automatically excluded from the rendered output.

    Args:
        reports (list): List of :class:`~checkov.common.output.report.Report`
            objects produced by framework runners.
        quiet (bool): When ``True`` only failed checks are included in the
            output — passed checks, skipped checks, and parsing errors are
            omitted.  Defaults to ``False``.
        compact (bool): Reserved for future compact rendering mode.
            Currently accepted but unused.  Defaults to ``False``.

    Returns:
        str: A complete, self-contained HTML document string ready to be
        written to a file or printed to stdout.
    """
    env = _get_template_environment()
    template = env.get_template('html_report.html')

    # ------------------------------------------------------------------
    # Aggregate data from all reports
    # ------------------------------------------------------------------
    report_data_list = []
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_parsing_errors = 0

    for report in reports:
        if report.is_empty():
            continue

        html_dict = report.get_html_dict(is_quiet=quiet)
        report_data_list.append(html_dict)

        summary = html_dict['summary']
        total_passed += summary['passed']
        total_failed += summary['failed']
        total_skipped += summary['skipped']
        total_parsing_errors += summary['parsing_errors']

    # ------------------------------------------------------------------
    # Build template context
    # ------------------------------------------------------------------
    context = {
        'reports': report_data_list,
        'total_passed': total_passed,
        'total_failed': total_failed,
        'total_skipped': total_skipped,
        'total_parsing_errors': total_parsing_errors,
        'checkov_version': checkov_version,
        'scan_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'CheckResult': CheckResult,
    }

    return template.render(**context)


def write_html_report(reports, output_path, quiet=False, compact=False):
    """Generate an HTML report and write it to a file.

    This is a convenience wrapper around :func:`get_html_report_string` that
    handles file I/O.  The output file is written with UTF-8 encoding so
    that any Unicode characters in file paths or resource names are
    correctly preserved.

    Args:
        reports (list): List of :class:`~checkov.common.output.report.Report`
            objects produced by framework runners.
        output_path (str): Filesystem path where the HTML report will be
            written.  Parent directories must already exist.
        quiet (bool): When ``True`` only failed checks are rendered.
            Defaults to ``False``.
        compact (bool): Reserved for future compact rendering mode.
            Defaults to ``False``.
    """
    html_string = get_html_report_string(reports, quiet=quiet, compact=compact)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_string)
