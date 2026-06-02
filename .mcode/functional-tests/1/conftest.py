"""Shared fixtures for checkov HTML output functional tests.

These fixtures only exist to keep the per-test files small and focused. They
intentionally avoid any test isolation magic — each test creates and tears
down its own temporary output directory via the standard ``tmp_path`` fixture
so failures are reproducible by hand.
"""
from __future__ import annotations

import os
import shutil

import pytest


WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/l2l/workspace")
CHECKOV_REPO_DIR = os.path.join(WORKSPACE_DIR, "checkov")
TF_FIXTURES_DIR = os.path.join(CHECKOV_REPO_DIR, "tests/common/output/fixtures")


@pytest.fixture(autouse=True)
def ensure_local_bin_on_path():
    """Make sure ``$HOME/.local/bin`` is on PATH so the ``checkov`` CLI binary is found."""
    home = os.environ.get("HOME", "/l2l")
    local_bin = os.path.join(home, ".local", "bin")
    path = os.environ.get("PATH", "")
    if local_bin not in path.split(":"):
        os.environ["PATH"] = local_bin + ":" + path
    yield


@pytest.fixture
def checkov_binary():
    """Return the absolute path to the ``checkov`` CLI binary."""
    home = os.environ.get("HOME", "/l2l")
    binary = os.path.join(home, ".local", "bin", "checkov")
    if not os.path.isfile(binary):
        # Fall back to whatever is on PATH.
        binary = shutil.which("checkov") or "checkov"
    return binary


@pytest.fixture
def tf_fixtures_dir():
    """Path to the terraform fixtures used by checkov HTML output tests."""
    return TF_FIXTURES_DIR


@pytest.fixture
def checkov_repo_dir():
    return CHECKOV_REPO_DIR
