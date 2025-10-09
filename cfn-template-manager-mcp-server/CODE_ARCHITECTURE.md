# CloudFormation Template Manager MCP Server - Code Architecture

## 📁 Project Structure

```
cfn-template-manager-mcp-server/
├── awslabs/
│   └── cfn_template_manager/
│       ├── __init__.py              # Package initialization
│       ├── server.py                # FastMCP server entry point
│       └── tools.py                 # Core business logic (800+ lines)
├── pyproject.toml                   # Package dependencies & metadata
├── Dockerfile                       # Container image definition
├── README.md                        # User documentation
└── CODE_ARCHITECTURE.md            # This file
```

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     FastMCP Server                          │
│                    (server.py)                              │
│  - HTTP/SSE endpoints                                       │
│  - Tool registration                                        │
│  - Request/response handling                                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              CFNTemplateManagerTools                        │
│                   (tools.py)                                │
│  - MCP tool decorators                                      │
│  - Tool registration                                        │
│  - Wraps CloudFormationTemplateManager                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         CloudFormationTemplateManager                       │
│                   (tools.py)                                │
│  - Core business logic                                      │
│  - AWS CloudFormation operations                            │
│  - Uses TemplateRepository                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              TemplateRepository                             │
│                   (tools.py)                                │
│  - Git repository management                                │
│  - Template file discovery                                  │
│  - Template parsing (YAML/JSON)                             │
└─────────────────────────────────────────────────────────────┘
```

## 📝 File-by-File Breakdown

### 1. `server.py` (55 lines)

**Purpose:** FastMCP server initialization and entry point

```python
# Key Components:

mcp = FastMCP(
    'awslabs.cfn-template-manager-mcp-server',
    stateless_http=True,
    instructions='...',  # Server instructions for AI agents
    dependencies=[...]   # Python package dependencies
)

# Tool registration
cfn_tools = CFNTemplateManagerTools()
cfn_tools.register(mcp)

# Server entry point
def main():
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**Responsibilities:**
- Initialize FastMCP server
- Register tools
- Start HTTP server with uvicorn
- Provide server metadata

**Entry Points:**
- `main()` - CLI entry point
- `mcp.streamable_http_app()` - Returns ASGI app

### 2. `tools.py` (800+ lines)

The main implementation file with three key classes:

---

#### **Class 1: `TemplateRepository`**

**Purpose:** Manages CloudFormation template repository (Git or local)

```python
class TemplateRepository:
    def __init__(self, repo_url: Optional[str], local_path: Optional[str])
    
    # Git operations
    def _clone_or_update_repo(self)
    
    # Discovery
    def list_resources(self) -> List[str]
    def get_template_path(self, resource_type: str) -> str
    
    # Template reading
    def read_template(self, resource_type: str) -> Dict[str, Any]
    def get_template_body(self, resource_type: str) -> str
```

**Key Methods:**

| Method | Purpose | Returns |
|--------|---------|---------|
| `_clone_or_update_repo()` | Clone or pull Git repository | None |
| `list_resources()` | List all resource type directories | `List[str]` |
| `get_template_path()` | Find template file in directory | `str` (file path) |
| `read_template()` | Parse YAML/JSON template | `Dict` (parsed template) |
| `get_template_body()` | Get raw template content | `str` (raw content) |

**Data Flow:**
```
Git Repo → Clone/Pull → Local Directory → 
Discover Directories → Find Template Files → 
Parse YAML/JSON → Return Data
```

**File Discovery Logic:**
```python
# Looks for these files in order:
1. template.yaml
2. template.yml
3. cloudformation.yaml
4. cloudformation.yml
5. template.json
```

---

#### **Class 2: `CloudFormationTemplateManager`**

**Purpose:** Core business logic for CloudFormation operations

```python
class CloudFormationTemplateManager:
    def __init__(self, repo_url, local_path, region_name)
    
    # Discovery
    def list_available_resources(self) -> Dict[str, Any]
    def get_template_info(self, resource_type: str) -> Dict[str, Any]
    def get_template_parameters(self, resource_type: str) -> Dict[str, Any]
    
    # Validation
    def validate_parameters(self, resource_type: str, parameters: Dict) -> Dict[str, Any]
    
    # CloudFormation operations
    def create_change_set(self, resource_type: str, ...) -> Dict[str, Any]
    def describe_change_set(self, change_set_name: str, ...) -> Dict[str, Any]
    def execute_change_set(self, change_set_name: str, ...) -> Dict[str, Any]
    def get_stack_status(self, stack_name: str) -> Dict[str, Any]
    def delete_stack(self, stack_name: str, ...) -> Dict[str, Any]
```

