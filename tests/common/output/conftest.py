from __future__ import annotations
from typing import Any

import pytest
from checkov.common.secrets.consts import ValidationStatus

from checkov.common.bridgecrew.check_type import CheckType
from checkov.common.bridgecrew.severities import BcSeverities, Severities
from checkov.common.models.enums import CheckResult

from checkov.common.output.record import Record
from checkov.common.output.secrets_record import SecretsRecord

from checkov.common.output.report import Report


@pytest.fixture
def secrets_report() -> Report:
    kwargs = {'check_id': 'mock', 'check_name': 'mock', 'code_block': 'mock', 'file_path': 'mock',
              'file_line_range': 'mock', 'evaluations': 'mock', 'check_class': 'mock', 'file_abs_path': 'mock'}
    record_1 = SecretsRecord(bc_check_id="VIOLATION_1", resource="RESOURCE_1",
                             check_result={"result": CheckResult.FAILED},
                             validation_status=ValidationStatus.VALID.value, **kwargs)
    record_2 = SecretsRecord(bc_check_id="VIOLATION_2", resource="RESOURCE_2",
                             check_result={"result": CheckResult.FAILED},
                             validation_status=ValidationStatus.INVALID.value, **kwargs)
    record_3 = SecretsRecord(bc_check_id="VIOLATION_3", resource="RESOURCE_3",
                             check_result={"result": CheckResult.FAILED},
                             validation_status=ValidationStatus.UNKNOWN.value, **kwargs)
    record_4 = SecretsRecord(bc_check_id="VIOLATION_4", resource="RESOURCE_4",
                             check_result={"result": CheckResult.FAILED},
                             validation_status=ValidationStatus.VALID.value, **kwargs)

    record_5 = SecretsRecord(bc_check_id="VIOLATION_1", resource="RESOURCE_1",
                             check_result={"result": CheckResult.PASSED},
                             validation_status=ValidationStatus.INVALID.value, **kwargs)

    report = Report(CheckType.SECRETS)
    report.add_record(record_1)
    report.add_record(record_2)
    report.add_record(record_3)
    report.add_record(record_4)
    report.add_record(record_5)

    return report


@pytest.fixture()
def json_reduced_check() -> dict[str, Any]:
    return {
        "check_id": "CKV_GHA_1",
        "check_name": "Ensure ACTIONS_ALLOW_UNSECURE_COMMANDS isn\u0027t true on environment variables",
        "check_result": {
            "result": "PASSED",
            "results_configuration": {}
        },
        "resource": "jobs(container-test-job)",
        "file_path": "/.github/workflows/image_no_violation.yml",
        "file_line_range": [
            7,
            7
        ],
        "file_abs_path": "/tmp/checkov/elturgeman6/elturgeman/supplygoat1/main/src/.github/workflows/image_no_violation.yml",
        "code_block": [
            [
                7,
                "    runs-on: ubuntu-latest\n"
            ],
        ],
        "bc_check_id": "BC_REPO_GITHUB_ACTION_1",
        "inspected_key_line": None,
        "evaluated_keys": None,
        "inspected_key": "",
        "inspected_value": ""
    }

@pytest.fixture()
def json_reduced_report() -> dict[str, Any]:
    return {
        "checks": {
            "passed_checks": [
                {
                    "check_id": "CKV_GHA_1",
                    "check_name": "Ensure ACTIONS_ALLOW_UNSECURE_COMMANDS isn\u0027t true on environment variables",
                    "check_result": {
                        "result": "PASSED",
                        "results_configuration": {}
                    },
                    "resource": "jobs(container-test-job)",
                    "file_path": "/.github/workflows/image_no_violation.yml",
                    "file_line_range": [
                        7,
                        7
                    ],
                    "file_abs_path": "/tmp/checkov/elturgeman6/elturgeman/supplygoat1/main/src/.github/workflows/image_no_violation.yml",
                    "code_block": [
                        [
                            7,
                            "    runs-on: ubuntu-latest\n"
                        ],
                    ],
                    "bc_check_id": "BC_REPO_GITHUB_ACTION_1",
                    "inspected_key_line": None,
                    "evaluated_keys": None,
                    "inspected_key": "",
                    "inspected_value": ""
                }
            ],
            "failed_checks": [
                {
                    "check_id": "CKV_GHA_2",
                    "check_name": "Ensure ACTIONS_ALLOW_UNSECURE_COMMANDS isn\u0027t true on environment variables",
                    "check_result": {
                        "result": "FAILED",
                        "results_configuration": {}
                    },
                    "resource": "jobs(container-test-job)",
                    "file_path": "/.github/workflows/image_no_violation.yml",
                    "file_line_range": [
                        7,
                        7
                    ],
                    "file_abs_path": "/tmp/checkov/elturgeman6/elturgeman/supplygoat1/main/src/.github/workflows/image_no_violation.yml",
                    "code_block": [
                        [
                            7,
                            "    runs-on: ubuntu-latest\n"
                        ],
                    ],
                    "bc_check_id": "BC_REPO_GITHUB_ACTION_1",
                    "inspected_key_line": None,
                    "evaluated_keys": None,
                    "inspected_key": "",
                    "inspected_value": ""
                }
            ],
            "skipped_checks": []
        },
        "image_cached_results": []
    }


