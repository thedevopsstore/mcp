"""
CloudFormation GitOps Agent

This agent creates AWS infrastructure using a GitOps workflow:
1. Reads CloudFormation templates from GitHub repository
2. Parses templates and understands parameter requirements
3. Collects parameters from users with validation
4. Creates parameter files in GitHub
5. Raises pull requests for admin approval
6. GitHub Actions deploys after PR merge

Uses:
- GitHub's hosted MCP server (https://api.githubcopilot.com/mcp/)
- Python tools for template parsing (no separate MCP needed)
"""

import os
import yaml
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel
from strands.mcp import MCPSession
from loguru import logger

# Load environment variables
load_dotenv()


# ============================================================================
# CloudFormation Template Tools (using @tool decorator)
# ============================================================================

# CloudFormation YAML Constructor Setup
def _cfn_constructor(loader, tag_suffix, node):
    """Handle CloudFormation intrinsic functions (!Ref, !GetAtt, etc.)."""
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node)
    else:
        value = None
    return {tag_suffix: value}


def _setup_cfn_yaml_constructors():
    """Register CloudFormation intrinsic function constructors."""
    cfn_functions = [
        'Ref', 'Condition', 'Equals', 'Not', 'And', 'Or', 'If',
        'FindInMap', 'Base64', 'GetAtt', 'GetAZs', 'ImportValue',
        'Join', 'Select', 'Split', 'Sub', 'Transform', 'Cidr',
    ]
    
    for func in cfn_functions:
        yaml.SafeLoader.add_constructor(
            f'!{func}',
            lambda loader, node, tag=func: _cfn_constructor(loader, tag, node)
        )


# Initialize CloudFormation YAML constructors at module load
_setup_cfn_yaml_constructors()


@tool
def parse_cloudformation_template(template_content: str) -> Dict[str, Any]:
    """
    Parse CloudFormation template from YAML or JSON content.
    
    Handles CloudFormation intrinsic functions like !Ref, !GetAtt, !Sub, !Equals, etc.
    
    Args:
        template_content: CloudFormation template as string (YAML or JSON)
        
    Returns:
        Parsed template as dictionary with success status
    """
    try:
        # Try YAML first
        template = yaml.safe_load(template_content)
        return {
            "success": True,
            "template": template,
            "format": "yaml"
        }
    except yaml.YAMLError:
        # Try JSON
        try:
            template = json.loads(template_content)
            return {
                "success": True,
                "template": template,
                "format": "json"
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid template format: {str(e)}"
            }


