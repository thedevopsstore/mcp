# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CloudFormation Template Manager Tools."""

import os
import boto3
import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger
import git
from botocore.exceptions import ClientError, WaiterError


# CloudFormation intrinsic function constructors for YAML parsing
def _cfn_constructor(loader, tag_suffix, node):
    """
    Generic constructor for CloudFormation intrinsic functions.
    Converts YAML tags like !Ref to dictionaries like {'Ref': 'value'}.
    """
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node)
    else:
        value = None
    
    # Convert tag to CloudFormation function name (e.g., !Ref -> Ref)
    return {tag_suffix: value}


def _setup_cfn_yaml_constructors():
    """
    Register CloudFormation intrinsic function constructors with PyYAML.
    This allows parsing of CloudFormation templates with !Ref, !GetAtt, etc.
    """
    # List of CloudFormation intrinsic functions
    cfn_functions = [
        'Ref',
        'Condition',
        'Equals',
        'Not',
        'And',
        'Or',
        'If',
        'FindInMap',
        'Base64',
        'GetAtt',
        'GetAZs',
        'ImportValue',
        'Join',
        'Select',
        'Split',
        'Sub',
        'Transform',
        'Cidr',
    ]
    
    # Register multi-constructor for all CloudFormation functions
    for func in cfn_functions:
        yaml.SafeLoader.add_constructor(
            f'!{func}',
            lambda loader, node, tag=func: _cfn_constructor(loader, tag, node)
        )


# Initialize CloudFormation YAML constructors
_setup_cfn_yaml_constructors()


