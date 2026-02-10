"""
MCP server for fetching product information from MDM platform.
Provides tools to interact with repositories, attributes, and values.
"""

import os
import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

# Initialize FastMCP server
mcp = FastMCP(name="MDM Product Server")

# Base URL for MDM API - can be set via environment variable
MDM_BASE_URL = os.getenv("MDM_BASE_URL", "http://35.91.235.135")

# Authentication token from environment variable
MDM_TOKEN = os.getenv("MDM_TOKEN", "")


async def _make_request(endpoint: str, params: dict | None = None) -> dict:
    """
    Helper function to make HTTP GET requests to the MDM API.
    
    Gets the authentication token from:
    1. Request header 'X-MDM-Token' (if provided by client)
    2. Request Cookie header 'epimresttoken' (if provided by client)
    3. Environment variable MDM_TOKEN (fallback)
    
    Args:
        endpoint: The API endpoint path (e.g., '/webcm/rest/api/repositories')
        params: Optional query parameters as a dictionary
        
    Returns:
        dict: JSON response from the API
        
    Raises:
        httpx.HTTPError: If the request fails
        ValueError: If no token is available from any source
    """
    # Try to get token from request headers first
    request_headers = get_http_headers()
    token = None
    
    # Check for X-MDM-Token header
    if "x-mdm-token" in request_headers:
        token = request_headers["x-mdm-token"]
    # Check for Cookie header with epimresttoken
    elif "cookie" in request_headers:
        cookie_header = request_headers["cookie"]
        # Parse cookie to find epimresttoken
        for cookie in cookie_header.split(";"):
            cookie = cookie.strip()
            if cookie.startswith("epimresttoken="):
                token = cookie.split("=", 1)[1]
                break
    
    # Fall back to environment variable if no header token found
    if not token:
        token = MDM_TOKEN
    
    if not token:
        raise ValueError(
            "No authentication token found. "
            "Provide token via 'X-MDM-Token' header, 'Cookie: epimresttoken=<token>' header, "
            "or set MDM_TOKEN environment variable."
        )
    
    url = f"{MDM_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "Cookie": f"epimresttoken={token}"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


@mcp.tool
async def list_repositories() -> dict:
    """
    Fetch a list of all repositories from the MDM platform.
    
    Returns:
        dict: A dictionary containing the list of repositories with their IDs and metadata.
    """
    return await _make_request("/webcm/rest/api/repositories")


@mcp.tool
async def get_repository(repository_name: str) -> dict:
    """
    Get detailed information about a specific repository by name.
    
    Args:
        repository_name: The name of the repository
        
    Returns:
        dict: Repository details including metadata and configuration.
    """
    return await _make_request("/webcm/rest/api/repositories", params={"NAME": repository_name})


@mcp.tool
async def get_repository_attributes(repository_name: str) -> dict:
    """
    Fetch all attributes for a given repository.
    
    Args:
        repository_name: The name of the repository
        
    Returns:
        dict: A dictionary containing the list of attributes with their IDs and metadata.
    """
    return await _make_request(f"/webcm/rest/api/repositories/{repository_name}/attributes")


@mcp.tool
async def get_attribute_values(repository_name: str, attr_id: str) -> dict:
    """
    Get all values for a specific attribute within a repository.
    
    Args:
        repository_name: The name of the repository
        attr_id: The unique identifier of the attribute
        
    Returns:
        dict: A dictionary containing the list of values for the specified attribute.
    """
    return await _make_request(f"/webcm/rest/api/repositories/{repository_name}/attributes/{attr_id}/values")


if __name__ == "__main__":
    # Run the server with Streamable HTTP transport
    host = os.getenv("MDM_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MDM_SERVER_PORT", "8000"))
    mcp.run(transport="http", host=host, port=port)