@tool
def extract_template_parameters(template: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract parameter information from parsed CloudFormation template.
    
    Gets parameter types, constraints, defaults, and descriptions.
    
    Args:
        template: Parsed CloudFormation template dictionary
        
    Returns:
        Parameter details with types, constraints, defaults, required/optional flags
    """
    try:
        parameters = template.get('Parameters', {})
        
        param_details = {}
        for param_name, param_config in parameters.items():
            # Convert boolean/numeric values to strings for String type
            allowed_values = param_config.get('AllowedValues', [])
            default_value = param_config.get('Default')
            
            if param_config.get('Type') == 'String':
                if allowed_values:
                    allowed_values = [str(v).lower() if isinstance(v, bool) else str(v) for v in allowed_values]
                if default_value is not None and not isinstance(default_value, str):
                    default_value = str(default_value).lower() if isinstance(default_value, bool) else str(default_value)
            
            param_details[param_name] = {
                "type": param_config.get('Type', 'String'),
                "description": param_config.get('Description', ''),
                "default": default_value,
                "allowed_values": allowed_values,
                "allowed_pattern": param_config.get('AllowedPattern'),
                "constraint_description": param_config.get('ConstraintDescription'),
                "min_length": param_config.get('MinLength'),
                "max_length": param_config.get('MaxLength'),
                "no_echo": param_config.get('NoEcho', False),
                "required": 'Default' not in param_config
            }
        
        return {
            "success": True,
            "parameters": param_details,
            "required_parameters": [name for name, info in param_details.items() if info['required']],
            "optional_parameters": [name for name, info in param_details.items() if not info['required']]
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error extracting parameters: {str(e)}"
        }


@tool
def validate_template_parameters(template: Dict[str, Any], parameters: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate parameter values against CloudFormation template constraints.
    
    Checks required parameters, allowed values, patterns, length constraints, etc.
    
    Args:
        template: Parsed CloudFormation template dictionary
        parameters: Parameter key-value pairs to validate
        
    Returns:
        Validation result with valid/invalid status and error/warning messages
    """
    try:
        # Extract template parameters
        param_info = extract_template_parameters(template)
        if not param_info.get('success'):
            return param_info
        
        template_params = param_info['parameters']
        required_params = param_info['required_parameters']
        
        errors = []
        warnings = []
        
        # Check required parameters
        for req_param in required_params:
            if req_param not in parameters:
                errors.append(f"Missing required parameter: {req_param}")
        
        # Validate parameter values
        for param_name, param_value in parameters.items():
            if param_name not in template_params:
                warnings.append(f"Unknown parameter: {param_name}")
                continue
            
            param_def = template_params[param_name]
            
            # Validate allowed values
            if param_def.get('allowed_values') and param_value not in param_def['allowed_values']:
                errors.append(f"Invalid value for {param_name}. Allowed: {param_def['allowed_values']}")
            
            # Validate string length
            if param_def.get('min_length') and len(param_value) < param_def['min_length']:
                errors.append(f"{param_name} must be at least {param_def['min_length']} characters")
            
            if param_def.get('max_length') and len(param_value) > param_def['max_length']:
                errors.append(f"{param_name} must be at most {param_def['max_length']} characters")
        
        return {
            "success": True,
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Validation error: {str(e)}"
        }


@tool
def generate_stack_configuration(template_type: str, stack_name: str, 
                                 parameters: Dict[str, str], region: str = "us-east-1",
                                 requester: str = "agent") -> str:
    """Parse and validate CloudFormation templates."""
    
    def __init__(self):
        """Initialize CloudFormation parser with intrinsic function support."""
        self._setup_cfn_yaml_constructors()
    
    def _cfn_constructor(self, loader, tag_suffix, node):
        """Handle CloudFormation intrinsic functions (!Ref, !GetAtt, etc.)."""
        if isinstance(node, yaml.ScalarNode):
            value = loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            value = loader.construct_sequence(node)
        elif isinstance(node, yaml.MappingNode):
            value = loader.construct_mapping(node)
        else:
            value = None
        return {tag_suffix: value}
    
    def _setup_cfn_yaml_constructors(self):
        """Register CloudFormation intrinsic function constructors."""
        cfn_functions = [
            'Ref', 'Condition', 'Equals', 'Not', 'And', 'Or', 'If',
            'FindInMap', 'Base64', 'GetAtt', 'GetAZs', 'ImportValue',
            'Join', 'Select', 'Split', 'Sub', 'Transform', 'Cidr',
        ]
        
        for func in cfn_functions:
            yaml.SafeLoader.add_constructor(
                f'!{func}',
                lambda loader, node, tag=func: self._cfn_constructor(loader, tag, node)
            )
    
    def parse_template(self, template_content: str) -> Dict[str, Any]:
        """
        Parse CloudFormation template from YAML or JSON.
        
        Args:
            template_content: Template content as string
            
        Returns:
            Parsed template as dictionary
        """
        try:
            # Try YAML first
            template = yaml.safe_load(template_content)
            return {
                "success": True,
                "template": template,
                "format": "yaml"
            }
        except yaml.YAMLError:
            # Try JSON
            try:
                template = json.loads(template_content)
                return {
                    "success": True,
                    "template": template,
                    "format": "json"
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Invalid template format: {str(e)}"
                }
    
    def get_template_parameters(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract parameter information from CloudFormation template.
        
        Args:
            template: Parsed CloudFormation template
            
        Returns:
            Parameter details with types, constraints, defaults
        """
        try:
            parameters = template.get('Parameters', {})
            
            param_details = {}
            for param_name, param_config in parameters.items():
                # Convert boolean/numeric values to strings for String type
                allowed_values = param_config.get('AllowedValues', [])
                default_value = param_config.get('Default')
                
                if param_config.get('Type') == 'String':
                    if allowed_values:
                        allowed_values = [str(v).lower() if isinstance(v, bool) else str(v) for v in allowed_values]
                    if default_value is not None and not isinstance(default_value, str):
                        default_value = str(default_value).lower() if isinstance(default_value, bool) else str(default_value)
                
                param_details[param_name] = {
                    "type": param_config.get('Type', 'String'),
                    "description": param_config.get('Description', ''),
                    "default": default_value,
                    "allowed_values": allowed_values,
                    "allowed_pattern": param_config.get('AllowedPattern'),
                    "constraint_description": param_config.get('ConstraintDescription'),
                    "min_length": param_config.get('MinLength'),
                    "max_length": param_config.get('MaxLength'),
                    "no_echo": param_config.get('NoEcho', False),
                    "required": 'Default' not in param_config
                }
            
            return {
                "success": True,
                "parameters": param_details,
                "required_parameters": [name for name, info in param_details.items() if info['required']],
                "optional_parameters": [name for name, info in param_details.items() if not info['required']]
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error extracting parameters: {str(e)}"
            }
    
    def validate_parameters(self, template: Dict[str, Any], parameters: Dict[str, str]) -> Dict[str, Any]:
        """
        Validate parameter values against template constraints.
        
        Args:
            template: Parsed CloudFormation template
            parameters: Parameter key-value pairs
            
        Returns:
            Validation result with errors/warnings
        """
        try:
            param_info = self.get_template_parameters(template)
            if not param_info.get('success'):
                return param_info
            
            template_params = param_info['parameters']
            required_params = param_info['required_parameters']
            
            errors = []
            warnings = []
            
            # Check required parameters
            for req_param in required_params:
                if req_param not in parameters:
                    errors.append(f"Missing required parameter: {req_param}")
            
            # Validate parameter values
            for param_name, param_value in parameters.items():
                if param_name not in template_params:
                    warnings.append(f"Unknown parameter: {param_name}")
                    continue
                
                param_def = template_params[param_name]
                
                # Validate allowed values
                if param_def.get('allowed_values') and param_value not in param_def['allowed_values']:
                    errors.append(f"Invalid value for {param_name}. Allowed: {param_def['allowed_values']}")
                
                # Validate string length
                if param_def.get('min_length') and len(param_value) < param_def['min_length']:
                    errors.append(f"{param_name} must be at least {param_def['min_length']} characters")
                
                if param_def.get('max_length') and len(param_value) > param_def['max_length']:
                    errors.append(f"{param_name} must be at most {param_def['max_length']} characters")
            
            return {
                "success": True,
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Validation error: {str(e)}"
            }
    
    def generate_stack_config(self, template_type: str, stack_name: str, 
                             parameters: Dict[str, str], region: str = "us-east-1",
                             requester: str = None) -> str:
        """
        Generate stack configuration file for GitOps deployment.
        
        Args:
            template_type: Resource type (e.g., 's3', 'ec2')
            stack_name: CloudFormation stack name
            parameters: Parameter key-value pairs
            region: AWS region
            requester: User who requested (email or username)
            
        Returns:
            JSON string of stack configuration
        """
        config = {
            "request": {
                "resource_type": template_type,
                "stack_name": stack_name,
                "region": region,
                "requested_by": requester or "agent",
                "requested_at": datetime.utcnow().isoformat() + "Z"
            },
            "template": {
                "type": template_type,
                "source": f"templates/{template_type}/template.yaml"
            },
            "parameters": parameters,
            "tags": {
                "Environment": parameters.get('Environment', 'dev'),
                "ManagedBy": "GitOps",
                "RequestedBy": requester or "agent"
            }
        }
        
        return json.dumps(config, indent=2)


# ============================================================================
# Agent System Prompt
# ============================================================================

GITOPS_AGENT_PROMPT = """
You are a CloudFormation GitOps Agent that creates AWS infrastructure using a pull request workflow.

## Your Role

Help users create AWS resources by:
1. Reading CloudFormation templates from GitHub repository
2. Understanding parameter requirements
3. Collecting parameter values from users
4. Creating stack configuration files
5. Raising pull requests for admin approval
6. Tracking PR status

## Architecture

**GitHub Repository:** {github_org}/{github_infra_repo}
**Templates Location:** templates/{resource-type}/template.yaml
**Stack Configs Location:** stacks/{resource-type}/{stack-name}.json

## Available Tools

**GitHub MCP Tools:**
- `get_file_contents(owner, repo, path, ref)` - Read template files
- `list_directory_contents(owner, repo, path, ref)` - List available templates
- `create_branch(owner, repo, branch, from_branch)` - Create feature branch
- `create_or_update_file(owner, repo, path, content, message, branch)` - Commit config file
- `create_pull_request(owner, repo, title, body, head, base)` - Create PR
- `request_reviewers(owner, repo, pull_number, reviewers)` - Tag reviewers
- `get_pull_request(owner, repo, pull_number)` - Check PR status
- `list_pull_request_comments(owner, repo, pull_number)` - Get comments

**Python Tools (CloudFormation):**
- `parse_template(template_content)` - Parse YAML/JSON template
- `get_template_parameters(template)` - Extract parameter requirements
- `validate_parameters(template, params)` - Validate parameter values
- `generate_stack_config(type, stack_name, params, region, requester)` - Generate config file

## Workflow (8 Steps)

**Step 1: List Available Resources**
- Call: `list_directory_contents(owner, repo, "templates", "main")`
- Parse: Directory names = resource types
- Match: User intent to resource type

**Step 2: Read Template**
- Call: `get_file_contents(owner, repo, "templates/{type}/template.yaml", "main")`
- Call: `parse_template(content)` to parse YAML

**Step 3: Understand Parameters**
- Call: `get_template_parameters(template)`
- Analyze: Required vs optional, constraints, defaults
- Prepare: Questions for user

**Step 4: Collect Parameters**
- For each required parameter:
  - Explain what it controls
  - Show constraints (allowed values, patterns)
  - Ask user for value
- For optional parameters:
  - Show default, ask if want to override

**Step 5: Validate**
- Call: `validate_parameters(template, params)`
- If errors: Show fixes, re-collect
- If valid: Proceed

**Step 6: Generate Configuration**
- Call: `generate_stack_config(type, stack_name, params, region, user)`
- Create: JSON file with all details

**Step 7: Create Branch and Commit**
- Call: `create_branch(owner, repo, "create-{resource}-{name}", "main")`
- Call: `create_or_update_file(owner, repo, path, json_content, message, branch)`

**Step 8: Create Pull Request**
- Generate PR description (resource summary, parameters, validation)
- Call: `create_pull_request(...)`
- Call: `request_reviewers(..., ["infra-team"])`
- Show: PR URL to user

## PR Description Template

Generate descriptive PRs:

```
## Resource Request: {Resource Type}

**Stack:** {stack-name}
**Template:** {template-type}
**Region:** {region}
**Requested By:** {user}

### Parameters
{list all parameters with values}

### Resources to be Created
{parse template Resources section, list what will be created}

### Tags
{list tags}

### Validation
✅ All required parameters provided
✅ Parameters validated against constraints
✅ Stack name follows naming convention

### Deployment
Upon merge, GitHub Actions will:
1. Deploy CloudFormation stack
2. Comment on PR with stack outputs
3. Send notification

**Approval required from:** @infra-team
```

## Safety Rules

⚠️ **NEVER directly deploy** - Always create PR
⚠️ **ALWAYS validate** - Before creating PR
⚠️ **ALWAYS explain** - What each parameter controls
⚠️ **Clear stack names** - Follow {app}-{resource}-{env}-stack pattern

## Parameter Collection

For each parameter:
- Show type and description
- Explain constraints in plain English
- Provide examples
- For AllowedValues: Show as options
- For NoEcho: Warn it's sensitive

## Stack Naming

Generate meaningful names: `{app}-{resource}-{env}-stack`
Example: `myapp-s3-prod-stack`

## Error Handling

**Template not found:** List available types in templates/
**Validation fails:** Show specific errors with fixes
**Branch exists:** Suggest new name or use existing
**PR creation fails:** Explain error, offer solutions

## User Communication

**Starting:** "I'll help you create {resource}. Let me read the template from GitHub..."

**Collecting:** "Parameter: BucketName (required)
- Must be unique, lowercase, 3-63 chars
- Example: mycompany-app-logs-2024
What would you like to name it?"

**Validating:** "✓ Parameters validated successfully"

**Creating PR:** "✅ Pull request created!
📋 PR: {url}
📦 Stack: {name}
👥 Reviewers: @infra-team

Next: Approval (usually <30 min) → Auto-deploy (5-10 min)"

## Example Interaction

```
User: "Create S3 bucket for logs"

1. List templates from GitHub
2. Read templates/s3/template.yaml
3. Parse and extract parameters
4. Ask: "BucketName (unique, lowercase)? Example: myapp-logs-2024"
5. User: "acme-logs-2024"
6. Validate → Generate config
7. Create branch → Commit file → Create PR
8. "✅ PR created: github.com/org/repo/pull/123"
```

Be helpful, clear, and always explain what will happen after approval.
"""


# ============================================================================
# Agent Creation
# ============================================================================

async def create_gitops_agent(
    github_org: str,
    github_infra_repo: str,
    github_templates_repo: str,
    github_pat: str,
    default_reviewers: List[str] = None,
    region: str = "us-east-1",
    bedrock_region: str = "us-east-1"
) -> Agent:
    """
    Create CloudFormation GitOps Agent.
    
    Args:
        github_org: GitHub organization name
        github_infra_repo: Repository for stack configs (infrastructure-configs)
        github_templates_repo: Repository with CF templates (cfn-templates)
        github_pat: GitHub Personal Access Token
        default_reviewers: List of default PR reviewers
        region: Default AWS region for stacks
        bedrock_region: AWS region for Bedrock
        
    Returns:
        Configured GitOps Agent
    """
    default_reviewers = default_reviewers or ["infra-team"]
    
    # Create GitHub MCP session (GitHub's hosted service)
    github_mcp = MCPSession(
        server_url="https://api.githubcopilot.com/mcp/",
        transport="sse",
        headers={
            "Authorization": f"Bearer {github_pat}"
        }
    )
    
    # Initialize MCP session
    await github_mcp.initialize()
    logger.info("Connected to GitHub MCP at https://api.githubcopilot.com/mcp/")
    
    # Format system prompt with configuration
    formatted_prompt = GITOPS_AGENT_PROMPT.format(
        github_org=github_org,
        github_infra_repo=github_infra_repo
    )
    
    # Create agent with GitHub MCP and CloudFormation tools
    agent = Agent(
        name="cfn_gitops_agent",
        instructions=formatted_prompt,
        model=BedrockModel(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            region=bedrock_region
        ),
        mcp_sessions=[github_mcp],
        tools=[
            # CloudFormation tools (using @tool decorator)
            parse_cloudformation_template,
            extract_template_parameters,
            validate_template_parameters,
            generate_stack_configuration,
        ],
        context={
            "github_org": github_org,
            "github_infra_repo": github_infra_repo,
            "github_templates_repo": github_templates_repo,
            "default_reviewers": default_reviewers,
            "default_region": region
        }
    )
    
    logger.info("CloudFormation GitOps Agent created successfully")
    return agent


# ============================================================================
# Main Interactive Loop
# ============================================================================

async def main():
    """Run the CloudFormation GitOps Agent."""
    
    # Configuration from environment
    GITHUB_ORG = os.getenv("GITHUB_ORG", "myorg")
    GITHUB_INFRA_REPO = os.getenv("GITHUB_INFRA_REPO", "infrastructure-configs")
    GITHUB_TEMPLATES_REPO = os.getenv("GITHUB_TEMPLATES_REPO", "cfn-templates")
    GITHUB_PAT = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    DEFAULT_REVIEWERS = os.getenv("DEFAULT_PR_REVIEWERS", "infra-team").split(",")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
    
    if not GITHUB_PAT:
        logger.error("GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set")
        print("❌ Error: Please set GITHUB_PERSONAL_ACCESS_TOKEN")
        return
    
    logger.info("Starting CloudFormation GitOps Agent...")
    
    # Create the agent
    agent = await create_gitops_agent(
        github_org=GITHUB_ORG,
        github_infra_repo=GITHUB_INFRA_REPO,
        github_templates_repo=GITHUB_TEMPLATES_REPO,
        github_pat=GITHUB_PAT,
        default_reviewers=DEFAULT_REVIEWERS,
        region=AWS_REGION,
        bedrock_region=BEDROCK_REGION
    )
    
    # Interactive loop
    print("\n" + "="*70)
    print("CloudFormation GitOps Agent")
    print("="*70)
    print(f"\nGitHub Org: {GITHUB_ORG}")
    print(f"Infrastructure Repo: {GITHUB_INFRA_REPO}")
    print(f"Templates Repo: {GITHUB_TEMPLATES_REPO}")
    print(f"Default Region: {AWS_REGION}")
    print(f"Default Reviewers: {', '.join(DEFAULT_REVIEWERS)}")
    print("\nI create AWS infrastructure via GitOps (Pull Requests).")
    print("\nExamples:")
    print("  - 'Create an S3 bucket for storing logs'")
    print("  - 'Deploy an EC2 instance for web hosting'")
    print("  - 'What resources can I create?'")
    print("  - 'Check status of PR #123'")
    print("\nType 'exit' to quit.\n")
    
    while True:
        try:
            # Get user input
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\nGoodbye!")
                break
            
            # Run agent
            print("\nAgent: ", end="", flush=True)
            
            response = await agent.run(
                prompt=user_input,
                stream=True
            )
            
            # Stream response
            async for chunk in response:
                if chunk.get("type") == "text":
                    print(chunk.get("content", ""), end="", flush=True)
            
            print()  # New line after streaming
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            print(f"\nError: {str(e)}")
            print("Please try again or type 'exit' to quit.")


if __name__ == "__main__":
    asyncio.run(main())