**Dependencies:**
- `boto3.client('cloudformation')` - AWS CloudFormation API
- `TemplateRepository` - Template management

**Method Categories:**

**A. Discovery Methods**
```python
list_available_resources()
├─> repository.list_resources()
└─> Returns: {"success": bool, "resources": list, "count": int}

get_template_info(resource_type)
├─> repository.read_template(resource_type)
├─> Extract: parameters, resources, outputs
└─> Returns: {"success": bool, "description": str, ...}

get_template_parameters(resource_type)
├─> repository.read_template(resource_type)
├─> Parse Parameters section
├─> Extract: type, description, defaults, constraints
└─> Returns: {"success": bool, "parameters": dict, "required_parameters": list}
```

**B. Validation Methods**
```python
validate_parameters(resource_type, parameters)
├─> get_template_parameters(resource_type)
├─> Check: required parameters present
├─> Check: unknown parameters (warnings)
├─> Validate: allowed values, patterns, min/max
└─> Returns: {"success": bool, "valid": bool, "errors": list, "warnings": list}
```

**C. CloudFormation Operations**
```python
create_change_set(resource_type, parameters, stack_name, change_set_type)
├─> validate_parameters()  # Pre-validation
├─> repository.get_template_body()
├─> Format parameters for CFN
├─> cfn_client.create_change_set()
└─> Returns: {"success": bool, "change_set_id": str, ...}

describe_change_set(change_set_name, stack_name)
├─> cfn_client.describe_change_set()
├─> Parse changes (Add/Modify/Remove)
├─> Extract: action, resource type, logical ID
└─> Returns: {"success": bool, "changes": list, ...}

execute_change_set(change_set_name, stack_name, wait)
├─> cfn_client.execute_change_set()
├─> [Optional] Wait for completion
└─> Returns: {"success": bool, "message": str}

get_stack_status(stack_name)
├─> cfn_client.describe_stacks()
├─> Extract: status, outputs, parameters
└─> Returns: {"success": bool, "status": str, "outputs": list}

delete_stack(stack_name, wait)
├─> cfn_client.delete_stack()
├─> [Optional] Wait for deletion
└─> Returns: {"success": bool, "message": str}
```

**Error Handling Pattern:**
```python
try:
    # AWS operation
    result = cfn_client.some_operation()
    return {"success": True, "data": result}
except ClientError as e:
    logger.error(f"AWS error: {str(e)}")
    return {"success": False, "error": str(e)}
except Exception as e:
    logger.error(f"Error: {str(e)}")
    return {"success": False, "error": str(e)}
```

---

#### **Class 3: `CFNTemplateManagerTools`**

**Purpose:** MCP tool registration wrapper

```python
class CFNTemplateManagerTools:
    def __init__(self, repo_url, local_path, region_name):
        self.manager = CloudFormationTemplateManager(...)
    
    def register(self, mcp):
        # Registers 9 MCP tools
        @mcp.tool()
        def list_available_resources() -> Dict[str, Any]:
            return self.manager.list_available_resources()
        
        # ... 8 more tools
```

**Pattern:**
```python
@mcp.tool()
def tool_name(param1: Type1, param2: Type2) -> Dict[str, Any]:
    """
    Tool description for AI agents.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns description of what this returns.
    """
    return self.manager.corresponding_method(param1, param2)
```

**All 9 Tools:**

| Tool | Manager Method | Purpose |
|------|---------------|---------|
| `list_available_resources()` | `list_available_resources()` | List resource types |
| `get_template_info(resource_type)` | `get_template_info()` | Get template overview |
| `get_template_parameters(resource_type)` | `get_template_parameters()` | Get parameter details |
| `validate_parameters(resource_type, params)` | `validate_parameters()` | Validate parameters |
| `create_change_set(...)` | `create_change_set()` | Create change set |
| `describe_change_set(...)` | `describe_change_set()` | Describe change set |
| `execute_change_set(...)` | `execute_change_set()` | Execute change set |
| `get_stack_status(stack_name)` | `get_stack_status()` | Get stack status |
| `delete_stack(stack_name, wait)` | `delete_stack()` | Delete stack |

