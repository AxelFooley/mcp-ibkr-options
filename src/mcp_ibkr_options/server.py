"""MCP server for IBKR option chain data fetching using FastMCP."""

import logging
from typing import Any

from fastmcp import FastMCP

from .config import settings
from .session_manager import session_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    "MCP IBKR Options",
    version="0.1.0",
    description="MCP server for fetching Interactive Brokers option chain data",
)


# ============================================================================
# Lifecycle Management
# ============================================================================


@mcp.lifespan
async def lifespan():
    """Manage server lifecycle."""
    logger.info("Starting MCP IBKR Options server")
    await session_manager.start()
    yield
    logger.info("Shutting down MCP IBKR Options server")
    await session_manager.stop()


# ============================================================================
# MCP Tools
# ============================================================================


@mcp.tool()
async def create_session() -> dict[str, Any]:
    """
    Create a new IBKR session.

    This must be called first before using other tools.
    Returns a session_id that must be included in subsequent requests.

    Returns:
        Dictionary containing session_id and confirmation message
    """
    session_id = session_manager.create_session()
    logger.info(f"Created new session: {session_id}")

    return {
        "session_id": session_id,
        "message": (
            f"Created new session: {session_id}\n\n"
            f"Use this session_id in subsequent tool calls. "
            f"Session will expire after {settings.session_timeout_minutes} "
            f"minutes of inactivity."
        ),
    }


@mcp.tool()
async def delete_session(session_id: str) -> dict[str, Any]:
    """
    Delete an existing IBKR session and clean up resources.

    Args:
        session_id: The session ID to delete

    Returns:
        Dictionary containing confirmation message
    """
    success = session_manager.delete_session(session_id)

    if success:
        logger.info(f"Deleted session: {session_id}")
        return {
            "success": True,
            "message": f"Successfully deleted session: {session_id}",
        }
    else:
        logger.warning(f"Attempted to delete non-existent session: {session_id}")
        return {
            "success": False,
            "message": f"Session not found or already deleted: {session_id}",
        }


@mcp.tool()
async def get_underlying_price(session_id: str, symbol: str) -> dict[str, Any]:
    """
    Get the current price of an underlying symbol.

    Tries Yahoo Finance first (free), falls back to IBKR market data.

    Args:
        session_id: The session ID from create_session
        symbol: Underlying symbol (e.g., SPY, AAPL, SPX)

    Returns:
        Dictionary containing current price and symbol

    Raises:
        ValueError: If session is invalid or symbol price cannot be fetched
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise ValueError(
            f"Invalid or expired session: {session_id}. Create a new session first."
        )

    client = session.get_or_create_client()
    price = client.get_underlying_price(symbol)

    if price is None:
        raise ValueError(
            f"Could not fetch price for {symbol}. "
            f"Check that the symbol is valid and market data is available."
        )

    logger.info(f"Fetched price for {symbol}: ${price:.2f}")

    return {
        "symbol": symbol,
        "price": price,
        "message": f"{symbol} current price: ${price:.2f}",
    }


@mcp.tool()
async def fetch_option_chain(
    session_id: str,
    symbol: str,
    strike_count: int | None = None,
    expiration_days: list[int] | None = None,
) -> dict[str, Any]:
    """
    Fetch complete option chain data for a symbol.

    Returns comprehensive data including bid/ask, volume, open interest,
    delta, gamma, theta, vega, and implied volatility.

    Args:
        session_id: The session ID from create_session
        symbol: Underlying symbol (e.g., SPY, AAPL, SPX)
        strike_count: Number of strikes above and below current price (default: 20)
        expiration_days: Array of days from today for expirations
                        (e.g., [0, 1, 7, 14, 30]). If not specified,
                        returns all available expirations.

    Returns:
        Dictionary containing complete option chain data

    Raises:
        ValueError: If session is invalid or option chain cannot be fetched
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise ValueError(
            f"Invalid or expired session: {session_id}. Create a new session first."
        )

    client = session.get_or_create_client()
    data = client.fetch_option_chain(
        symbol=symbol,
        strike_count=strike_count,
        expiration_days=expiration_days,
    )

    logger.info(
        f"Fetched option chain for {symbol}: {data['total_contracts']} contracts "
        f"({data['calls']} calls, {data['puts']} puts)"
    )

    # Add summary message
    data["message"] = (
        f"Successfully fetched option chain for {symbol}\n\n"
        f"Underlying Price: ${data['underlying_price']:.2f}\n"
        f"Total Contracts: {data['total_contracts']}\n"
        f"Calls: {data['calls']} | Puts: {data['puts']}\n"
        f"Expirations: {len(data['expirations'])}\n"
        f"Strikes: {len(data['strikes'])}\n\n"
        f"Data includes: bid, ask, last, volume, open interest, "
        f"delta, gamma, theta, vega, implied volatility"
    )

    return data


@mcp.tool()
async def get_session_stats() -> dict[str, Any]:
    """
    Get statistics about all active sessions.

    Includes connection status and last access times.
    Useful for debugging and monitoring.

    Returns:
        Dictionary containing session statistics
    """
    stats = session_manager.get_stats()

    summary = (
        f"Session Statistics\n"
        f"{'=' * 50}\n"
        f"Total Active Sessions: {stats['total_sessions']}\n\n"
    )

    if stats["sessions"]:
        for s in stats["sessions"]:
            summary += (
                f"Session ID: {s['session_id']}\n"
                f"  Created: {s['created_at']}\n"
                f"  Last Accessed: {s['last_accessed']}\n"
                f"  Connected: {s['is_connected']}\n\n"
            )
    else:
        summary += "No active sessions\n"

    stats["message"] = summary
    return stats


@mcp.tool()
async def health_check(session_id: str | None = None) -> dict[str, Any]:
    """
    Check the health status of the MCP server and IBKR connection.

    Verifies that the server is running and can connect to IBKR.

    Args:
        session_id: Optional session ID to check specific session health

    Returns:
        Dictionary containing health status information
    """
    import datetime

    health_info = {
        "server": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "total_sessions": len(session_manager.sessions),
    }

    if session_id:
        session = session_manager.get_session(session_id)
        if session:
            health_info["session"] = {
                "valid": True,
                "connected": session.client.is_connected if session.client else False,
            }
        else:
            health_info["session"] = {"valid": False}

    summary = (
        f"Health Check\n"
        f"{'=' * 50}\n"
        f"Server Status: {health_info['server']}\n"
        f"Active Sessions: {health_info['total_sessions']}\n"
    )

    if "session" in health_info:
        summary += (
            f"Session Valid: {health_info['session']['valid']}\n"
            f"Session Connected: {health_info['session'].get('connected', 'N/A')}\n"
        )

    health_info["message"] = summary
    return health_info


# ============================================================================
# Server Entry Point
# ============================================================================


def main() -> None:
    """Run the MCP server."""
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    mcp.run(host=settings.host, port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
