"""
MCP server with automatic login-based authentication using cookies.
Login happens automatically when cookies are missing.
Server is stateless - checks for cookies on each request.
"""

import os
import httpx
from fastmcp import FastMCP, Context
from fastmcp.server.dependencies import get_http_headers

# Initialize FastMCP server
mcp = FastMCP(name="MDM Server with Auto-Login")

# Base URL for MDM API - can be set via environment variable
MDM_BASE_URL = os.getenv("MDM_BASE_URL", "http://35.91.235.135")

# Credentials from environment variables (fallback)
MDM_USERNAME = os.getenv("MDM_USERNAME", "")
MDM_PASSWORD = os.getenv("MDM_PASSWORD", "")


async def _perform_login(ctx: Context, username: str, password: str) -> dict:
    """
    Perform login to MDM API and store cookies in session state.
    This is called automatically when cookies are missing.
    
    Args:
        ctx: FastMCP Context for accessing session state
        username: Username for authentication
        password: Password for authentication
        
    Returns:
        dict: Cookies dictionary with epimresttoken and ewtoken
        
    Raises:
        ValueError: If required cookies are missing after login
    """
    login_url = f"{MDM_BASE_URL}/enable-api/login"
    params = {
        "login": username,
        "password": password
    }
    
    # Make login request
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.post(login_url, params=params)
        response.raise_for_status()
        
        # Extract cookies from the response
        cookies_dict = {}
        for cookie in response.cookies.jar:
            cookies_dict[cookie.name] = cookie.value
        
        # Also check Set-Cookie headers
        set_cookie_headers = response.headers.get_list("Set-Cookie")
        for cookie_header in set_cookie_headers:
            cookie_parts = cookie_header.split(";")[0].strip()
            if "=" in cookie_parts:
                name, value = cookie_parts.split("=", 1)
                cookies_dict[name.strip()] = value.strip()
        
        # Verify both required cookies are present
        required_cookies = ["epimresttoken", "ewtoken"]
        missing_cookies = [cookie for cookie in required_cookies if cookie not in cookies_dict]
        
        if missing_cookies:
            raise ValueError(
                f"Login successful but required cookies missing: {missing_cookies}. "
                f"Received cookies: {list(cookies_dict.keys())}"
            )
        
        # Store cookies in session state
        await ctx.set_state("api_cookies", cookies_dict)
        
        return cookies_dict


async def _ensure_authenticated(ctx: Context) -> dict:
    """
    Ensure authentication cookies exist in session state.
    If cookies don't exist, automatically perform login using credentials from:
    1. Request headers (X-MDM-Username, X-MDM-Password)
    2. Environment variables (MDM_USERNAME, MDM_PASSWORD)
    
    Args:
        ctx: FastMCP Context for accessing session state
        
    Returns:
        dict: Cookies dictionary with epimresttoken and ewtoken
        
    Raises:
        ValueError: If no credentials available or login fails
    """
    # Check if cookies already exist
    cookies = await ctx.get_state("api_cookies")
    if cookies:
        # Verify both required cookies are present
        if "epimresttoken" in cookies and "ewtoken" in cookies:
            return cookies
    
    # No cookies found - need to login
    # Try to get credentials from request headers first
    request_headers = get_http_headers()
    username = request_headers.get("x-mdm-username") or request_headers.get("X-MDM-Username")
    password = request_headers.get("x-mdm-password") or request_headers.get("X-MDM-Password")
    
    # Fall back to environment variables
    if not username:
        username = MDM_USERNAME
    if not password:
        password = MDM_PASSWORD
    
    if not username or not password:
        raise ValueError(
            "No authentication cookies found and no credentials available. "
            "Provide credentials via 'X-MDM-Username' and 'X-MDM-Password' headers, "
            "or set MDM_USERNAME and MDM_PASSWORD environment variables."
        )
    
    # Perform automatic login
    cookies = await _perform_login(ctx, username, password)
    return cookies


async def _get_authenticated_client(ctx: Context) -> httpx.AsyncClient:
    """
    Get an authenticated HTTP client with cookies from session state.
    Automatically performs login if cookies are missing.
    The client will automatically send both 'epimresttoken' and 'ewtoken' cookies
    in all requests to the MDM API.
    
    Args:
        ctx: FastMCP Context for accessing session state
        
    Returns:
        httpx.AsyncClient: HTTP client with cookies configured (epimresttoken and ewtoken)
    """
    # Ensure we have cookies (auto-login if needed)
    cookies = await _ensure_authenticated(ctx)
    
    # Create HTTP client with cookies
    # httpx.AsyncClient automatically handles cookies when you pass a dict
    client = httpx.AsyncClient(
        timeout=30.0,
        cookies=cookies,
        base_url=MDM_BASE_URL
    )
    
    return client


