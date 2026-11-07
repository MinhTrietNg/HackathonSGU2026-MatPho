"""
Pytest Test Fixtures for Mắt Phố Backend Tests
"""

import sys
import os
from pathlib import Path
import pytest
from starlette.testclient import TestClient

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["ENVIRONMENT"] = "development"

from src.main import app


@pytest.fixture(scope="session")
def client():
    """Provides a TestClient for making HTTP requests against the FastAPI app."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