@pytest.fixture()
def html_multi_check_type_reports() -> list[Report]:
    """Build a list of :class:`Report` objects with varied check_types,
    record statuses, severities, and parsing errors.

    Used by the HTML output tests to exercise multi-report rendering
    in a single, deterministic context.
    """

    def _record(
        *,
        check_id: str,
        check_name: str,
        resource: str,
        file_path: str,
        result: CheckResult,
        severity_name: str | None = None,
    ) -> Record:
        severity = Severities[severity_name] if severity_name else None
        return Record(
            check_id=check_id,
            check_name=check_name,
            check_result={"result": result},
            code_block=[(1, f'resource "{resource}" {{\n'), (2, "  foo = \"bar\"\n"), (3, "}\n")],
            file_path=file_path,
            file_line_range=[1, 3],
            resource=resource,
            evaluations=None,
            check_class="test_check_class",
            file_abs_path="/abs" + file_path,
            severity=severity,
        )

    tf_report = Report("terraform")
    tf_report.add_record(_record(
        check_id="CKV_AWS_TF_P1", check_name="TF passed one",
        resource="aws_s3_bucket.tf_passed_1", file_path="/iac/tf/passed_1.tf",
        result=CheckResult.PASSED, severity_name=BcSeverities.LOW,
    ))
    tf_report.add_record(_record(
        check_id="CKV_AWS_TF_P2", check_name="TF passed two",
        resource="aws_s3_bucket.tf_passed_2", file_path="/iac/tf/passed_2.tf",
        result=CheckResult.PASSED, severity_name=BcSeverities.MEDIUM,
    ))
    tf_report.add_record(_record(
        check_id="CKV_AWS_TF_F1", check_name="TF failed one",
        resource="aws_s3_bucket.tf_failed_1", file_path="/iac/tf/failed_1.tf",
        result=CheckResult.FAILED, severity_name=BcSeverities.HIGH,
    ))
    tf_report.add_record(_record(
        check_id="CKV_AWS_TF_F2", check_name="TF failed two",
        resource="aws_s3_bucket.tf_failed_2", file_path="/iac/tf/failed_2.tf",
        result=CheckResult.FAILED, severity_name=BcSeverities.CRITICAL,
    ))
    tf_report.add_record(_record(
        check_id="CKV_AWS_TF_S1", check_name="TF skipped one",
        resource="aws_s3_bucket.tf_skipped_1", file_path="/iac/tf/skipped_1.tf",
        result=CheckResult.SKIPPED, severity_name=BcSeverities.NONE,
    ))

    cfn_report = Report("cloudformation")
    cfn_report.add_record(_record(
        check_id="CKV_AWS_CFN_P1", check_name="CFN passed one",
        resource="AWS::S3::Bucket.cfn_passed_1", file_path="/iac/cfn/passed_1.json",
        result=CheckResult.PASSED, severity_name=BcSeverities.MEDIUM,
    ))
    cfn_report.add_record(_record(
        check_id="CKV_AWS_CFN_F1", check_name="CFN failed one",
        resource="AWS::S3::Bucket.cfn_failed_1", file_path="/iac/cfn/failed_1.json",
        result=CheckResult.FAILED, severity_name=BcSeverities.HIGH,
    ))

    k8s_report = Report("kubernetes")
    k8s_report.add_parsing_error("/iac/k8s/broken.yaml")

    return [tf_report, cfn_report, k8s_report]