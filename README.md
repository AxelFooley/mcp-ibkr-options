# MCP IBKR Options

[![CI/CD Pipeline](https://github.com/AxelFooley/mcp-ibkr-options/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/AxelFooley/mcp-ibkr-options/actions/workflows/ci-cd.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-ready Model Context Protocol (MCP) server for fetching real-time option chain data from Interactive Brokers (IBKR). Built with FastAPI, featuring automatic session management, comprehensive error handling, and full Docker support.

## Features

- 🔄 **MCP Protocol Compliant** - Full support for Model Context Protocol over HTTP with SSE streaming
- 📊 **Real-time Option Data** - Fetch live option chains with Greeks (delta, gamma, theta, vega, IV)
- 🔐 **Session Management** - Automatic session cleanup and connection pooling
- 🐳 **Docker Ready** - Multi-stage Dockerfile optimized for production
- 🔧 **Fully Configurable** - All settings configurable via environment variables
- ✅ **Production Ready** - Comprehensive tests, linting, type checking, and CI/CD
- 📈 **Market Data Flexibility** - Support for live, delayed, and frozen market data
- 🎯 **Smart Defaults** - Sensible defaults with easy customization

## Prerequisites

- Python 3.11 or higher
- Interactive Brokers TWS or IB Gateway running and configured
- API connections enabled in TWS/Gateway settings

## Quick Start

### Using Docker (Recommended)

```bash
# Pull the latest image
docker pull ghcr.io/axelfooley/mcp-ibkr-options:latest

# Run the container
docker run -d \
  -p 8000:8000 \
  -e IBKR_HOST=host.docker.internal \
  -e IBKR_PORT=7496 \
  --name mcp-ibkr-options \
  ghcr.io/axelfooley/mcp-ibkr-options:latest
```

### Using Python

```bash
# Clone the repository
git clone https://github.com/AxelFooley/mcp-ibkr-options.git
cd mcp-ibkr-options

# Install dependencies
pip install -e .

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your settings

# Run the server
python -m mcp_ibkr_options.server
```

## Configuration

All configuration is done through environment variables. See `.env.example` for all available options.

### Key Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | MCP server host |
| `PORT` | `8000` | MCP server port |
| `IBKR_HOST` | `127.0.0.1` | IB Gateway/TWS host |
| `IBKR_PORT` | `7496` | IB Gateway/TWS port (7497 for paper) |
| `IBKR_CLIENT_ID` | `1` | Client ID for IB connection |
| `SESSION_TIMEOUT_MINUTES` | `5` | Session inactivity timeout |
| `MARKET_DATA_TYPE` | `4` | 1=live, 2=frozen, 3=delayed, 4=delayed frozen |

## MCP Tools

The server exposes the following MCP tools:

### `create_session`
Create a new IBKR session. Must be called first before using other tools.

**Returns:** `session_id` to use in subsequent calls

### `get_underlying_price`
Get the current price of an underlying symbol.

**Parameters:**
- `session_id` (required): Session ID from `create_session`
- `symbol` (required): Underlying symbol (e.g., SPY, AAPL, SPX)

### `fetch_option_chain`
Fetch complete option chain data with market data and Greeks.

**Parameters:**
- `session_id` (required): Session ID from `create_session`
- `symbol` (required): Underlying symbol
- `strike_count` (optional): Number of strikes above/below current price (default: 20)
- `expiration_days` (optional): Array of days from today for expirations (e.g., [0, 1, 7, 14, 30])

**Returns:** Complete option chain including:
- Bid/Ask/Last prices
- Volume and Open Interest
- Greeks (Delta, Gamma, Theta, Vega)
- Implied Volatility

### `delete_session`
Delete a session and clean up resources.

**Parameters:**
- `session_id` (required): Session ID to delete

### `get_session_stats`
Get statistics about all active sessions.

### `health_check`
Check server and connection health.

**Parameters:**
- `session_id` (optional): Session ID to check specific session health

## Usage Example

### Using MCP Client

```python
import httpx

# MCP server URL
base_url = "http://localhost:8000"

# Create a session
response = httpx.post(
    f"{base_url}/mcp",
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "create_session",
            "arguments": {}
        }
    }
)
session_id = response.json()["result"]["session_id"]

# Fetch option chain for SPY
response = httpx.post(
    f"{base_url}/mcp",
    json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "fetch_option_chain",
            "arguments": {
                "session_id": session_id,
                "symbol": "SPY",
                "strike_count": 10,
                "expiration_days": [0, 7, 14, 30]
            }
        }
    }
)
option_data = response.json()["result"]["data"]
print(f"Fetched {option_data['total_contracts']} contracts")

# Clean up
httpx.post(
    f"{base_url}/mcp",
    json={
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "delete_session",
            "arguments": {"session_id": session_id}
        }
    }
)
```

### Using curl

```bash
# Create session
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "create_session",
      "arguments": {}
    }
  }'

# Fetch option chain
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "fetch_option_chain",
      "arguments": {
        "session_id": "YOUR_SESSION_ID",
        "symbol": "SPY",
        "strike_count": 10
      }
    }
  }'
```

## Development

### Setup Development Environment

```bash
# Clone and install with dev dependencies
git clone https://github.com/AxelFooley/mcp-ibkr-options.git
cd mcp-ibkr-options
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_server.py
```

### Code Quality

```bash
# Lint with ruff
ruff check src/ tests/

# Format with black
black src/ tests/

# Type check with mypy
mypy src/
```

## Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  mcp-ibkr-options:
    image: ghcr.io/axelfooley/mcp-ibkr-options:latest
    ports:
      - "8000:8000"
    environment:
      - IBKR_HOST=host.docker.internal
      - IBKR_PORT=7496
      - SESSION_TIMEOUT_MINUTES=5
      - LOG_LEVEL=INFO
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-ibkr-options
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-ibkr-options
  template:
    metadata:
      labels:
        app: mcp-ibkr-options
    spec:
      containers:
      - name: mcp-ibkr-options
        image: ghcr.io/axelfooley/mcp-ibkr-options:latest
        ports:
        - containerPort: 8000
        env:
        - name: IBKR_HOST
          value: "ibkr-gateway-service"
        - name: IBKR_PORT
          value: "7496"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
```

## Architecture

```
┌─────────────────┐
│   MCP Client    │
│  (AI Agent)     │
└────────┬────────┘
         │ HTTP/SSE
         │
┌────────▼────────────────────┐
│   FastAPI Server            │
│  ┌──────────────────────┐   │
│  │  MCP Protocol Layer  │   │
│  └──────────┬───────────┘   │
│             │                │
│  ┌──────────▼───────────┐   │
│  │  Session Manager     │   │
│  │  (Auto-cleanup)      │   │
│  └──────────┬───────────┘   │
│             │                │
│  ┌──────────▼───────────┐   │
│  │   IBKR Client        │   │
│  │   (ib_insync)        │   │
│  └──────────┬───────────┘   │
└─────────────┼───────────────┘
              │
     ┌────────▼────────┐
     │  IB Gateway/TWS │
     └─────────────────┘
```

## Session Management

The server implements automatic session management with the following features:

- **Session Creation**: Each client gets a unique session ID
- **Connection Pooling**: IBKR connections are reused within sessions
- **Auto-cleanup**: Inactive sessions are automatically removed after timeout
- **Reconnection**: Automatic reconnection on connection failures
- **Thread Safety**: Safe concurrent access to shared resources

## Error Handling

The server provides comprehensive error handling:

- Invalid session IDs return clear error messages
- IBKR connection failures trigger reconnection attempts
- Market data errors include troubleshooting suggestions
- All errors follow MCP error response format

## CI/CD Pipeline

The project includes a complete GitHub Actions pipeline:

1. **Lint & Test** (runs on every push and PR)
   - Linting with Ruff
   - Formatting check with Black
   - Type checking with MyPy
   - Unit and integration tests with Pytest
   - **Pipeline fails if any step fails** ✅

2. **Build & Push** (runs on push to main)
   - Multi-platform Docker build (amd64, arm64)
   - Push to GitHub Container Registry
   - Automatic tagging (latest, sha, branch)

## Troubleshooting

### Connection Refused
- Ensure TWS/IB Gateway is running
- Check that API connections are enabled in TWS settings
- Verify correct host and port in configuration

### Market Data Errors
- Try `MARKET_DATA_TYPE=3` or `4` for delayed/frozen data
- Live data requires market data subscriptions
- Check TWS: Account → Market Data Subscriptions

### Session Expired
- Sessions expire after inactivity (default 5 minutes)
- Create a new session with `create_session`
- Adjust `SESSION_TIMEOUT_MINUTES` if needed

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all tests pass: `pytest`
5. Ensure linting passes: `ruff check src/ tests/`
6. Submit a pull request

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- IBKR integration via [ib_insync](https://github.com/erdewit/ib_insync)
- MCP protocol implementation based on [Model Context Protocol](https://modelcontextprotocol.io/)

## Support

For issues and questions:
- GitHub Issues: https://github.com/AxelFooley/mcp-ibkr-options/issues
- Documentation: See this README and inline code documentation

---

**Note**: This server requires an active Interactive Brokers account and TWS/IB Gateway installation. Market data subscriptions may be required for certain symbols and data types.
