# CloudFormation Template Manager MCP Server - Quick Reference

## 📂 File Structure (What's Where)

```
mcp/src/cfn-template-manager-mcp-server/
│
├── 📄 server.py                    (55 lines)
│   └─ FastMCP server entry point
│      • Creates MCP server instance
│      • Registers tools
│      • Starts uvicorn on port 8080
│
├── 📄 tools.py                     (800+ lines)
│   ├─ Class: TemplateRepository
│   │  └─ Git/local template management
│   │     • Clone/pull Git repos
│   │     • Discover resource types
│   │     • Parse YAML/JSON templates
│   │
│   ├─ Class: CloudFormationTemplateManager
│   │  └─ Core CloudFormation logic
│   │     • List/describe templates
│   │     • Validate parameters
│   │     • Create/execute change sets
│   │     • Monitor stacks
│   │
│   └─ Class: CFNTemplateManagerTools
│      └─ MCP tool registration
│         • Wraps manager methods
│         • Adds @mcp.tool() decorators
│         • 9 tools total
│
├── 📄 pyproject.toml
│   └─ Package metadata & dependencies
│
├── 📄 Dockerfile
│   └─ Container image definition
│
├── 📄 README.md
│   └─ User documentation
│
├── 📄 CODE_ARCHITECTURE.md
│   └─ Detailed code documentation
│
└── 📄 QUICK_REFERENCE.md
    └─ This file
```

## 🔧 Three Main Classes

### 1️⃣ TemplateRepository
**File:** `tools.py` (lines ~20-130)
**Purpose:** Template file management

```python
repository = TemplateRepository(
    repo_url="https://github.com/org/templates.git",  # OR
    local_path="/path/to/templates"
)

# What it does:
resources = repository.list_resources()         # ["s3", "ec2", "lambda"]
template = repository.read_template("s3")       # {Parameters: {...}, Resources: {...}}
body = repository.get_template_body("s3")       # "AWSTemplateFormatVersion: ..."
```

### 2️⃣ CloudFormationTemplateManager
**File:** `tools.py` (lines ~133-600)
**Purpose:** CloudFormation operations

```python
manager = CloudFormationTemplateManager(
    repo_url="...",
    local_path="...",
    region_name="us-east-1"
)

# Discovery
manager.list_available_resources()
manager.get_template_info("s3")
manager.get_template_parameters("s3")

# Validation
manager.validate_parameters("s3", {"BucketName": "my-bucket"})

# Deployment
manager.create_change_set("s3", {...}, "my-stack")
manager.describe_change_set("my-changeset", "my-stack")
manager.execute_change_set("my-changeset", "my-stack")

# Monitoring
manager.get_stack_status("my-stack")
manager.delete_stack("my-stack")
```

### 3️⃣ CFNTemplateManagerTools
**File:** `tools.py` (lines ~603-800)
**Purpose:** MCP tool registration

```python
tools = CFNTemplateManagerTools()
tools.register(mcp)  # Registers 9 tools

# Each tool is a thin wrapper:
@mcp.tool()
def list_available_resources():
    return self.manager.list_available_resources()
```

## 🎯 The 9 MCP Tools

| # | Tool Name | What It Does | Returns |
|---|-----------|--------------|---------|
| 1 | `list_available_resources()` | Lists resource types | `["s3", "ec2", ...]` |
| 2 | `get_template_info(resource_type)` | Template overview | Description, params, resources |
| 3 | `get_template_parameters(resource_type)` | Parameter details | Type, description, constraints |
| 4 | `validate_parameters(resource_type, params)` | Validates params | Valid/invalid, errors |
| 5 | `create_change_set(...)` | Creates CFN change set | Change set ID |
| 6 | `describe_change_set(...)` | Shows what will change | List of changes |
| 7 | `execute_change_set(...)` | Deploys resources | Success/failure |
| 8 | `get_stack_status(stack_name)` | Stack status | Status, outputs |
| 9 | `delete_stack(stack_name)` | Deletes stack | Success/failure |

## 🔄 How A Request Flows

```
AI Agent sends: create_change_set("s3", {"BucketName": "test"}, "my-stack")
    ↓
FastMCP Server (server.py)
    ↓
CFNTemplateManagerTools.create_change_set() [tool wrapper]
    ↓
CloudFormationTemplateManager.create_change_set() [business logic]
    ├─→ validate_parameters()
    ├─→ TemplateRepository.get_template_body()
    └─→ boto3.client('cloudformation').create_change_set()
    ↓
Returns: {"success": true, "change_set_id": "arn:..."}
    ↓
FastMCP sends response back to AI Agent
```

## 📦 Key Dependencies

```python
import boto3                  # AWS SDK
from mcp.server.fastmcp import FastMCP  # MCP framework
import yaml                   # Parse CloudFormation templates
import git                    # Git operations
from loguru import logger     # Logging
```

## 🌍 Environment Variables

```bash
# Template source (pick one)
export CFN_TEMPLATE_REPO_URL="https://github.com/org/templates.git"
export CFN_TEMPLATE_LOCAL_PATH="/path/to/templates"

# AWS
export AWS_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

## 🚀 Running the Server

### Method 1: CLI
```bash
cfn-template-manager-mcp-server
# Runs on http://localhost:8080
```

### Method 2: Python
```bash
python -m awslabs.cfn_template_manager.server
```

### Method 3: Docker
```bash
docker run -p 8080:8080 \
  -e CFN_TEMPLATE_LOCAL_PATH=/templates \
  -e AWS_REGION=us-east-1 \
  cfn-template-manager-mcp-server
