"""Integration test fixtures.

These tests expect the docker-compose.test.yml stack to be running:
    docker compose -f docker-compose.test.yml up -d
"""

import os

import pytest

API_URL = os.environ.get("TEST_API_URL", "http://localhost:8000/api")


@pytest.fixture
def api_url():
    return API_URL