async def _make_request(
    ctx: Context,
    method: str,
    endpoint: str,
    params: dict | None = None,
    json_data: dict | None = None
) -> dict:
    """
    Helper function to make authenticated HTTP requests to the MDM API.
    Uses cookies stored in session state for authentication.
    Automatically sends both 'epimresttoken' and 'ewtoken' cookies in the request.
    
    Args:
        ctx: FastMCP Context for accessing session state
        method: HTTP method ('GET', 'POST', etc.)
        endpoint: The API endpoint path (e.g., '/webcm/rest/api/repositories')
        params: Optional query parameters as a dictionary
        json_data: Optional JSON body for POST/PUT requests
        
    Returns:
        dict: JSON response from the API
        
    Raises:
        httpx.HTTPError: If the request fails
        ValueError: If not authenticated
    """
    async with await _get_authenticated_client(ctx) as client:
        # Dynamically call the HTTP method on the client
        http_method = getattr(client, method.lower())
        
        # Prepare kwargs based on method
        kwargs = {"params": params} if params else {}
        if json_data and method.upper() in ("POST", "PUT", "PATCH"):
            kwargs["json"] = json_data
        
        # Make the request
        response = await http_method(endpoint, **kwargs)
        response.raise_for_status()
        return response.json()


@mcp.tool
async def list_repositories(ctx: Context) -> dict:
    """
    Fetch a list of all repositories from the MDM platform.
    Authentication is handled automatically - login happens if cookies are missing.
    
    Args:
        ctx: FastMCP Context (automatically injected)
        
    Returns:
        dict: A dictionary containing the list of repositories with their IDs and metadata.
    """
    return await _make_request(ctx, "GET", "/webcm/rest/api/repositories")


@mcp.tool
async def get_repository(ctx: Context, repository_name: str) -> dict:
    """
    Get detailed information about a specific repository by name.
    Authentication is handled automatically - login happens if cookies are missing.
    
    Args:
        ctx: FastMCP Context (automatically injected)
        repository_name: The name of the repository
        
    Returns:
        dict: Repository details including metadata and configuration.
    """
    return await _make_request(
        ctx, 
        "GET", 
        "/webcm/rest/api/repositories", 
        params={"NAME": repository_name}
    )


@mcp.tool
async def get_repository_attributes(ctx: Context, repository_name: str) -> dict:
    """
    Fetch all attributes for a given repository.
    Authentication is handled automatically - login happens if cookies are missing.
    
    Args:
        ctx: FastMCP Context (automatically injected)
        repository_name: The name of the repository
        
    Returns:
        dict: A dictionary containing the list of attributes with their IDs and metadata.
    """
    return await _make_request(
        ctx, 
        "GET", 
        f"/webcm/rest/api/repositories/{repository_name}/attributes"
    )


@mcp.tool
async def get_attribute_values(ctx: Context, repository_name: str, attr_id: str) -> dict:
    """
    Get all values for a specific attribute within a repository.
    Authentication is handled automatically - login happens if cookies are missing.
    
    Args:
        ctx: FastMCP Context (automatically injected)
        repository_name: The name of the repository
        attr_id: The unique identifier of the attribute
        
    Returns:
        dict: A dictionary containing the list of values for the specified attribute.
    """
    return await _make_request(
        ctx, 
        "GET", 
        f"/webcm/rest/api/repositories/{repository_name}/attributes/{attr_id}/values"
    )


@mcp.tool
async def create_item(ctx: Context, repository_name: str, item_data: dict) -> dict:
    """
    Example POST request - Create a new item in a repository.
    Authentication is handled automatically - login happens if cookies are missing.
    
    Args:
        ctx: FastMCP Context (automatically injected)
        repository_name: The name of the repository
        item_data: Dictionary containing item data to create
        
    Returns:
        dict: Response from the API with created item details
    """
    return await _make_request(
        ctx,
        "POST",
        f"/webcm/rest/api/repositories/{repository_name}/items",
        json_data=item_data
    )


if __name__ == "__main__":
    # Run the server with Streamable HTTP transport
    host = os.getenv("MDM_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MDM_SERVER_PORT", "8000"))
    mcp.run(transport="http", host=host, port=port)
