# CloudFormation Template Manager - Visual Architecture

## 🏗️ System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER                                     │
│              "Create an S3 bucket"                               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AI AGENT                                      │
│          (cfn_infrastructure_agent.py)                           │
│  • Understands natural language                                  │
│  • Guides parameter collection                                   │
│  • Shows previews before execution                               │
└────────────────────────┬────────────────────────────────────────┘
                         │ MCP Protocol (HTTP/SSE)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│            MCP SERVER (This Component)                           │
│     CloudFormation Template Manager                              │
│                                                                  │
│  Port: 8080                                                      │
│  Protocol: HTTP/SSE                                              │
│  Tools: 9 CloudFormation operations                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
┌──────────────────────┐    ┌──────────────────────┐
│  Git Repository      │    │  AWS CloudFormation  │
│  (Your Templates)    │    │  (Resource Creation) │
└──────────────────────┘    └──────────────────────┘
```

## 📦 Internal Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      server.py (Entry Point)                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              FastMCP Server Instance                       │ │
│  │  • HTTP/SSE endpoints on port 8080                         │ │
│  │  • Tool registration & routing                             │ │
│  │  • Request/response serialization                          │ │
│  └───────────────────────┬────────────────────────────────────┘ │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                tools.py (Business Logic)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │        CFNTemplateManagerTools (Tool Wrapper)              │ │
│  │  • Registers 9 MCP tools                                   │ │
│  │  • Thin wrapper around manager methods                     │ │
│  │  • Adds @mcp.tool() decorators                             │ │
│  └───────────────────────┬────────────────────────────────────┘ │
│                          │                                       │
│                          ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │   CloudFormationTemplateManager (Core Logic)               │ │
│  │  • List/describe templates                                 │ │
│  │  • Validate parameters                                     │ │
│  │  • CloudFormation operations (create/execute/monitor)      │ │
│  │  • Uses boto3 for AWS API calls                            │ │
│  └───────────────────────┬────────────────────────────────────┘ │
│                          │                                       │
│                          ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │       TemplateRepository (Template Management)             │ │
│  │  • Git clone/pull operations                               │ │
│  │  • Directory scanning & discovery                          │ │
│  │  • YAML/JSON template parsing                              │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 🔄 Request Flow (Step by Step)

```
1. HTTP Request Arrives
   ↓
   [server.py: FastMCP receives request]
   ↓
2. Route to Tool
   ↓
   [server.py: Identifies tool (e.g., create_change_set)]
   ↓
3. Tool Wrapper
   ↓
   [tools.py: CFNTemplateManagerTools.create_change_set()]
   ↓
4. Manager Method
   ↓
   [tools.py: CloudFormationTemplateManager.create_change_set()]
   ├─→ [Validate parameters]
   ├─→ [Get template from repository]
   └─→ [Call AWS CloudFormation API]
   ↓
5. Template Repository
   ↓
   [tools.py: TemplateRepository.get_template_body()]
   ├─→ [Read file from disk/git]
   └─→ [Return raw template content]
   ↓
6. AWS API Call
   ↓
   [boto3: cfn_client.create_change_set()]
   ↓
7. Format Response
   ↓
   [tools.py: Return {"success": true, "change_set_id": "..."}]
   ↓
8. Send Response
   ↓
   [server.py: FastMCP sends HTTP response]
   ↓
9. AI Agent Receives
```

## 🎯 The 9 Tools (Visual Map)

```
┌─────────────────────────────────────────────────────────┐
│                  MCP TOOLS (9 Total)                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📋 DISCOVERY TOOLS                                     │
│  ├─ list_available_resources()                         │
│  │  └─> Lists: ["s3", "ec2", "lambda", ...]           │
│  │                                                      │
│  ├─ get_template_info(resource_type)                   │
│  │  └─> Returns: description, params, resources        │
│  │                                                      │
│  └─ get_template_parameters(resource_type)             │
│     └─> Returns: detailed parameter info               │
│                                                         │
│  ✅ VALIDATION TOOLS                                    │
│  └─ validate_parameters(resource_type, params)         │
│     └─> Returns: valid/invalid, errors, warnings       │
│                                                         │
│  🚀 DEPLOYMENT TOOLS                                    │
│  ├─ create_change_set(...)                             │
│  │  └─> Returns: change_set_id                         │
│  │                                                      │
│  ├─ describe_change_set(change_set_name, stack_name)   │
│  │  └─> Returns: list of changes (Add/Modify/Remove)   │
│  │                                                      │
│  └─ execute_change_set(change_set_name, stack_name)    │
│     └─> Returns: execution status                      │
│                                                         │
│  📊 MONITORING TOOLS                                    │
│  ├─ get_stack_status(stack_name)                       │
│  │  └─> Returns: status, outputs, parameters           │
│  │                                                      │
│  └─ delete_stack(stack_name)                           │
│     └─> Returns: deletion status                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 🗂️ Template Repository Structure

```
Git Repository or Local Directory
│
├── s3/                          ← Resource Type
│   └── template.yaml            ← CloudFormation Template
│       ├─ Parameters            ← What user needs to provide
│       ├─ Resources             ← AWS resources to create
│       └─ Outputs               ← Values returned after creation
│
├── ec2/                         ← Another resource type
│   └── template.yaml
│
├── lambda/                      ← Another resource type
│   └── template.yaml
│
└── rds/                         ← Another resource type
    └── template.yaml

Template Discovery:
1. Scan directories → ["s3", "ec2", "lambda", "rds"]
2. Each directory = one resource type
3. Each template.yaml = how to create that resource
```

