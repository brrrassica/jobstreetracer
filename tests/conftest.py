"""Shared pytest fixtures and options for the jobstreetracer test suite."""

from __future__ import annotations


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--update-fixtures",
        action="store_true",
        default=False,
        help="regenerate committed cross-track fixtures (e.g. web/tests/fixtures/feed.json)",
    )
