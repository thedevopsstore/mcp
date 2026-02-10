"""
MCP server for fetching product information from MDM platform.
Provides tools to interact with repositories, attributes, and values.
"""

import os
import httpx
from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP(name="MDM Product Server")

# Base URL for MDM API - can be set via environment variable
MDM_BASE_URL = os.getenv("MDM_BASE_URL", "http://35.91.235.135")

# Authentication token from environment variable
MDM_TOKEN = os.getenv("MDM_TOKEN", "")


async def _make_request(endpoint: str, params: dict | None = None) -> dict:
    """
    Helper function to make HTTP GET requests to the MDM API.
    
    Args:
        endpoint: The API endpoint path (e.g., '/webcm/rest/api/repositories')
        params: Optional query parameters as a dictionary
        
    Returns:
        dict: JSON response from the API
        
    Raises:
        httpx.HTTPError: If the request fails
        ValueError: If MDM_TOKEN environment variable is not set
    """
    if not MDM_TOKEN:
        raise ValueError("MDM_TOKEN environment variable is not set. Please set it with your authentication token.")
    
    url = f"{MDM_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "Cookie": f"epimresttoken={MDM_TOKEN}"
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
