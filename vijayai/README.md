# MDM MCP Server

An MCP (Model Context Protocol) server for fetching product information from an MDM (Master Data Management) platform.

## Features

This server provides tools for interacting with the MDM platform:

1. **list_repositories** - Fetch all available repositories
2. **get_repository** - Get detailed information about a specific repository by name
3. **get_repository_attributes** - Fetch all attributes for a repository
4. **get_attribute_values** - Get all values for a specific attribute in a repository

## Installation

1. Install dependencies:
```bash
pip install -e .
```

Or install directly:
```bash
pip install fastmcp httpx
```

## Configuration

Set environment variables to configure the MDM API connection:

- `MDM_BASE_URL`: Base URL for the MDM API (default: `http://35.91.235.135`)
- `MDM_TOKEN`: Authentication token for the MDM API (required)

Example:
```bash
export MDM_BASE_URL="http://35.91.235.135"
export MDM_TOKEN="your-authentication-token-here"
```

**Note:** You need to generate the token yourself (e.g., via Postman or curl) and set it as the `MDM_TOKEN` environment variable before running the server.

## Usage

### Testing with MCP Inspector (Recommended for Development)

To test your server locally with the MCP Inspector:

1. **Install FastMCP CLI** (if not already installed):
```bash
pip install fastmcp
```

2. **Set your environment variables**:
```bash
export MDM_BASE_URL="http://35.91.235.135"
export MDM_TOKEN="your-authentication-token-here"
```

3. **Run with the inspector**:
```bash
fastmcp dev mdm_server.py
```

This will:
- Start your server with STDIO transport
- Automatically open the MCP Inspector in your browser
- Enable auto-reload when you make code changes

The inspector allows you to:
- View all available tools
- Test each tool with different parameters
- See real-time responses
- Debug your server interactively

**Note:** The `fastmcp dev` command uses STDIO transport by default. The server code automatically detects this.

### Running as Streamable HTTP Server

For production or HTTP-based testing:

1. **Set the transport to HTTP**:
```bash
export MDM_TRANSPORT="http"
export MDM_SERVER_HOST="0.0.0.0"
export MDM_SERVER_PORT="8000"
export MDM_BASE_URL="http://35.91.235.135"
export MDM_TOKEN="your-authentication-token-here"
```

2. **Run the server**:
```bash
python mdm_server.py
```

The server will be available at `http://localhost:8000/mcp` (or your configured host/port).

**Environment Variables for HTTP Transport:**
- `MDM_TRANSPORT`: Set to `"http"` for HTTP transport, `"stdio"` for STDIO (default)
- `MDM_SERVER_HOST`: Host address to bind to (default: `0.0.0.0`)
- `MDM_SERVER_PORT`: Port to bind to (default: `8000`)

## Authentication

The server supports multiple ways to provide the authentication token (in order of priority):

1. **Request Header `X-MDM-Token`** (recommended for testing with Inspector)
   - Pass the token as a custom header: `X-MDM-Token: <your-token>`
   - Works when testing with MCP Inspector or any HTTP client

2. **Cookie Header `epimresttoken`**
   - Pass as: `Cookie: epimresttoken=<your-token>`
   - Useful if your client already uses cookie-based auth

3. **Environment Variable `MDM_TOKEN`** (fallback)
   - Set: `export MDM_TOKEN="your-token-here"`
   - Useful for server-side configuration

**To generate a token:**
- Use Postman to POST to `/enable-api/login?login={user}&password={password}`
- Or use curl: `curl -X POST "http://35.91.235.135/enable-api/login?login=user&password=pass"`

**All API requests will automatically include the token in the `Cookie: epimresttoken={token}` header when calling the MDM API.**

## API Endpoints

The server interacts with the following MDM API endpoints:

**Data Access (all require authentication via MDM_TOKEN):**
- `GET /webcm/rest/api/repositories` - List all repositories
- `GET /webcm/rest/api/repositories?NAME={repository_name}` - Get repository details by name
- `GET /webcm/rest/api/repositories/{repository_name}/attributes` - Get repository attributes
- `GET /webcm/rest/api/repositories/{repository_name}/attributes/{attrId}/values` - Get attribute values

## MCP Client Configuration

### For HTTP/Streamable HTTP Transport

Since the server runs as an HTTP service, clients can connect directly via URL and pass the token in headers:

**Option 1: Using X-MDM-Token header (recommended):**
```json
{
  "mcpServers": {
    "mdm-server": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "X-MDM-Token": "your-mdm-token-here"
      }
    }
  }
}
```

**Option 2: Using Cookie header:**
```json
{
  "mcpServers": {
    "mdm-server": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Cookie": "epimresttoken=your-mdm-token-here"
      }
    }
  }
}
```

**Using FastMCP client library:**
```python
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

transport = StreamableHttpTransport(
    url="http://localhost:8000/mcp",
    headers={
        "X-MDM-Token": "your-mdm-token-here"
    }
)
client = Client(transport)
```

**Testing with MCP Inspector:**
When using the MCP Inspector, you can configure headers in the connection settings. Add:
- Header name: `X-MDM-Token`
- Header value: `your-token-here`

### For STDIO Transport (Alternative)

If you prefer STDIO, modify `mdm_server.py` to use `transport="stdio"` instead of `transport="http"`, then configure:

```json
{
  "mcpServers": {
    "mdm-server": {
      "command": "python",
      "args": ["/path/to/mdm_server.py"],
      "env": {
        "MDM_BASE_URL": "http://35.91.235.135",
        "MDM_TOKEN": "your-authentication-token"
      }
    }
  }
}
```
