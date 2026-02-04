"""MCP server for IBKR option chain data fetching."""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import settings
from .session_manager import session_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    logger.info("Starting MCP IBKR Options server")
    await session_manager.start()
    yield
    logger.info("Shutting down MCP IBKR Options server")
    await session_manager.stop()


app = FastAPI(
    title="MCP IBKR Options",
    description="MCP server for fetching Interactive Brokers option chain data",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================================
# MCP Protocol Models
# ============================================================================


class MCPRequest(BaseModel):
    """Base MCP request model."""

    jsonrpc: str = "2.0"
    id: int | str
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


class MCPResponse(BaseModel):
    """Base MCP response model."""

    jsonrpc: str = "2.0"
    id: int | str
    result: Dict[str, Any] | None = None
    error: Dict[str, Any] | None = None


class MCPError(BaseModel):
    """MCP error model."""

    code: int
    message: str
    data: Any = None


# ============================================================================
# MCP Tool Definitions
# ============================================================================

TOOLS = [
    {
        "name": "create_session",
        "description": (
            "Create a new IBKR session. This must be called first before using other tools. "
            "Returns a session_id that must be included in subsequent requests."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "delete_session",
        "description": "Delete an existing IBKR session and clean up resources.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to delete",
                }
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "get_underlying_price",
        "description": (
            "Get the current price of an underlying symbol (stock or index). "
            "Tries Yahoo Finance first (free), falls back to IBKR market data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID from create_session",
                },
                "symbol": {
                    "type": "string",
                    "description": "Underlying symbol (e.g., SPY, AAPL, SPX)",
                },
            },
            "required": ["session_id", "symbol"],
        },
    },
    {
        "name": "fetch_option_chain",
        "description": (
            "Fetch complete option chain data for a symbol with market data and Greeks. "
            "Returns comprehensive data including bid/ask, volume, open interest, "
            "delta, gamma, theta, vega, and implied volatility."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID from create_session",
                },
                "symbol": {
                    "type": "string",
                    "description": "Underlying symbol (e.g., SPY, AAPL, SPX)",
                },
                "strike_count": {
                    "type": "integer",
                    "description": (
                        "Number of strikes above and below current price (default: 20)"
                    ),
                },
                "expiration_days": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "List of days from today for expirations (e.g., [0, 1, 7, 14, 30]). "
                        "If not specified, returns all available expirations."
                    ),
                },
            },
            "required": ["session_id", "symbol"],
        },
    },
    {
        "name": "get_session_stats",
        "description": (
            "Get statistics about all active sessions, including connection status "
            "and last access times. Useful for debugging and monitoring."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "health_check",
        "description": (
            "Check the health status of the MCP server and IBKR connection. "
            "Verifies that the server is running and can connect to IBKR."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID to check specific session health",
                }
            },
            "required": [],
        },
    },
]


