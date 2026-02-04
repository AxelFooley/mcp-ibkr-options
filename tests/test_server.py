"""Tests for MCP server endpoints."""

import pytest
from fastapi.testclient import TestClient

from mcp_ibkr_options.server import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint returns server info."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "MCP IBKR Options"
    assert "version" in data
    assert data["protocol"] == "mcp/http"


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "sessions" in data


def test_mcp_tools_list(client):
    """Test MCP tools/list endpoint."""
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert "result" in data
    assert "tools" in data["result"]

    tools = data["result"]["tools"]
    tool_names = [t["name"] for t in tools]

    assert "create_session" in tool_names
    assert "delete_session" in tool_names
    assert "get_underlying_price" in tool_names
    assert "fetch_option_chain" in tool_names
    assert "get_session_stats" in tool_names
    assert "health_check" in tool_names


def test_mcp_invalid_method(client):
    """Test MCP endpoint with invalid method."""
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "invalid/method", "params": {}},
    )
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


def test_create_session_tool(client):
    """Test create_session tool."""
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_session", "arguments": {}},
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert "session_id" in data["result"]
    assert "content" in data["result"]


def test_get_session_stats_tool(client):
    """Test get_session_stats tool."""
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_session_stats", "arguments": {}},
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert "stats" in data["result"]


def test_health_check_tool(client):
    """Test health_check tool."""
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "health_check", "arguments": {}},
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert "health" in data["result"]


def test_delete_session_tool_with_invalid_session(client):
    """Test delete_session with invalid session ID."""
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "delete_session",
                "arguments": {"session_id": "invalid-session-id"},
            },
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert "content" in data["result"]


def test_unknown_tool(client):
    """Test calling an unknown tool."""
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}},
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert data["result"]["isError"] is True


def test_session_lifecycle(client):
    """Test complete session lifecycle: create, use, delete."""
    # Create session
    create_response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_session", "arguments": {}},
        },
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["result"]["session_id"]

    # Check health with session
    health_response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "health_check", "arguments": {"session_id": session_id}},
        },
    )
    assert health_response.status_code == 200

    # Delete session
    delete_response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "delete_session", "arguments": {"session_id": session_id}},
        },
    )
    assert delete_response.status_code == 200