## 📊 Data Flow Example: Creating an S3 Bucket

```
User: "Create an S3 bucket for logs"
   ↓
┌──────────────────────────────────────────┐
│ Step 1: List Available Resources         │
│ Tool: list_available_resources()         │
│ Response: ["s3", "ec2", "lambda"]        │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 2: Get S3 Template Parameters       │
│ Tool: get_template_parameters("s3")      │
│ Response: {                               │
│   "BucketName": {                        │
│     "type": "String",                    │
│     "description": "Bucket name",        │
│     "required": true                     │
│   }                                      │
│ }                                        │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 3: User Provides Parameters         │
│ Agent asks: "What bucket name?"          │
│ User replies: "my-logs-bucket"           │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 4: Validate Parameters              │
│ Tool: validate_parameters("s3", {...})   │
│ Response: {"valid": true}                │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 5: Create Change Set                │
│ Tool: create_change_set(...)             │
│ Response: {"change_set_id": "arn:..."}   │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 6: Describe Change Set              │
│ Tool: describe_change_set(...)           │
│ Response: {                               │
│   "changes": [                           │
│     {"action": "Add",                    │
│      "resource": "S3::Bucket"},          │
│     {"action": "Add",                    │
│      "resource": "S3::BucketPolicy"}     │
│   ]                                      │
│ }                                        │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 7: User Confirmation                │
│ Agent: "Create these resources? (yes/no)"│
│ User: "yes"                              │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 8: Execute Change Set               │
│ Tool: execute_change_set(...)            │
│ Response: {"success": true}              │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 9: Monitor Status                   │
│ Tool: get_stack_status(...)              │
│ Response: {                               │
│   "status": "CREATE_COMPLETE",           │
│   "outputs": {                           │
│     "BucketName": "my-logs-bucket",      │
│     "BucketArn": "arn:aws:s3:::..."      │
│   }                                      │
│ }                                        │
└──────────────────────────────────────────┘
```

## 🔧 Component Responsibilities

```
┌────────────────────────────────────────────────────────┐
│                    server.py                           │
├────────────────────────────────────────────────────────┤
│ • Initialize FastMCP server                            │
│ • Register tools                                       │
│ • Start HTTP server                                    │
│ • Handle incoming requests                             │
│ • Serialize responses                                  │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│          CFNTemplateManagerTools (tools.py)            │
├────────────────────────────────────────────────────────┤
│ • Wrap manager methods as MCP tools                    │
│ • Add @mcp.tool() decorators                           │
│ • Provide tool descriptions for AI                     │
│ • No business logic (just wrappers)                    │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│      CloudFormationTemplateManager (tools.py)          │
├────────────────────────────────────────────────────────┤
│ • Core business logic                                  │
│ • Template discovery & parsing                         │
│ • Parameter validation                                 │
│ • AWS CloudFormation API calls                         │
│ • Error handling                                       │
│ • Response formatting                                  │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│           TemplateRepository (tools.py)                │
├────────────────────────────────────────────────────────┤
│ • Git repository operations                            │
│ • Directory scanning                                   │
│ • File discovery (template.yaml)                       │
│ • YAML/JSON parsing                                    │
│ • Template content retrieval                           │
└────────────────────────────────────────────────────────┘
```

## 🌐 Network Flow

```
External                MCP Server              AWS
   │                        │                    │
   │  HTTP POST             │                    │
   ├───────────────────────>│                    │
   │  /tools/create_change_set                   │
   │                        │                    │
   │                        │  create_change_set │
   │                        ├───────────────────>│
   │                        │                    │
   │                        │  change_set_id     │
   │                        │<───────────────────┤
   │                        │                    │
   │  JSON Response         │                    │
   │<───────────────────────┤                    │
   │  {"change_set_id": "..."}                   │
   │                        │                    │
```

## 📚 File Dependencies

```
server.py
   ↓ imports
tools.py
   ├─ imports boto3 (AWS SDK)
   ├─ imports yaml (template parsing)
   ├─ imports git (GitPython)
   ├─ imports loguru (logging)
   └─ imports FastMCP decorators

pyproject.toml
   └─ defines all dependencies
```

## 🎓 Learning Path

**If you want to understand the code:**

1. Start with `QUICK_REFERENCE.md` (this repo)
   - Get overview of structure
   - Understand the 9 tools

2. Read `server.py` (55 lines)
   - See how FastMCP is initialized
   - See how tools are registered

3. Read `tools.py` in order:
   - TemplateRepository class (lines 20-130)
   - CloudFormationTemplateManager class (lines 133-600)
   - CFNTemplateManagerTools class (lines 603-800)

4. Read `CODE_ARCHITECTURE.md` (this repo)
   - Deep dive into each method
   - Understand data structures
   - Learn extension points

**If you want to use it:**

1. Read `README.md` (setup instructions)
2. Run `test_cfn_mcp_server.py` (test it works)
3. Start the server
4. Connect your AI agent

---

**Visual learner?** This file is for you! 📊
**Code reader?** See `CODE_ARCHITECTURE.md` 📝
**Quick lookup?** See `QUICK_REFERENCE.md` ⚡

