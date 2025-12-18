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
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
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
                                 parameters: Dict[str, str], template_filename: str,
                                 region: str = "us-east-1",
                                 requester: str = "agent") -> str:
    """
    Generate stack configuration file for GitOps deployment.
    
    Creates a JSON configuration file with stack metadata, parameters, and tags
    that GitHub Actions will use to deploy the CloudFormation stack.
    
    NOTE: This format is NOT directly usable with AWS CLI commands. It's a custom
    GitOps format that GitHub Actions parses. For AWS CLI compatibility, use
    generate_aws_cli_parameters() instead.
    
    Args:
        template_type: Resource type (e.g., 's3', 'ec2', 'lambda')
        stack_name: CloudFormation stack name
        parameters: Parameter key-value pairs
        template_filename: Actual template filename discovered (e.g., 'bucket-config.yaml')
        region: AWS region (default: us-east-1)
        requester: User who requested (email or username)
        
    Returns:
        JSON string of complete stack configuration (GitOps format)
    """
    config = {
        "request": {
            "resource_type": template_type,
            "stack_name": stack_name,
            "region": region,
            "requested_by": requester,
            "requested_at": datetime.utcnow().isoformat() + "Z"
        },
        "template": {
            "type": template_type,
            "source": f"templates/{template_type}/{template_filename}"
        },
        "parameters": parameters,
        "tags": {
            "Environment": parameters.get('Environment', 'dev'),
            "ManagedBy": "GitOps",
            "RequestedBy": requester
        }
    }
    
    return json.dumps(config, indent=2)


@tool
def generate_aws_cli_parameters(parameters: Dict[str, str]) -> str:
    """
    Generate AWS CLI-compatible parameter file for CloudFormation commands.
    
    Creates a JSON parameter file in the format required by AWS CloudFormation CLI
    commands like create-stack, update-stack, and deploy.
    
    Format: Array of objects with ParameterKey and ParameterValue fields.
    
    Usage with AWS CLI:
        aws cloudformation create-stack \\
            --stack-name my-stack \\
            --template-body file://template.yaml \\
            --parameters file://parameters.json
    
    Args:
        parameters: Parameter key-value pairs (e.g., {"BucketName": "my-bucket", "Environment": "prod"})
        
    Returns:
        JSON string in AWS CLI parameter file format
    """
    param_list = [
        {"ParameterKey": key, "ParameterValue": str(value)}
        for key, value in parameters.items()
    ]
    
    return json.dumps(param_list, indent=2)


# ============================================================================
# Agent System Prompt
# ============================================================================