---

## 🔄 Request Flow

### Example: Creating a Stack

```
1. AI Agent Request
   ↓
2. FastMCP Server (server.py)
   - Receives HTTP/SSE request
   - Routes to tool: create_change_set
   ↓
3. CFNTemplateManagerTools (tools.py)
   - @mcp.tool() decorator
   - Calls: self.manager.create_change_set(...)
   ↓
4. CloudFormationTemplateManager (tools.py)
   - Validates parameters
   - Calls: repository.get_template_body()
   ↓
5. TemplateRepository (tools.py)
   - Reads template file
   - Returns: template content
   ↓
6. CloudFormationTemplateManager (tools.py)
   - Calls: boto3 cfn_client.create_change_set()
   ↓
7. AWS CloudFormation API
   - Creates change set
   - Returns: change set ID
   ↓
8. Response flows back up
   - CloudFormationTemplateManager formats response
   - CFNTemplateManagerTools returns to FastMCP
   - FastMCP sends HTTP/SSE response to agent
```

## 📊 Data Structures

### Template Structure (CloudFormation)

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Template description'

Parameters:
  ParameterName:
    Type: String
    Description: 'Parameter description'
    Default: 'value'
    AllowedValues: [...]
    AllowedPattern: 'regex'
    MinLength: 1
    MaxLength: 255

Resources:
  LogicalResourceId:
    Type: AWS::Service::Resource
    Properties:
      # ...

Outputs:
  OutputName:
    Description: 'Output description'
    Value: !Ref ResourceId
```

### Response Structure (All Methods)

```python
{
    "success": bool,        # Operation succeeded?
    
    # On success:
    "data": Any,           # Method-specific data
    "message": str,        # Human-readable message
    
    # On failure:
    "error": str,          # Error message
    
    # Method-specific fields:
    "resources": List[str],     # list_available_resources
    "parameters": Dict,         # get_template_parameters
    "valid": bool,             # validate_parameters
    "errors": List[str],       # validate_parameters
    "warnings": List[str],     # validate_parameters
    "change_set_id": str,      # create_change_set
    "changes": List[Dict],     # describe_change_set
    "status": str,             # get_stack_status
    "outputs": List[Dict],     # get_stack_status
}
```

## 🔧 Configuration

### Environment Variables

```python
# Template source (choose one)
CFN_TEMPLATE_REPO_URL      # Git repository URL
CFN_TEMPLATE_LOCAL_PATH    # Local directory path

# AWS configuration
AWS_REGION                 # AWS region (default: us-east-1)
AWS_ACCESS_KEY_ID         # AWS credentials
AWS_SECRET_ACCESS_KEY     # AWS credentials
AWS_SESSION_TOKEN         # Optional: temporary credentials
AWS_PROFILE               # Optional: AWS CLI profile

# Logging
LOG_LEVEL                 # DEBUG, INFO, WARNING, ERROR
```

### Initialization Sequence

```python
1. server.py imports tools
2. CFNTemplateManagerTools.__init__()
   ├─> CloudFormationTemplateManager.__init__()
   │   ├─> Read environment variables
   │   ├─> Initialize boto3 CloudFormation client
   │   └─> TemplateRepository.__init__()
   │       ├─> Read CFN_TEMPLATE_REPO_URL or CFN_TEMPLATE_LOCAL_PATH
   │       └─> Clone/update Git repo if URL provided
   └─> Ready to register tools
3. cfn_tools.register(mcp)
   └─> Registers all 9 tools with FastMCP
4. main() starts uvicorn server
```

## 🧪 Testing Strategy

### Unit Tests (Recommended Structure)

```python
tests/
├── test_template_repository.py
│   ├── test_list_resources()
│   ├── test_get_template_path()
│   ├── test_read_template()
│   └── test_git_operations()
│
├── test_cfn_manager.py
│   ├── test_list_available_resources()
│   ├── test_get_template_info()
│   ├── test_get_template_parameters()
│   ├── test_validate_parameters()
│   └── test_change_set_operations()
│
└── test_integration.py
    └── test_full_workflow()
