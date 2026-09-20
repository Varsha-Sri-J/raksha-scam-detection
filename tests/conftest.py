import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.services.session_store import session_store


@pytest.fixture
def client():
    """Synchronous test client."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client():
    """Asynchronous HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


import asyncio


@pytest.fixture(autouse=True)
def clear_session_store():
    """Reset the in-memory session store before each test."""
    asyncio.run(session_store.clear())
    yield
    asyncio.run(session_store.clear())