GITOPS_AGENT_PROMPT = """
You create AWS infrastructure via GitOps: read CloudFormation templates from GitHub, collect parameters, create AWS CLI-compatible parameter files, raise PRs for approval.

## Config
**Org:** {github_org} | **Infra Repo:** {github_infra_repo} | **Templates Repo:** {github_templates_repo}
**Paths:** Templates: `templates/{{type}}/` | Parameter files: `stacks/{{type}}/{{stack}}.json`

## Variables
- `{{type}}` = resource type (lowercase, e.g., "s3", "ec2", "lambda") - capitalize when needed for display
- `{{filename}}` = template filename discovered (e.g., "bucket-config.yaml", "s3-template.yml")
- `{{stack}}` = stack name (e.g., "acme-logs-prod-stack")
- `{{region}}` = AWS region (e.g., "us-east-1")
- `{{user}}` = requester (email or username)
- `{{app}}` = application name (e.g., "acme")
- `{{resource}}` = resource name (e.g., "logs")
- `{{env}}` = environment (e.g., "prod", "dev", "staging")

## Tools
**GitHub MCP:** get_file_contents (works for files AND directories), create_branch, create_or_update_file, create_pull_request, request_reviewers, get_pull_request, list_pull_request_comments
**Python:** parse_cloudformation_template, extract_template_parameters, validate_template_parameters, generate_aws_cli_parameters

## Workflow
1. **Discover resources:** get_file_contents(owner, templates_repo, path="templates") → list directories [s3, ec2, ...]
2. **Find template:** get_file_contents(owner, templates_repo, path="templates/{{type}}") → find first .yaml/.yml/.json (templates can be ANY filename!)
3. **Read template:** get_file_contents(owner, templates_repo, path="templates/{{type}}/{{filename}}")
4. **Parse & extract:** parse_cloudformation_template() → extract_template_parameters()
5. **Collect params:** Ask user for each parameter, explain constraints (AllowedValues, Pattern, Min/Max), show examples
6. **Validate:** validate_template_parameters(template, params)
7. **Generate file:** generate_aws_cli_parameters(params) → AWS CLI-compatible JSON (use this for PR file, NOT generate_stack_configuration)
8. **Create PR:** create_branch → create_or_update_file(path="stacks/{{type}}/{{stack}}.json", content=aws_cli_params_json) → create_pull_request → request_reviewers

## Stack Naming
Pattern: `{{app}}-{{resource}}-{{env}}-stack` (e.g., acme-logs-prod-stack). Confirm with user.

## Parameter Collection Rules
- **Required:** Explain constraints clearly, show examples
- **Optional:** Show default value, ask if user wants to override
- **NoEcho:** Warn it's sensitive
- **AllowedValues:** Present as options (e.g., "Environment? (dev/staging/prod)")

## PR File Format
**CRITICAL:** PR file must use `generate_aws_cli_parameters()` output. Format: `[{{"ParameterKey": "key", "ParameterValue": "value"}}]` - directly usable with `aws cloudformation create-stack --parameters file://...`

## PR Description Template
Use {{type}} (capitalize when displaying, e.g., "s3" → "S3", "ec2" → "EC2")
```
## Resource Request: [capitalized {{type}}]
**Stack:** {{stack}} | **Template:** {{filename}} | **Region:** {{region}} | **By:** {{user}}
### Parameters: {{list}}
### Resources: {{parse CF template Resources section}}
### Validation: ✅ Params validated ✅ Stack name follows convention
### Deployment: GitHub Actions deploys after merge (~5-10 min)
```

## Safety
⚠️ Always PR (never deploy directly) | ⚠️ Always validate before PR | ⚠️ Explain each parameter clearly

## Example
```
User: "Create S3 bucket for logs"
You: [get_file_contents(path="templates") → "s3"]
     [get_file_contents(path="templates/s3") → "bucket-config.yaml"]
     [get_file_contents(path="templates/s3/bucket-config.yaml")]
     [parse → extract_params]
     "BucketName (unique, lowercase, 3-63 chars)? Example: myapp-logs-2024"
User: "acme-logs-2024"
You: "Environment? (dev/staging/prod, default: dev)"
User: "prod"
You: "Stack name: acme-logs-prod-stack - OK?"
User: "yes"
You: [validate ✓] [generate_aws_cli_parameters(params)]
     [create_branch → create_or_update_file("stacks/s3/acme-logs-prod-stack.json") → create_pull_request]
     "✅ PR created | Stack: acme-logs-prod-stack | Format: AWS CLI-compatible"
```
"""


# ============================================================================
# Agent Class
# ============================================================================

