"""Tests for MCP server endpoints using FastMCP."""

import pytest

from mcp_ibkr_options.server import mcp


@pytest.mark.asyncio
async def test_create_session_tool():
    """Test create_session tool."""
    result = await mcp.call_tool("create_session", {})

    assert "session_id" in result
    assert "message" in result
    assert isinstance(result["session_id"], str)
    assert len(result["session_id"]) > 0


@pytest.mark.asyncio
async def test_get_session_stats_tool():
    """Test get_session_stats tool."""
    result = await mcp.call_tool("get_session_stats", {})

    assert "total_sessions" in result
    assert "sessions" in result
    assert "message" in result
    assert isinstance(result["total_sessions"], int)


@pytest.mark.asyncio
async def test_health_check_tool():
    """Test health_check tool without session."""
    result = await mcp.call_tool("health_check", {})

    assert "server" in result
    assert result["server"] == "healthy"
    assert "timestamp" in result
    assert "total_sessions" in result
    assert "message" in result


@pytest.mark.asyncio
async def test_health_check_tool_with_invalid_session():
    """Test health_check tool with invalid session."""
    result = await mcp.call_tool("health_check", {"session_id": "invalid-session-id"})

    assert "server" in result
    assert "session" in result
    assert result["session"]["valid"] is False


@pytest.mark.asyncio
async def test_delete_session_tool_with_invalid_session():
    """Test delete_session with invalid session ID."""
    result = await mcp.call_tool("delete_session", {"session_id": "invalid-session-id"})

    assert "success" in result
    assert result["success"] is False
    assert "message" in result


@pytest.mark.asyncio
async def test_session_lifecycle():
    """Test complete session lifecycle: create, use, delete."""
    # Create session
    create_result = await mcp.call_tool("create_session", {})
    assert "session_id" in create_result
    session_id = create_result["session_id"]

    # Check health with session
    health_result = await mcp.call_tool("health_check", {"session_id": session_id})
    assert "session" in health_result
    assert health_result["session"]["valid"] is True

    # Delete session
    delete_result = await mcp.call_tool("delete_session", {"session_id": session_id})
    assert delete_result["success"] is True

    # Verify session is gone
    health_after_delete = await mcp.call_tool("health_check", {"session_id": session_id})
    assert health_after_delete["session"]["valid"] is False


@pytest.mark.asyncio
async def test_get_underlying_price_without_session():
    """Test get_underlying_price with invalid session raises error."""
    with pytest.raises(ValueError, match="Invalid or expired session"):
        await mcp.call_tool(
            "get_underlying_price", {"session_id": "invalid", "symbol": "SPY"}
        )


@pytest.mark.asyncio
async def test_fetch_option_chain_without_session():
    """Test fetch_option_chain with invalid session raises error."""
    with pytest.raises(ValueError, match="Invalid or expired session"):
        await mcp.call_tool(
            "fetch_option_chain", {"session_id": "invalid", "symbol": "SPY"}
        )


@pytest.mark.asyncio
async def test_list_tools():
    """Test that all expected tools are registered."""
    tools = mcp.list_tools()
    tool_names = [tool["name"] for tool in tools]

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
async def test_tool_schemas():
    """Test that all tools have proper schemas."""
    tools = mcp.list_tools()

    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["description"], f"Tool {tool['name']} has empty description"