class TemplateRepository:
    """Manages CloudFormation template repository."""
    
    def __init__(self, repo_url: Optional[str] = None, local_path: Optional[str] = None):
        """
        Initialize template repository.
        
        Args:
            repo_url: Git repository URL (e.g., GitHub URL)
            local_path: Local path to templates (alternative to repo_url)
        """
        self.repo_url = repo_url or os.environ.get('CFN_TEMPLATE_REPO_URL')
        self.local_path = local_path or os.environ.get('CFN_TEMPLATE_LOCAL_PATH', '/tmp/cfn-templates')
        
        # Git authentication credentials (for private repos)
        self.git_username = os.environ.get('GIT_USERNAME')
        self.git_token = os.environ.get('GIT_TOKEN')
        self.git_ssh_key_path = os.environ.get('GIT_SSH_KEY_PATH')
        
        if self.repo_url:
            self._clone_or_update_repo()
        elif not os.path.exists(self.local_path):
            raise ValueError("Either repo_url or valid local_path must be provided")
    
    def _get_authenticated_repo_url(self) -> str:
        """
        Get repository URL with authentication embedded (for HTTPS).
        
        Returns:
            Authenticated repo URL or original URL
        """
        if self.git_username and self.git_token and self.repo_url.startswith('https://'):
            # Embed credentials in URL: https://username:token@github.com/org/repo.git
            url_parts = self.repo_url.replace('https://', '').split('/', 1)
            if len(url_parts) == 2:
                host = url_parts[0]
                path = url_parts[1]
                return f"https://{self.git_username}:{self.git_token}@{host}/{path}"
        
        return self.repo_url
    
    def _get_git_ssh_command(self) -> Optional[str]:
        """
        Get SSH command with custom key path if configured.
        
        Returns:
            SSH command string or None
        """
        if self.git_ssh_key_path and os.path.exists(self.git_ssh_key_path):
            # Use custom SSH key
            return f'ssh -i {self.git_ssh_key_path} -o StrictHostKeyChecking=no'
        return None
    
    def _clone_or_update_repo(self):
        """Clone or update the git repository (supports private repos)."""
        try:
            # Get authenticated URL for HTTPS repos
            repo_url = self._get_authenticated_repo_url()
            
            # Setup SSH command for SSH repos
            ssh_cmd = self._get_git_ssh_command()
            git_env = {}
            if ssh_cmd:
                git_env['GIT_SSH_COMMAND'] = ssh_cmd
            
            if os.path.exists(self.local_path):
                # Update existing repo
                repo = git.Repo(self.local_path)
                origin = repo.remotes.origin
                
                # Update origin URL if credentials changed
                if repo_url != self.repo_url:
                    origin.set_url(repo_url)
                
                # Pull with custom environment if needed
                with repo.git.custom_environment(**git_env) if git_env else repo.git:
                    origin.pull()
                
                logger.info(f"Updated template repository at {self.local_path}")
            else:
                # Clone new repo
                if git_env:
                    # Clone with custom SSH command
                    with git.Git().custom_environment(**git_env):
                        git.Repo.clone_from(repo_url, self.local_path)
                else:
                    # Clone normally (HTTPS with embedded credentials or public repo)
                    git.Repo.clone_from(repo_url, self.local_path)
                
                logger.info(f"Cloned template repository to {self.local_path}")
                
        except git.exc.GitCommandError as e:
            logger.error(f"Git command error: {str(e)}")
            if "Authentication failed" in str(e) or "403" in str(e):
                logger.error("Authentication failed. Check GIT_USERNAME, GIT_TOKEN, or GIT_SSH_KEY_PATH")
            raise
        except Exception as e:
            logger.error(f"Error managing git repository: {str(e)}")
            raise
    
    def list_resources(self) -> List[str]:
        """List all available resource types (directory names)."""
        try:
            resources = []
            base_path = Path(self.local_path)
            
            for item in base_path.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    resources.append(item.name)
            
            return sorted(resources)
        except Exception as e:
            logger.error(f"Error listing resources: {str(e)}")
            raise
    
    def get_template_path(self, resource_type: str) -> str:
        """
        Get the path to a CloudFormation template.
        
        Searches for template files in this order:
        1. Common naming patterns (template.yaml, cloudformation.yaml, etc.)
        2. Any .yaml or .yml file
        3. Any .json file
        
        Args:
            resource_type: Resource type directory name
            
        Returns:
            Path to the template file
            
        Raises:
            ValueError: If directory or template not found
        """
        template_dir = Path(self.local_path) / resource_type
        
        if not template_dir.exists():
            raise ValueError(f"Resource type '{resource_type}' not found")
        
        # Priority 1: Look for common template file names (preferred)
        preferred_names = [
            'template.yaml',
            'template.yml', 
            'cloudformation.yaml',
            'cloudformation.yml',
            'template.json',
            'cloudformation.json'
        ]
        
        for filename in preferred_names:
            template_path = template_dir / filename
            if template_path.exists():
                logger.debug(f"Found template: {template_path}")
                return str(template_path)
        
        # Priority 2: Look for ANY .yaml or .yml file
        yaml_files = list(template_dir.glob('*.yaml')) + list(template_dir.glob('*.yml'))
        if yaml_files:
            template_path = yaml_files[0]  # Use first found
            logger.info(f"Using YAML file: {template_path.name}")
            return str(template_path)
        
        # Priority 3: Look for ANY .json file
        json_files = list(template_dir.glob('*.json'))
        if json_files:
            template_path = json_files[0]  # Use first found
            logger.info(f"Using JSON file: {template_path.name}")
            return str(template_path)
        
        # No template files found
        raise ValueError(
            f"No CloudFormation template found in {template_dir}. "
            f"Expected: .yaml, .yml, or .json file"
        )
    
    def read_template(self, resource_type: str) -> Dict[str, Any]:
        """Read and parse a CloudFormation template."""
        template_path = self.get_template_path(resource_type)
        
        try:
            with open(template_path, 'r') as f:
                if template_path.endswith('.json'):
                    return json.load(f)
                else:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error reading template: {str(e)}")
            raise
    
    def get_template_body(self, resource_type: str) -> str:
        """Get the raw template body as string."""
        template_path = self.get_template_path(resource_type)
        
        try:
            with open(template_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading template body: {str(e)}")
            raise


class CloudFormationTemplateManager:
    """Manages CloudFormation operations with pre-existing templates."""
    
    def __init__(self, repo_url: Optional[str] = None, local_path: Optional[str] = None, region_name: Optional[str] = None):
        """
        Initialize CloudFormation Template Manager.
        
        Args:
            repo_url: Git repository URL
            local_path: Local path to templates
            region_name: AWS region (defaults to environment or us-east-1)
        """
        self.region_name = region_name or os.environ.get('AWS_REGION', 'us-east-1')
        self.cfn_client = boto3.client('cloudformation', region_name=self.region_name)
        self.repository = TemplateRepository(repo_url=repo_url, local_path=local_path)
        logger.info(f"Initialized CloudFormation Template Manager for region {self.region_name}")
    
    def list_available_resources(self) -> Dict[str, Any]:
        """List all available resource types from the template repository."""
        try:
            resources = self.repository.list_resources()
            return {
                "success": True,
                "resources": resources,
                "count": len(resources),
                "message": f"Found {len(resources)} resource types available"
            }
        except Exception as e:
            logger.error(f"Error listing resources: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_template_info(self, resource_type: str) -> Dict[str, Any]:
        """Get detailed information about a CloudFormation template."""
        try:
            template = self.repository.read_template(resource_type)
            
            info = {
                "success": True,
                "resource_type": resource_type,
                "description": template.get('Description', 'No description available'),
                "parameters": list(template.get('Parameters', {}).keys()),
                "resources": list(template.get('Resources', {}).keys()),
                "outputs": list(template.get('Outputs', {}).keys())
            }
            
            return info
        except Exception as e:
            logger.error(f"Error getting template info: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_template_parameters(self, resource_type: str) -> Dict[str, Any]:
        """Get detailed parameter information for a template."""
        try:
            template = self.repository.read_template(resource_type)
            parameters = template.get('Parameters', {})
            
            param_details = {}
            for param_name, param_config in parameters.items():
                param_details[param_name] = {
                    "type": param_config.get('Type', 'String'),
                    "description": param_config.get('Description', ''),
                    "default": param_config.get('Default'),
                    "allowed_values": param_config.get('AllowedValues', []),
                    "allowed_pattern": param_config.get('AllowedPattern'),
                    "constraint_description": param_config.get('ConstraintDescription'),
                    "min_length": param_config.get('MinLength'),
                    "max_length": param_config.get('MaxLength'),
                    "min_value": param_config.get('MinValue'),
                    "max_value": param_config.get('MaxValue'),
                    "no_echo": param_config.get('NoEcho', False)
                }
            
            return {
                "success": True,
                "resource_type": resource_type,
                "parameters": param_details,
                "required_parameters": [name for name, config in parameters.items() if 'Default' not in config]
            }
        except Exception as e:
            logger.error(f"Error getting template parameters: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def validate_parameters(self, resource_type: str, parameters: Dict[str, str]) -> Dict[str, Any]:
        """Validate parameters against template requirements."""
        try:
            param_info = self.get_template_parameters(resource_type)
            
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
            
            # Check for unknown parameters
            for param_name in parameters:
                if param_name not in template_params:
                    warnings.append(f"Unknown parameter: {param_name}")
            
            # Validate parameter values
            for param_name, param_value in parameters.items():
                if param_name in template_params:
                    param_def = template_params[param_name]
                    
                    # Validate allowed values
                    if param_def.get('allowed_values') and param_value not in param_def['allowed_values']:
                        errors.append(f"Invalid value for {param_name}. Allowed: {param_def['allowed_values']}")
                    
                    # Validate string length
                    if param_def.get('min_length') and len(param_value) < param_def['min_length']:
                        errors.append(f"{param_name} must be at least {param_def['min_length']} characters")
                    
                    if param_def.get('max_length') and len(param_value) > param_def['max_length']:
                        errors.append(f"{param_name} must be at most {param_def['max_length']} characters")
            
            is_valid = len(errors) == 0
            
            return {
                "success": True,
                "valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "message": "Parameters are valid" if is_valid else "Parameter validation failed"
            }
        except Exception as e:
            logger.error(f"Error validating parameters: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_change_set(self, resource_type: str, parameters: Dict[str, str], stack_name: str, 
                         change_set_type: str = "CREATE") -> Dict[str, Any]:
        """
        Create a CloudFormation change set.
        
        Args:
            resource_type: Type of resource (directory name in repo)
            parameters: Parameter key-value pairs
            stack_name: CloudFormation stack name
            change_set_type: CREATE or UPDATE
        """
        try:
            # Validate parameters first
            validation = self.validate_parameters(resource_type, parameters)
            if not validation.get('valid'):
                return validation
            
            # Get template body
            template_body = self.repository.get_template_body(resource_type)
            
            # Convert parameters to CloudFormation format
            cfn_parameters = [
                {'ParameterKey': key, 'ParameterValue': value}
                for key, value in parameters.items()
            ]
            
            # Create change set
            change_set_name = f"{stack_name}-changeset-{change_set_type.lower()}"
            
            response = self.cfn_client.create_change_set(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cfn_parameters,
                ChangeSetName=change_set_name,
                ChangeSetType=change_set_type,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
            )
            
            logger.info(f"Created change set: {change_set_name}")
            
            return {
                "success": True,
                "change_set_id": response['Id'],
                "change_set_name": change_set_name,
                "stack_name": stack_name,
                "message": f"Change set created successfully. Review with describe_change_set before executing."
            }
        except ClientError as e:
            logger.error(f"AWS error creating change set: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error creating change set: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def describe_change_set(self, change_set_name: str, stack_name: str) -> Dict[str, Any]:
        """Describe a CloudFormation change set to see what will change."""
        try:
            response = self.cfn_client.describe_change_set(
                ChangeSetName=change_set_name,
                StackName=stack_name
            )
            
            changes = []
            for change in response.get('Changes', []):
                resource_change = change.get('ResourceChange', {})
                changes.append({
                    "action": resource_change.get('Action'),
                    "logical_id": resource_change.get('LogicalResourceId'),
                    "physical_id": resource_change.get('PhysicalResourceId'),
                    "resource_type": resource_change.get('ResourceType'),
                    "replacement": resource_change.get('Replacement', 'N/A'),
                    "scope": resource_change.get('Scope', [])
                })
            
            return {
                "success": True,
                "change_set_name": change_set_name,
                "stack_name": stack_name,
                "status": response.get('Status'),
                "status_reason": response.get('StatusReason', ''),
                "changes": changes,
                "changes_count": len(changes),
                "parameters": response.get('Parameters', [])
            }
        except ClientError as e:
            logger.error(f"AWS error describing change set: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error describing change set: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def execute_change_set(self, change_set_name: str, stack_name: str, wait: bool = False) -> Dict[str, Any]:
        """
        Execute a CloudFormation change set.
        
        Args:
            change_set_name: Name of the change set
            stack_name: Name of the stack
            wait: Whether to wait for completion
        """
        try:
            response = self.cfn_client.execute_change_set(
                ChangeSetName=change_set_name,
                StackName=stack_name
            )
            
            result = {
                "success": True,
                "stack_name": stack_name,
                "message": f"Change set {change_set_name} execution started"
            }
            
            if wait:
                logger.info(f"Waiting for stack operation to complete...")
                try:
                    waiter = self.cfn_client.get_waiter('stack_create_complete')
                    waiter.wait(StackName=stack_name)
                    result["message"] = f"Stack {stack_name} created successfully"
                except WaiterError as e:
                    result["warning"] = "Stack operation timed out or failed"
                    result["waiter_error"] = str(e)
            
            return result
        except ClientError as e:
            logger.error(f"AWS error executing change set: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error executing change set: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_stack_status(self, stack_name: str) -> Dict[str, Any]:
        """Get the current status of a CloudFormation stack."""
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            
            if not response.get('Stacks'):
                return {
                    "success": False,
                    "error": f"Stack {stack_name} not found"
                }
            
            stack = response['Stacks'][0]
            
            return {
                "success": True,
                "stack_name": stack['StackName'],
                "status": stack['StackStatus'],
                "status_reason": stack.get('StackStatusReason', ''),
                "creation_time": str(stack.get('CreationTime', '')),
                "last_updated_time": str(stack.get('LastUpdatedTime', '')),
                "outputs": [
                    {
                        "key": output['OutputKey'],
                        "value": output['OutputValue'],
                        "description": output.get('Description', '')
                    }
                    for output in stack.get('Outputs', [])
                ],
                "parameters": [
                    {
                        "key": param['ParameterKey'],
                        "value": param['ParameterValue']
                    }
                    for param in stack.get('Parameters', [])
                ]
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'ValidationError':
                return {
                    "success": True,
                    "stack_name": stack_name,
                    "status": "DOES_NOT_EXIST",
                    "message": f"Stack {stack_name} does not exist"
                }
            logger.error(f"AWS error getting stack status: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error getting stack status: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def delete_stack(self, stack_name: str, wait: bool = False) -> Dict[str, Any]:
        """
        Delete a CloudFormation stack.
        
        Args:
            stack_name: Name of the stack to delete
            wait: Whether to wait for deletion to complete
        """
        try:
            self.cfn_client.delete_stack(StackName=stack_name)
            
            result = {
                "success": True,
                "stack_name": stack_name,
                "message": f"Stack {stack_name} deletion initiated"
            }
            
            if wait:
                logger.info(f"Waiting for stack deletion to complete...")
                try:
                    waiter = self.cfn_client.get_waiter('stack_delete_complete')
                    waiter.wait(StackName=stack_name)
                    result["message"] = f"Stack {stack_name} deleted successfully"
                except WaiterError as e:
                    result["warning"] = "Stack deletion timed out or failed"
                    result["waiter_error"] = str(e)
            
            return result
        except ClientError as e:
            logger.error(f"AWS error deleting stack: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error deleting stack: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


class CFNTemplateManagerTools:
    """MCP Tools for CloudFormation Template Manager."""
    
    def __init__(self, repo_url: Optional[str] = None, local_path: Optional[str] = None, region_name: Optional[str] = None):
        """Initialize CFN Template Manager tools."""
        self.manager = CloudFormationTemplateManager(
            repo_url=repo_url,
            local_path=local_path,
            region_name=region_name
        )
    
    def register(self, mcp):
        """Register all tools with the MCP server."""
        
        @mcp.tool()
        def list_available_resources() -> Dict[str, Any]:
            """
            List all available resource types from the CloudFormation template repository.
            
            Returns a list of resource types (e.g., 's3', 'ec2', 'alb') that have templates available.
            """
            return self.manager.list_available_resources()
        
        @mcp.tool()
        def get_template_info(resource_type: str) -> Dict[str, Any]:
            """
            Get detailed information about a CloudFormation template.
            
            Args:
                resource_type: Type of resource (e.g., 's3', 'ec2', 'alb')
            
            Returns information about the template including description, parameters, resources, and outputs.
            """
            return self.manager.get_template_info(resource_type)
        
        @mcp.tool()
        def get_template_parameters(resource_type: str) -> Dict[str, Any]:
            """
            Get detailed parameter information for a CloudFormation template.
            
            Args:
                resource_type: Type of resource (e.g., 's3', 'ec2', 'alb')
            
            Returns detailed information about each parameter including type, description, defaults,
            allowed values, and constraints. Use this to understand what parameters to ask the user for.
            """
            return self.manager.get_template_parameters(resource_type)
        
        @mcp.tool()
        def validate_parameters(resource_type: str, parameters: Dict[str, str]) -> Dict[str, Any]:
            """
            Validate parameters against template requirements.
            
            Args:
                resource_type: Type of resource (e.g., 's3', 'ec2', 'alb')
                parameters: Dictionary of parameter key-value pairs
            
            Returns validation results including any errors or warnings.
            """
            return self.manager.validate_parameters(resource_type, parameters)
        
        @mcp.tool()
        def create_change_set(
            resource_type: str,
            parameters: Dict[str, str],
            stack_name: str,
            change_set_type: str = "CREATE"
        ) -> Dict[str, Any]:
            """
            Create a CloudFormation change set.
            
            Args:
                resource_type: Type of resource (e.g., 's3', 'ec2', 'alb')
                parameters: Dictionary of parameter key-value pairs
                stack_name: Name for the CloudFormation stack
                change_set_type: Either "CREATE" for new stacks or "UPDATE" for existing stacks
            
            Creates a change set that can be reviewed before execution. Returns the change set ID.
            """
            return self.manager.create_change_set(resource_type, parameters, stack_name, change_set_type)
        
        @mcp.tool()
        def describe_change_set(change_set_name: str, stack_name: str) -> Dict[str, Any]:
            """
            Describe a CloudFormation change set to see what will change.
            
            Args:
                change_set_name: Name of the change set
                stack_name: Name of the stack
            
            Returns detailed information about the changes that will be made if the change set is executed.
            ALWAYS use this to show the user what will change before executing.
            """
            return self.manager.describe_change_set(change_set_name, stack_name)
        
        @mcp.tool()
        def execute_change_set(change_set_name: str, stack_name: str, wait: bool = False) -> Dict[str, Any]:
            """
            Execute a CloudFormation change set to create or update resources.
            
            Args:
                change_set_name: Name of the change set to execute
                stack_name: Name of the stack
                wait: Whether to wait for the operation to complete (default: False)
            
            Executes the change set and creates/updates the CloudFormation stack.
            ALWAYS get user confirmation before calling this.
            """
            return self.manager.execute_change_set(change_set_name, stack_name, wait)
        
        @mcp.tool()
        def get_stack_status(stack_name: str) -> Dict[str, Any]:
            """
            Get the current status of a CloudFormation stack.
            
            Args:
                stack_name: Name of the stack
            
            Returns the current status, outputs, and other details about the stack.
            """
            return self.manager.get_stack_status(stack_name)
        
        @mcp.tool()
        def delete_stack(stack_name: str, wait: bool = False) -> Dict[str, Any]:
            """
            Delete a CloudFormation stack.
            
            Args:
                stack_name: Name of the stack to delete
                wait: Whether to wait for deletion to complete (default: False)
            
            Deletes the stack and all its resources.
            ALWAYS get user confirmation before calling this.
            """
            return self.manager.delete_stack(stack_name, wait)