class CFNGitOpsAgent:
    """CloudFormation GitOps Agent with proper context management"""
    
    def __init__(
        self,
        github_org: str,
        github_infra_repo: str,
        github_templates_repo: str,
        github_pat: str,
        default_reviewers: List[str] = None,
        region: str = "us-east-1",
        bedrock_region: str = "us-east-1"
    ):
        """
        Initialize CFN GitOps Agent configuration.
        
        Args:
            github_org: GitHub organization name
            github_infra_repo: Repository for stack configs (infrastructure-configs)
            github_templates_repo: Repository with CF templates (cfn-templates)
            github_pat: GitHub Personal Access Token
            default_reviewers: List of default PR reviewers
            region: Default AWS region for stacks
            bedrock_region: AWS region for Bedrock
        """
        self.github_org = github_org
        self.github_infra_repo = github_infra_repo
        self.github_templates_repo = github_templates_repo
        self.github_pat = github_pat
        self.default_reviewers = default_reviewers or ["infra-team"]
        self.region = region
        self.bedrock_region = bedrock_region
        
        self.mcp_client = None
        self.agent = None
        self._initialized = False
    
    def create_mcp_client(self):
        """Create the MCP client for GitHub's hosted service"""
        return MCPClient(
            lambda: streamablehttp_client(
                "https://api.githubcopilot.com/mcp/",
                headers={"Authorization": f"Bearer {self.github_pat}"},
                timeout=200,
                sse_read_timeout=200
            )
        )
    
    async def initialize(self):
        """Initialize the MCP client and agent once at startup"""
        if self._initialized:
            return self.agent
        
        try:
            print("Initializing CloudFormation GitOps Agent...")
            print("Connecting to GitHub MCP server...")
            
            self.mcp_client = self.create_mcp_client()
            
            # Manually enter the context manager and keep it active
            self.mcp_client.__enter__()
            
            print("GitHub MCP client connected successfully.")
            
            # Format system prompt with configuration
            formatted_prompt = GITOPS_AGENT_PROMPT.format(
                github_org=self.github_org,
                github_infra_repo=self.github_infra_repo,
                github_templates_repo=self.github_templates_repo
            )
            
            # Get tools from MCP server and add CloudFormation tools
            cf_tools = [
                parse_cloudformation_template,
                extract_template_parameters,
                validate_template_parameters,
                generate_stack_configuration,
                generate_aws_cli_parameters,
            ]
            tools = self.mcp_client.list_tools_sync() + cf_tools
            
            # Create the CloudFormation GitOps agent
            bedrock_model = BedrockModel(
                model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                region=self.bedrock_region
            )
            
            self.agent = Agent(
                model=bedrock_model,
                system_prompt=formatted_prompt,
                tools=tools,
                callback_handler=None
            )
            
            print("Tools registered with the agent:")
            for tool_spec in self.agent.tool_registry.get_all_tool_specs():
                print(f"  - {tool_spec['name']}")
            
            print("Agent initialization complete!")
            self._initialized = True
            return self.agent
                
        except Exception as e:
            print(f"Error initializing MCP client: {e}")
            raise
    
    async def run_conversation(self, user_input: str):
        """Run a conversation through the agent with async streaming"""
        if not self._initialized or self.agent is None:
            raise RuntimeError("Agent not initialized. Call initialize() first.")
        
        print("Processing...")

        try:
            agent_stream = self.agent.stream_async(user_input)
            
            print("\nResponse:")
            full_response = ""
            current_tool_info = None
            
            async for event in agent_stream:
                if "data" in event:
                    text_chunk = event["data"]
                    print(text_chunk, end="", flush=True)
                    full_response += text_chunk
                    
                elif "current_tool_use" in event:
                    tool_info = event["current_tool_use"]
                    if tool_info != current_tool_info:
                        current_tool_info = tool_info
                        print(f"\nUsing tool: {tool_info.get('name', 'Unknown')}")
                        if tool_info.get('input'):
                            print(f"   Input: {tool_info['input']}")
                            
                elif "reasoning" in event and event["reasoning"]:
                    if "reasoningText" in event:
                        print(f"\nReasoning: {event['reasoningText']}")
                        
                elif "result" in event:
                    print(f"\nTask completed")
                    
                elif "force_stop" in event and event["force_stop"]:
                    reason = event.get("force_stop_reason", "Unknown reason")
                    print(f"\nStream stopped: {reason}")
                    break
                    
                elif "start" in event and event["start"]:
                    print("Starting new processing cycle...")
                    
                elif "init_event_loop" in event and event["init_event_loop"]:
                    print("Initializing event loop...")

            print("\n" + "="*50)
            return {"final_response": full_response, "stream_completed": True}
            
        except Exception as e:
            print(f"Stream error: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup MCP client resources"""
        if self.mcp_client and self._initialized:
            try:
                print("Cleaning up MCP client...")
                self.mcp_client.__exit__(None, None, None)
            except Exception as e:
                print(f"Error during cleanup: {e}")


# ============================================================================
# Main Interactive Loop
# ============================================================================

async def main():
    """Main interactive loop using class-based approach"""
    
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
    
    # Create agent manager
    agent_manager = CFNGitOpsAgent(
        github_org=GITHUB_ORG,
        github_infra_repo=GITHUB_INFRA_REPO,
        github_templates_repo=GITHUB_TEMPLATES_REPO,
        github_pat=GITHUB_PAT,
        default_reviewers=DEFAULT_REVIEWERS,
        region=AWS_REGION,
        bedrock_region=BEDROCK_REGION
    )
    
    try:
        # Initialize the agent
        await agent_manager.initialize()
        
        # Interactive loop
        print("\n" + "="*70)
        print("CloudFormation GitOps Agent Ready!")
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
        print("\nType 'quit' to exit.\n")
        
        while True:
            try:
                user_input = input("You > ").strip()
                
                if user_input.lower() in ["quit", "exit", "q"]:
                    print("Goodbye!")
                    break
                    
                if not user_input:
                    continue
                    
                await agent_manager.run_conversation(user_input)
                
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                break
            except Exception as e:
                print(f"\nError: {e}")
                
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
    finally:
        # Cleanup when done
        await agent_manager.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

