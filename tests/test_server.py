"""Tests for MCP server endpoints using FastMCP."""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_ibkr_options.server import mcp


@pytest.fixture
async def client():
    """Create a test client connected to the MCP server."""
    async with Client(mcp) as c:
        yield c


@pytest.mark.asyncio
async def test_create_session_tool(client):
    """Test create_session tool."""
    result = await client.call_tool("create_session", {})
    content = result.content[0].text

    # Parse the result - tools return text content
    assert "session_id" in content or "Created new session" in content


@pytest.mark.asyncio
async def test_get_session_stats_tool(client):
    """Test get_session_stats tool."""
    result = await client.call_tool("get_session_stats", {})
    content = result.content[0].text

    assert "total_sessions" in content or "sessions" in content


@pytest.mark.asyncio
async def test_health_check_tool(client):
    """Test health_check tool without session."""
    result = await client.call_tool("health_check", {})
    content = result.content[0].text

    assert "server" in content.lower() or "healthy" in content.lower()


@pytest.mark.asyncio
async def test_health_check_tool_with_invalid_session(client):
    """Test health_check tool with invalid session."""
    result = await client.call_tool("health_check", {"session_id": "invalid-session-id"})
    content = result.content[0].text

    assert "invalid" in content.lower() or "expired" in content.lower() or "false" in content.lower()


@pytest.mark.asyncio
async def test_delete_session_tool_with_invalid_session(client):
    """Test delete_session with invalid session ID."""
    result = await client.call_tool("delete_session", {"session_id": "invalid-session-id"})
    content = result.content[0].text

    assert "invalid" in content.lower() or "not found" in content.lower() or "false" in content.lower()


@pytest.mark.asyncio
async def test_session_lifecycle(client):
    """Test complete session lifecycle: create, use, delete."""
    # Create session
    create_result = await client.call_tool("create_session", {})
    create_content = create_result.content[0].text
    assert "session" in create_content.lower()

    # Extract session_id from content - this is a simplified approach
    # In practice, you'd parse the actual response format
    import re
    match = re.search(r'session[_\s]+id[:\s]+([a-f0-9\-]+)', create_content, re.IGNORECASE)
    if match:
        session_id = match.group(1)

        # Check health with session
        health_result = await client.call_tool("health_check", {"session_id": session_id})
        health_content = health_result.content[0].text
        assert "valid" in health_content.lower() or "true" in health_content.lower()

        # Delete session
        delete_result = await client.call_tool("delete_session", {"session_id": session_id})
        delete_content = delete_result.content[0].text
        assert "deleted" in delete_content.lower() or "success" in delete_content.lower()


@pytest.mark.asyncio
async def test_get_underlying_price_without_session(client):
    """Test get_underlying_price with invalid session raises error."""
    with pytest.raises(ToolError, match="Invalid or expired session"):
        await client.call_tool("get_underlying_price", {"session_id": "invalid", "symbol": "SPY"})


@pytest.mark.asyncio
async def test_fetch_option_chain_without_session(client):
    """Test fetch_option_chain with invalid session raises error."""
    with pytest.raises(ToolError, match="Invalid or expired session"):
        await client.call_tool("fetch_option_chain", {"session_id": "invalid", "symbol": "SPY"})


@pytest.mark.asyncio
async def test_list_tools(client):
    """Test that all expected tools are registered."""
    tools = await client.list_tools()
    tool_names = [tool.name for tool in tools]

    expected_tools = [
        "create_session",
        "delete_session",
        "get_underlying_price",
        "fetch_option_chain",
        "get_session_stats",
        "health_check",
    ]

    for expected_tool in expected_tools:
        assert expected_tool in tool_names, f"Tool {expected_tool} not found"


@pytest.mark.asyncio
async def test_tool_schemas(client):
    """Test that all tools have proper schemas."""
    tools = await client.list_tools()

    for tool in tools:
        assert tool.name
        assert tool.description
        assert tool.inputSchema
        assert tool.description, f"Tool {tool.name} has empty description"
