# MDM Server Code Documentation

This document provides a comprehensive explanation of the `mdm_server.py` file, which implements an MCP (Model Context Protocol) server for fetching product information from an MDM (Master Data Management) platform.

## Table of Contents

1. [Overview](#overview)
2. [Imports and Dependencies](#imports-and-dependencies)
3. [Configuration](#configuration)
4. [Core Functions](#core-functions)
5. [MCP Tools](#mcp-tools)
6. [Server Execution](#server-execution)
7. [Authentication Flow](#authentication-flow)
8. [API Endpoints](#api-endpoints)
9. [Usage Examples](#usage-examples)

---

## Overview

The `mdm_server.py` file creates an MCP server that acts as a bridge between MCP clients (like LLMs or development tools) and an MDM platform's REST API. It provides four tools that allow clients to:

- List all repositories
- Get details about a specific repository
- Fetch attributes for a repository
- Get values for specific attributes

The server uses FastMCP framework and communicates with the MDM API using HTTP GET requests with cookie-based authentication.

---

## Imports and Dependencies

```python
import os
import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
```

### Explanation:

- **`os`**: Standard library for accessing environment variables and system configuration
- **`httpx`**: Async HTTP client library used to make GET requests to the MDM API
- **`FastMCP`**: The main FastMCP class for creating MCP servers
- **`get_http_headers`**: FastMCP dependency function that extracts HTTP headers from incoming client requests

---

## Configuration

```python
# Initialize FastMCP server
mcp = FastMCP(name="MDM Product Server")

# Base URL for MDM API - can be set via environment variable
MDM_BASE_URL = os.getenv("MDM_BASE_URL", "http://35.91.235.135")

# Authentication token from environment variable
MDM_TOKEN = os.getenv("MDM_TOKEN", "")
```

### Explanation:

1. **`mcp = FastMCP(name="MDM Product Server")`**
   - Creates a new FastMCP server instance
   - The name "MDM Product Server" is used for identification in MCP clients
   - This instance will hold all the tools and handle MCP protocol communication

2. **`MDM_BASE_URL`**
   - Base URL for the MDM API endpoint
   - Reads from `MDM_BASE_URL` environment variable
   - Defaults to `"http://35.91.235.135"` if not set
   - Used to construct full API endpoint URLs

3. **`MDM_TOKEN`**
   - Authentication token for the MDM API
   - Reads from `MDM_TOKEN` environment variable
   - Defaults to empty string if not set
   - Used as fallback when no token is provided in request headers

---

## Core Functions

### `_make_request(endpoint: str, params: dict | None = None) -> dict`

This is the core helper function that handles all HTTP requests to the MDM API.

#### Parameters:
- **`endpoint`**: The API endpoint path (e.g., `/webcm/rest/api/repositories`)
- **`params`**: Optional dictionary of query parameters to append to the URL

#### Return Value:
- Returns a dictionary containing the JSON response from the MDM API

#### Function Flow:

1. **Token Resolution (Lines 41-67)**
   ```python
   request_headers = get_http_headers()
   token = None
   ```
   - Gets HTTP headers from the incoming MCP client request
   - Attempts to extract authentication token in this priority order:
     
     **Priority 1: `X-MDM-Token` header**
     ```python
     if "x-mdm-token" in request_headers:
         token = request_headers["x-mdm-token"]
     ```
     - Checks for custom header `X-MDM-Token` (case-insensitive)
     - This allows clients to pass token directly in headers
     
     **Priority 2: Cookie header with `epimresttoken`**
     ```python
     elif "cookie" in request_headers:
         cookie_header = request_headers["cookie"]
         for cookie in cookie_header.split(";"):
             cookie = cookie.strip()
             if cookie.startswith("epimresttoken="):
                 token = cookie.split("=", 1)[1]
                 break
     ```
     - Parses the Cookie header to find `epimresttoken=<token>`
     - Handles multiple cookies separated by semicolons
     - Extracts the token value after the `=` sign
     
     **Priority 3: Environment variable fallback**
     ```python
     if not token:
         token = MDM_TOKEN
     ```
     - Uses the `MDM_TOKEN` environment variable if no header token found
     - Useful for server-side configuration

2. **Token Validation (Lines 62-67)**
   ```python
   if not token:
       raise ValueError("No authentication token found...")
   ```
   - Raises an error if no token is available from any source
   - Provides helpful error message with all available options

3. **URL Construction (Line 69)**
   ```python
   url = f"{MDM_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
   ```
   - Combines base URL with endpoint path
   - `rstrip('/')` removes trailing slash from base URL
   - `lstrip('/')` removes leading slash from endpoint
   - Prevents double slashes in the final URL

4. **Request Headers (Lines 70-72)**
   ```python
   headers = {
       "Cookie": f"epimresttoken={token}"
   }
   ```
   - Creates headers dictionary with the MDM API's required cookie format
   - The MDM API expects authentication via `Cookie: epimresttoken=<token>`

5. **HTTP Request (Lines 74-77)**
   ```python
   async with httpx.AsyncClient(timeout=30.0) as client:
       response = await client.get(url, headers=headers, params=params)
       response.raise_for_status()
       return response.json()
   ```
   - Creates an async HTTP client with 30-second timeout
   - Makes GET request to the constructed URL
   - `params` are automatically converted to query string parameters
   - `raise_for_status()` raises an exception for HTTP error status codes (4xx, 5xx)
   - Returns parsed JSON response as a dictionary

---

## MCP Tools

The server exposes four MCP tools that clients can call. Each tool is decorated with `@mcp.tool`, which registers it with the FastMCP server.

### 1. `list_repositories() -> dict`

**Purpose**: Fetches a list of all available repositories from the MDM platform.

**Implementation**:
```python
@mcp.tool
async def list_repositories() -> dict:
    return await _make_request("/webcm/rest/api/repositories")
```

**API Endpoint**: `GET /webcm/rest/api/repositories`

**Returns**: Dictionary containing list of repositories with their IDs and metadata.

**Example Response**:
```json
{
  "repositories": [
    {"id": "repo1", "name": "Products", ...},
    {"id": "repo2", "name": "Categories", ...}
  ]
}
```

---

### 2. `get_repository(repository_name: str) -> dict`

**Purpose**: Gets detailed information about a specific repository by name.

**Parameters**:
- **`repository_name`**: The name of the repository to retrieve

**Implementation**:
```python
@mcp.tool
async def get_repository(repository_name: str) -> dict:
    return await _make_request("/webcm/rest/api/repositories", params={"NAME": repository_name})
```

**API Endpoint**: `GET /webcm/rest/api/repositories?NAME={repository_name}`

**Returns**: Dictionary containing repository details including metadata and configuration.

**Example Usage**:
```python
# Client calls:
get_repository(repository_name="Products")

# Results in API call:
# GET http://35.91.235.135/webcm/rest/api/repositories?NAME=Products
```

---

### 3. `get_repository_attributes(repository_name: str) -> dict`

**Purpose**: Fetches all attributes defined for a given repository.

**Parameters**:
- **`repository_name`**: The name of the repository

**Implementation**:
```python
@mcp.tool
async def get_repository_attributes(repository_name: str) -> dict:
    return await _make_request(f"/webcm/rest/api/repositories/{repository_name}/attributes")
```

**API Endpoint**: `GET /webcm/rest/api/repositories/{repository_name}/attributes`

**Returns**: Dictionary containing list of attributes with their IDs and metadata.

**Example Usage**:
```python
# Client calls:
get_repository_attributes(repository_name="Products")

# Results in API call:
# GET http://35.91.235.135/webcm/rest/api/repositories/Products/attributes
```

---

### 4. `get_attribute_values(repository_name: str, attr_id: str) -> dict`

**Purpose**: Gets all values for a specific attribute within a repository.

**Parameters**:
- **`repository_name`**: The name of the repository
- **`attr_id`**: The unique identifier of the attribute

**Implementation**:
```python
@mcp.tool
async def get_attribute_values(repository_name: str, attr_id: str) -> dict:
    return await _make_request(f"/webcm/rest/api/repositories/{repository_name}/attributes/{attr_id}/values")
```

**API Endpoint**: `GET /webcm/rest/api/repositories/{repository_name}/attributes/{attr_id}/values`

**Returns**: Dictionary containing list of values for the specified attribute.

**Example Usage**:
```python
# Client calls:
get_attribute_values(repository_name="Products", attr_id="color")

# Results in API call:
# GET http://35.91.235.135/webcm/rest/api/repositories/Products/attributes/color/values
```

---

## Server Execution

```python
if __name__ == "__main__":
    # Run the server with Streamable HTTP transport
    host = os.getenv("MDM_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MDM_SERVER_PORT", "8000"))
    mcp.run(transport="http", host=host, port=port)
```

### Explanation:

1. **`if __name__ == "__main__":`**
   - Ensures this code only runs when the script is executed directly
   - Prevents execution when imported as a module

2. **Host Configuration**:
   ```python
   host = os.getenv("MDM_SERVER_HOST", "0.0.0.0")
   ```
   - Reads host from `MDM_SERVER_HOST` environment variable
   - Defaults to `"0.0.0.0"` (listens on all network interfaces)
   - Use `"127.0.0.1"` for localhost-only access

3. **Port Configuration**:
   ```python
   port = int(os.getenv("MDM_SERVER_PORT", "8000"))
   ```
   - Reads port from `MDM_SERVER_PORT` environment variable
   - Defaults to `8000`
   - Converts to integer (environment variables are strings)

4. **Server Start**:
   ```python
   mcp.run(transport="http", host=host, port=port)
   ```
   - Starts the MCP server with Streamable HTTP transport
   - Server becomes accessible at `http://{host}:{port}/mcp`
   - Handles MCP protocol communication over HTTP
   - Supports multiple concurrent client connections

---

## Authentication Flow

The server implements a flexible authentication system with three methods (in priority order):

### Method 1: Request Header `X-MDM-Token`

**When to use**: Testing with MCP Inspector or HTTP clients

**How it works**:
1. Client sends request with header: `X-MDM-Token: <token>`
2. `get_http_headers()` extracts the header
3. Token is used for MDM API authentication

**Example**:
```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-MDM-Token: your-token-here" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", ...}'
```

### Method 2: Cookie Header `epimresttoken`

**When to use**: When client already uses cookie-based authentication

**How it works**:
1. Client sends request with header: `Cookie: epimresttoken=<token>`
2. Server parses the cookie string
3. Extracts token value and uses it for MDM API

**Example**:
```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Cookie: epimresttoken=your-token-here" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", ...}'
```

### Method 3: Environment Variable `MDM_TOKEN`

**When to use**: Server-side configuration, production deployments

**How it works**:
1. Set environment variable: `export MDM_TOKEN="your-token"`
2. Server reads it if no header token is found
3. Used as fallback authentication method

**Example**:
```bash
export MDM_TOKEN="your-token-here"
python mdm_server.py
```

### Token Flow Diagram

```
Client Request
    ↓
[Check X-MDM-Token header]
    ↓ (not found)
[Check Cookie: epimresttoken]
    ↓ (not found)
[Check MDM_TOKEN env var]
    ↓
Token Found → Use in MDM API Request
    ↓
MDM API Response
```

---

## API Endpoints

The server makes requests to the following MDM API endpoints:

| Tool | HTTP Method | Endpoint | Query Params |
|------|-------------|----------|-------------|
| `list_repositories` | GET | `/webcm/rest/api/repositories` | None |
| `get_repository` | GET | `/webcm/rest/api/repositories` | `NAME={repository_name}` |
| `get_repository_attributes` | GET | `/webcm/rest/api/repositories/{repository_name}/attributes` | None |
| `get_attribute_values` | GET | `/webcm/rest/api/repositories/{repository_name}/attributes/{attr_id}/values` | None |

### Base URL Construction

All endpoints are prefixed with the `MDM_BASE_URL`:

```
{MDM_BASE_URL}/webcm/rest/api/...
```

Example:
- Base URL: `http://35.91.235.135`
- Endpoint: `/webcm/rest/api/repositories`
- Full URL: `http://35.91.235.135/webcm/rest/api/repositories`

### Authentication

All MDM API requests include:
```
Cookie: epimresttoken={token}
```

---

## Usage Examples

### Example 1: Running the Server

```bash
# Set environment variables
export MDM_BASE_URL="http://35.91.235.135"
export MDM_TOKEN="your-token-here"
export MDM_SERVER_HOST="0.0.0.0"
export MDM_SERVER_PORT="8000"

# Start the server
python mdm_server.py
```

Server will be available at: `http://localhost:8000/mcp`

### Example 2: Testing with MCP Inspector

1. **Start the server**:
   ```bash
   python mdm_server.py
   ```

2. **Open MCP Inspector** (if installed):
   ```bash
   npx @modelcontextprotocol/inspector
   ```

3. **Connect to server**:
   - URL: `http://localhost:8000/mcp`
   - Add header: `X-MDM-Token: your-token-here`

4. **Test a tool**:
   - Select `list_repositories`
   - Click "Call Tool"
   - View the response

### Example 3: Using with FastMCP Client

```python
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

# Create transport with authentication header
transport = StreamableHttpTransport(
    url="http://localhost:8000/mcp",
    headers={
        "X-MDM-Token": "your-token-here"
    }
)

# Create client and use tools
async with Client(transport) as client:
    # List repositories
    repos = await client.call_tool("list_repositories", {})
    print(repos)
    
    # Get specific repository
    repo = await client.call_tool("get_repository", {
        "repository_name": "Products"
    })
    print(repo)
```

### Example 4: Error Handling

The server raises errors in these scenarios:

1. **No token available**:
   ```python
   ValueError: No authentication token found. Provide token via 
   'X-MDM-Token' header, 'Cookie: epimresttoken=<token>' header, 
   or set MDM_TOKEN environment variable.
   ```

2. **HTTP errors from MDM API**:
   ```python
   httpx.HTTPError: 401 Unauthorized  # Invalid token
   httpx.HTTPError: 404 Not Found     # Repository not found
   httpx.HTTPError: 500 Server Error  # MDM API error
   ```

---

## Summary

The `mdm_server.py` file implements a complete MCP server that:

1. **Connects MCP clients to MDM API**: Provides a standardized interface for LLMs and tools to access MDM data
2. **Handles authentication flexibly**: Supports header-based, cookie-based, and environment variable authentication
3. **Exposes four tools**: For listing repositories, getting repository details, fetching attributes, and retrieving attribute values
4. **Uses async HTTP**: Leverages `httpx` for efficient async API calls
5. **Runs as HTTP server**: Uses Streamable HTTP transport for network accessibility

The code is designed to be:
- **Flexible**: Multiple authentication methods
- **Robust**: Error handling and validation
- **Simple**: Clear function structure and documentation
- **Production-ready**: Environment-based configuration