```

## 🧪 Testing

```bash
# Run test suite
python test_cfn_mcp_server.py

# What it tests:
# ✓ List resources
# ✓ Get template info
# ✓ Get parameters
# ✓ Validate parameters
# ✓ Full workflow (dry run)
```

## 🔍 Code Locations (Line Numbers)

| What | File | Approx Lines |
|------|------|--------------|
| Server initialization | `server.py` | 23-32 |
| Main entry point | `server.py` | 45-50 |
| TemplateRepository class | `tools.py` | 20-130 |
| Git operations | `tools.py` | 40-65 |
| Template discovery | `tools.py` | 67-95 |
| CloudFormationTemplateManager | `tools.py` | 133-600 |
| List resources | `tools.py` | 155-170 |
| Get parameters | `tools.py` | 195-240 |
| Validate parameters | `tools.py` | 242-310 |
| Create change set | `tools.py` | 312-380 |
| Execute change set | `tools.py` | 430-480 |
| CFNTemplateManagerTools | `tools.py` | 603-800 |
| Tool registration | `tools.py` | 615-780 |

## 🎨 Response Format (All Tools)

```python
# Success response
{
    "success": true,
    "data": {...},              # Tool-specific data
    "message": "Operation succeeded"
}

# Error response
{
    "success": false,
    "error": "Error message describing what went wrong"
}
```

## 🔧 Common Modifications

### Add a new tool
**Edit:** `tools.py` → `CFNTemplateManagerTools.register()`
```python
@mcp.tool()
def your_new_tool(param: str) -> Dict[str, Any]:
    """Tool description."""
    return self.manager.your_new_method(param)
```

### Change template search pattern
**Edit:** `tools.py` → `TemplateRepository.get_template_path()`
```python
# Add new template file names
for filename in ['template.yaml', 'your-custom-name.yaml']:
    # ...
```

### Add validation rules
**Edit:** `tools.py` → `CloudFormationTemplateManager.validate_parameters()`
```python
# Add custom validation
if 'BucketName' in parameters:
    if not parameters['BucketName'].startswith('mycompany-'):
        errors.append("BucketName must start with 'mycompany-'")
```

## 📊 Data Flow Example

**User:** "Create an S3 bucket named 'my-logs'"

```
1. Agent → list_available_resources()
   Response: ["s3", "ec2", "lambda"]

2. Agent → get_template_parameters("s3")
   Response: {
     "parameters": {
       "BucketName": {
         "type": "String",
         "description": "Name for bucket"
       }
     },
     "required_parameters": ["BucketName"]
   }

3. Agent → validate_parameters("s3", {"BucketName": "my-logs"})
   Response: {"valid": true, "errors": []}

4. Agent → create_change_set("s3", {"BucketName": "my-logs"}, "my-logs-stack")
   Response: {"success": true, "change_set_id": "arn:..."}

5. Agent → describe_change_set("my-logs-stack-changeset-create", "my-logs-stack")
   Response: {
     "changes": [
       {"action": "Add", "resource_type": "AWS::S3::Bucket"},
       {"action": "Add", "resource_type": "AWS::S3::BucketPolicy"}
     ]
   }

6. [User confirms]

7. Agent → execute_change_set("my-logs-stack-changeset-create", "my-logs-stack")
   Response: {"success": true, "message": "Execution started"}

8. Agent → get_stack_status("my-logs-stack")
   Response: {
     "status": "CREATE_COMPLETE",
     "outputs": [
       {"key": "BucketName", "value": "my-logs"},
       {"key": "BucketArn", "value": "arn:aws:s3:::my-logs"}
     ]
   }
```

## 🐛 Debug Checklist

Problem getting started? Check:
- ✓ Python 3.10+ installed
- ✓ Dependencies installed (`pip install -e .`)
- ✓ Environment variables set
- ✓ Template directory exists and has templates
- ✓ AWS credentials configured
- ✓ Port 8080 not in use

Problem with templates? Check:
- ✓ Directory structure (one dir per resource type)
- ✓ Template file named correctly (template.yaml)
- ✓ Valid CloudFormation YAML/JSON
- ✓ Parameters section properly formatted

Problem with AWS? Check:
- ✓ AWS credentials valid (`aws sts get-caller-identity`)
- ✓ Region set correctly
- ✓ CloudFormation permissions granted
- ✓ Resource limits not exceeded

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | User guide, setup instructions |
| `CODE_ARCHITECTURE.md` | Detailed code documentation |
| `QUICK_REFERENCE.md` | This file - quick lookup |
| `../../../CFN_INFRASTRUCTURE_SETUP.md` | Full setup guide |
| `../../../CFN_INFRASTRUCTURE_SUMMARY.md` | Project summary |

---

**Need more details?** See `CODE_ARCHITECTURE.md`
**Need setup help?** See `README.md`
**Need full picture?** See `CFN_INFRASTRUCTURE_SUMMARY.md`