```

### Current Test File

`test_cfn_mcp_server.py` (in project root) provides:
- Integration tests
- Dry-run workflow tests
- No actual AWS resource creation

## 🚀 Extension Points

### Adding New Tools

```python
# In CFNTemplateManagerTools.register()

@mcp.tool()
def your_new_tool(param: Type) -> Dict[str, Any]:
    """Tool description for AI agents."""
    return self.manager.your_new_method(param)

# In CloudFormationTemplateManager

def your_new_method(self, param: Type) -> Dict[str, Any]:
    try:
        # Implementation
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Adding New Template Sources

Extend `TemplateRepository` to support other sources:

```python
class TemplateRepository:
    def __init__(self, source_type: str, source_config: Dict):
        if source_type == "git":
            self._init_git(source_config)
        elif source_type == "s3":
            self._init_s3(source_config)
        elif source_type == "artifactory":
            self._init_artifactory(source_config)
```

### Adding Validation Rules

Extend `validate_parameters()`:

```python
def validate_parameters(self, resource_type, parameters):
    # ... existing validation
    
    # Add custom validation
    errors.extend(self._validate_naming_conventions(parameters))
    errors.extend(self._validate_cost_constraints(parameters))
    errors.extend(self._validate_security_rules(parameters))
```

## 📚 Dependencies

### Core Dependencies

```toml
boto3 >= 1.35.0           # AWS SDK
botocore >= 1.35.0        # AWS SDK core
fastmcp >= 0.2.3          # MCP server framework
loguru >= 0.7.2           # Logging
pydantic >= 2.0.0         # Data validation
gitpython >= 3.1.0        # Git operations
pyyaml >= 6.0.0           # YAML parsing
uvicorn >= 0.30.0         # ASGI server
```

### Why These Dependencies?

- **boto3/botocore**: AWS CloudFormation API
- **fastmcp**: MCP protocol server framework
- **loguru**: Better logging than stdlib
- **pydantic**: Type validation and serialization
- **gitpython**: Git repository cloning/pulling
- **pyyaml**: CloudFormation template parsing
- **uvicorn**: Production-ready ASGI server

## 🐛 Debugging

### Enable Debug Logging

```bash
export LOG_LEVEL=DEBUG
cfn-template-manager-mcp-server
```

### Common Issues

**Issue:** Templates not found
```python
# Check:
logger.debug(f"Looking in: {self.local_path}")
logger.debug(f"Found directories: {os.listdir(self.local_path)}")
```

**Issue:** Git clone fails
```python
# Check:
logger.debug(f"Cloning from: {self.repo_url}")
logger.debug(f"To: {self.local_path}")
# Verify: Git credentials, network access, repo URL
```

**Issue:** AWS permissions
```python
# Check:
logger.debug(f"AWS Region: {self.region_name}")
logger.debug(f"AWS Credentials: {boto3.client('sts').get_caller_identity()}")
```

## 🔒 Security Considerations

### Credentials
- Never log AWS credentials
- Use IAM roles in production (not access keys)
- NoEcho parameters should not be logged

### Template Validation
- Templates come from trusted source (your Git repo)
- Still validate parameter inputs
- Review change sets before execution

### Network
- MCP server should be in private network
- Use authentication for production
- Consider TLS/HTTPS

## 📈 Performance

### Caching Opportunities

```python
# Cache parsed templates (not implemented)
@lru_cache(maxsize=100)
def read_template(self, resource_type: str):
    # ...

# Cache template parameters (not implemented)
@lru_cache(maxsize=100)
def get_template_parameters(self, resource_type: str):
    # ...
```

### Optimization Ideas

1. **Cache Git repo** - Don't pull on every request
2. **Cache parsed templates** - Parse once, use many times
3. **Async operations** - Use async/await for boto3
4. **Connection pooling** - Reuse boto3 clients

## 📖 Further Reading

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCP Protocol Spec](https://modelcontextprotocol.io/)
- [AWS CloudFormation API](https://docs.aws.amazon.com/cloudformation/)
- [boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

---

**Last Updated:** October 2024
**Version:** 0.1.0

