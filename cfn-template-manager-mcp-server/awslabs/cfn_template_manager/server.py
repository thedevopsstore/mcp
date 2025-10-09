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

"""awslabs CloudFormation Template Manager MCP Server implementation."""

from awslabs.cfn_template_manager.tools import CFNTemplateManagerTools
from loguru import logger
from mcp.server.fastmcp import FastMCP
import uvicorn


mcp = FastMCP(
    'awslabs.cfn-template-manager-mcp-server',
    stateless_http=True,
    instructions="""Use this MCP server to manage AWS CloudFormation deployments using pre-existing templates from a Git repository.

This server provides a workflow for creating AWS resources:
1. List available resource types (e.g., s3, ec2, alb)
2. Get template information and required parameters
3. Validate parameter values
4. Create a change set with user-provided parameters
5. Review the change set to see what will be created/modified
6. Execute the change set after user confirmation
7. Monitor stack status

The templates are sourced from a Git repository organized by resource type, where each directory contains a CloudFormation template.

IMPORTANT: Always show the user the change set details before execution and get their confirmation.""",
    dependencies=[
        'boto3',
        'botocore',
        'pydantic',
        'loguru',
        'gitpython',
        'pyyaml',
    ],
)

# Initialize and register CFN Template Manager tools
try:
    cfn_tools = CFNTemplateManagerTools()
    cfn_tools.register(mcp)
    logger.info('CloudFormation Template Manager tools registered successfully')
except Exception as e:
    logger.error(f'Error initializing CFN Template Manager tools: {str(e)}')
    raise


def main():
    """Run the MCP server."""
    app = mcp.streamable_http_app()
    logger.info('CloudFormation Template Manager MCP server starting...')
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
    logger.info('CloudFormation Template Manager MCP server started')


if __name__ == '__main__':
    main()