# ============================================================================
# MCP Protocol Endpoints
# ============================================================================


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint with server info."""
    return {
        "name": "MCP IBKR Options",
        "version": "0.1.0",
        "description": "MCP server for fetching Interactive Brokers option chain data",
        "protocol": "mcp/http",
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "sessions": len(session_manager.sessions),
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """Main MCP endpoint for JSON-RPC requests."""
    try:
        body = await request.json()
        mcp_request = MCPRequest(**body)

        logger.debug(f"Received MCP request: {mcp_request.method}")

        # Route to appropriate handler
        if mcp_request.method == "tools/list":
            result = {"tools": TOOLS}
        elif mcp_request.method == "tools/call":
            result = await handle_tool_call(mcp_request.params)
        else:
            return JSONResponse(
                content=MCPResponse(
                    jsonrpc="2.0",
                    id=mcp_request.id,
                    error=MCPError(
                        code=-32601,
                        message=f"Method not found: {mcp_request.method}",
                    ).model_dump(),
                ).model_dump(),
                status_code=404,
            )

        response = MCPResponse(jsonrpc="2.0", id=mcp_request.id, result=result)
        return JSONResponse(content=response.model_dump())

    except Exception as e:
        logger.error(f"Error handling MCP request: {e}", exc_info=True)
        return JSONResponse(
            content=MCPResponse(
                jsonrpc="2.0",
                id=getattr(body, "id", 0) if "body" in locals() else 0,
                error=MCPError(code=-32603, message=str(e)).model_dump(),
            ).model_dump(),
            status_code=500,
        )


@app.post("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """SSE endpoint for streaming MCP responses."""

    async def event_generator():
        try:
            body = await request.json()
            mcp_request = MCPRequest(**body)

            # For SSE, we'll send the response as an event
            if mcp_request.method == "tools/call":
                result = await handle_tool_call(mcp_request.params)
                response = MCPResponse(jsonrpc="2.0", id=mcp_request.id, result=result)
                yield f"data: {json.dumps(response.model_dump())}\n\n"
            else:
                error_response = MCPResponse(
                    jsonrpc="2.0",
                    id=mcp_request.id,
                    error=MCPError(
                        code=-32601, message=f"Method not supported via SSE"
                    ).model_dump(),
                )
                yield f"data: {json.dumps(error_response.model_dump())}\n\n"

        except Exception as e:
            logger.error(f"Error in SSE stream: {e}", exc_info=True)
            error_response = MCPResponse(
                jsonrpc="2.0",
                id=0,
                error=MCPError(code=-32603, message=str(e)).model_dump(),
            )
            yield f"data: {json.dumps(error_response.model_dump())}\n\n"

    return StreamingResponse(
        event_generator(), media_type="text/event-stream"
    )


# ============================================================================
# Tool Handlers
# ============================================================================


async def handle_tool_call(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP tool calls."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    logger.info(f"Calling tool: {tool_name} with arguments: {arguments}")

    try:
        if tool_name == "create_session":
            return await tool_create_session()
        elif tool_name == "delete_session":
            return await tool_delete_session(arguments)
        elif tool_name == "get_underlying_price":
            return await tool_get_underlying_price(arguments)
        elif tool_name == "fetch_option_chain":
            return await tool_fetch_option_chain(arguments)
        elif tool_name == "get_session_stats":
            return await tool_get_session_stats()
        elif tool_name == "health_check":
            return await tool_health_check(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error: {str(e)}",
                }
            ],
            "isError": True,
        }


async def tool_create_session() -> Dict[str, Any]:
    """Create a new IBKR session."""
    session_id = session_manager.create_session()
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Created new session: {session_id}\n\n"
                    f"Use this session_id in subsequent tool calls. "
                    f"Session will expire after {settings.session_timeout_minutes} "
                    f"minutes of inactivity."
                ),
            }
        ],
        "session_id": session_id,
    }


async def tool_delete_session(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Delete an IBKR session."""
    session_id = arguments.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")

    success = session_manager.delete_session(session_id)
    if success:
        return {
            "content": [
                {"type": "text", "text": f"Successfully deleted session: {session_id}"}
            ]
        }
    else:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Session not found or already deleted: {session_id}",
                }
            ]
        }


async def tool_get_underlying_price(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Get the current price of an underlying symbol."""
    session_id = arguments.get("session_id")
    symbol = arguments.get("symbol")

    if not session_id or not symbol:
        raise ValueError("session_id and symbol are required")

    session = session_manager.get_session(session_id)
    if not session:
        raise ValueError(
            f"Invalid or expired session: {session_id}. Create a new session first."
        )

    client = session.get_or_create_client()
    price = client.get_underlying_price(symbol)

    if price is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not fetch price for {symbol}. "
                    f"Check that the symbol is valid and market data is available.",
                }
            ]
        }

    return {
        "content": [
            {"type": "text", "text": f"{symbol} current price: ${price:.2f}"}
        ],
        "price": price,
        "symbol": symbol,
    }


async def tool_fetch_option_chain(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch option chain data."""
    session_id = arguments.get("session_id")
    symbol = arguments.get("symbol")
    strike_count = arguments.get("strike_count")
    expiration_days = arguments.get("expiration_days")

    if not session_id or not symbol:
        raise ValueError("session_id and symbol are required")

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

    summary = (
        f"Successfully fetched option chain for {symbol}\n\n"
        f"Underlying Price: ${data['underlying_price']:.2f}\n"
        f"Total Contracts: {data['total_contracts']}\n"
        f"Calls: {data['calls']} | Puts: {data['puts']}\n"
        f"Expirations: {len(data['expirations'])}\n"
        f"Strikes: {len(data['strikes'])}\n\n"
        f"Data includes: bid, ask, last, volume, open interest, "
        f"delta, gamma, theta, vega, implied volatility"
    )

    return {
        "content": [
            {"type": "text", "text": summary},
        ],
        "data": data,
    }


async def tool_get_session_stats() -> Dict[str, Any]:
    """Get session statistics."""
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

    return {
        "content": [{"type": "text", "text": summary}],
        "stats": stats,
    }


async def tool_health_check(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Perform health check."""
    session_id = arguments.get("session_id")

    health_info = {
        "server": "healthy",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "total_sessions": len(session_manager.sessions),
    }

    if session_id:
        session = session_manager.get_session(session_id)
        if session:
            health_info["session"] = {
                "valid": True,
                "connected": (
                    session.client.is_connected if session.client else False
                ),
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

    return {
        "content": [{"type": "text", "text": summary}],
        "health": health_info,
    }


def main() -> None:
    """Run the MCP server."""
    import uvicorn

    logger.info(f"Starting server on {settings.host}:{settings.port}")
    uvicorn.run(
        "mcp_ibkr_options.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
