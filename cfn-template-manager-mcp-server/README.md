# CloudFormation Template Manager MCP Server

An MCP (Model Context Protocol) server for managing AWS CloudFormation deployments using pre-existing templates from a Git repository.

## Overview

This MCP server enables AI agents to:
- Use your own CloudFormation templates instead of dynamically generating them
- Automatically discover available resource types from your template repository
- Parse templates and extract required parameters
- Guide users through parameter collection
- Create and review change sets before execution
- Deploy resources safely with user confirmation

## Features

### 🎯 Key Capabilities

- **Template Discovery**: Automatically lists all available resource types from your Git repository
- **Parameter Intelligence**: Parses CloudFormation templates to understand required parameters
- **Validation**: Validates parameters against template constraints before deployment
- **Safe Deployments**: Creates change sets for review before execution
- **Stack Management**: Monitor stack status, outputs, and manage lifecycle

### 🛠️ MCP Tools

1. **`list_available_resources()`** - List all resource types in your repository
2. **`get_template_info(resource_type)`** - Get template overview
3. **`get_template_parameters(resource_type)`** - Get detailed parameter requirements
4. **`validate_parameters(resource_type, parameters)`** - Validate parameter values
5. **`create_change_set(resource_type, parameters, stack_name)`** - Create a change set
6. **`describe_change_set(change_set_name, stack_name)`** - Review changes before execution
7. **`execute_change_set(change_set_name, stack_name)`** - Execute the change set
8. **`get_stack_status(stack_name)`** - Monitor stack status and outputs
9. **`delete_stack(stack_name)`** - Delete a stack

## Setup

### Prerequisites

- Python 3.10+
- AWS credentials configured
- Git repository with CloudFormation templates

### Template Repository Structure

Your Git repository should be organized by resource type:

```
cfn-templates/
├── s3/
│   └── template.yaml          # S3 bucket template
├── ec2/
│   └── template.yaml          # EC2 instance template
├── alb/
│   └── template.yaml          # Application Load Balancer template
├── rds/
│   └── template.yaml          # RDS database template
└── lambda/
    └── template.yaml          # Lambda function template
```

Each directory represents a resource type, and should contain:
- `template.yaml` or `template.yml` (CloudFormation template)
- Alternatively: `cloudformation.yaml`, `cloudformation.yml`, or `template.json`

### Installation

```bash
cd mcp/src/cfn-template-manager-mcp-server
pip install -e .
```

### Configuration

Set environment variables:

```bash
# Required: Git repository URL or local path
export CFN_TEMPLATE_REPO_URL="https://github.com/your-org/cfn-templates.git"
# OR
export CFN_TEMPLATE_LOCAL_PATH="/path/to/local/templates"

# For PRIVATE repositories - choose one:
# Method 1: Personal Access Token (HTTPS)
export GIT_USERNAME="your-github-username"
export GIT_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Method 2: SSH Key (for git@github.com:org/repo.git)
export GIT_SSH_KEY_PATH="/path/to/your/ssh/key"

# Optional: AWS region (defaults to us-east-1)
export AWS_REGION="us-east-1"

# AWS credentials (if not using default profile or IRSA)
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

**For detailed private repository setup, see [PRIVATE_REPO_GUIDE.md](PRIVATE_REPO_GUIDE.md)**

### Running the Server

```bash
# Run as HTTP server
cfn-template-manager-mcp-server

# Or with Python
python -m awslabs.cfn_template_manager.server
```

The server will start on `http://0.0.0.0:8080`

## Usage Example

### Typical Workflow

1. **User**: "Create an S3 bucket for storing logs"

2. **Agent** calls `list_available_resources()`:
   ```json
   {
     "resources": ["s3", "ec2", "alb", "rds"],
     "count": 4
   }
   ```

3. **Agent** calls `get_template_parameters("s3")`:
   ```json
   {
     "parameters": {
       "BucketName": {
         "type": "String",
         "description": "Name of the S3 bucket",
         "allowed_pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$"
       },
       "Environment": {
         "type": "String",
         "allowed_values": ["dev", "staging", "prod"],
         "default": "dev"
       }
     },
     "required_parameters": ["BucketName"]
   }
   ```

4. **Agent** asks user: "What would you like to name the bucket?"

5. **User**: "my-app-logs-bucket"

6. **Agent** calls `create_change_set()`:
   ```python
   create_change_set(
     resource_type="s3",
     parameters={
       "BucketName": "my-app-logs-bucket",
       "Environment": "prod"
     },
     stack_name="my-app-logs-bucket-stack"
   )
   ```

7. **Agent** calls `describe_change_set()` and shows user:
   ```
   Changes to be made:
   - CREATE: AWS::S3::Bucket (LogsBucket)
   - CREATE: AWS::S3::BucketPolicy (LogsBucketPolicy)
   ```

8. **Agent** asks: "Execute these changes?"

9. **User**: "Yes"

10. **Agent** calls `execute_change_set()` and monitors with `get_stack_status()`

## Docker Deployment

### Build

```bash
docker build -t cfn-template-manager-mcp-server .
```

### Run

```bash
docker run -d \
  -p 8080:8080 \
  -e CFN_TEMPLATE_REPO_URL="https://github.com/your-org/cfn-templates.git" \
  -e AWS_REGION="us-east-1" \
  -e AWS_ACCESS_KEY_ID="your-key" \
  -e AWS_SECRET_ACCESS_KEY="your-secret" \
  cfn-template-manager-mcp-server
```

## Kubernetes Deployment

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cfn-template-manager-config
data:
  CFN_TEMPLATE_REPO_URL: "https://github.com/your-org/cfn-templates.git"
  AWS_REGION: "us-east-1"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cfn-template-manager
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cfn-template-manager
  template:
    metadata:
      labels:
        app: cfn-template-manager
    spec:
      containers:
      - name: cfn-template-manager
        image: cfn-template-manager-mcp-server:latest
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: cfn-template-manager-config
        - secretRef:
            name: aws-credentials
---
apiVersion: v1
kind: Service
metadata:
  name: cfn-template-manager
spec:
  selector:
    app: cfn-template-manager
  ports:
  - port: 8080
    targetPort: 8080
  type: LoadBalancer
```

## Integration with Strands Agent

See [example_infra_agent.py](../../../examples/cfn_infrastructure_agent.py) for a complete example of an AI agent that uses this MCP server.

## Security Considerations

1. **AWS Credentials**: Use IAM roles in production, not access keys
2. **Git Authentication**: For private repos, use SSH keys or GitHub tokens
3. **Template Validation**: Always review change sets before execution
4. **Least Privilege**: Grant only required CloudFormation permissions
5. **Network Security**: Run MCP server in private network, use authentication

## Troubleshooting

### Template Not Found

**Error**: `Resource type 'xxx' not found`

**Solution**: Check that the directory exists in your template repository and contains a valid template file.

### Git Clone Failed

**Error**: `Error managing git repository`

**Solution**: 
- Verify `CFN_TEMPLATE_REPO_URL` is correct
- For private repos, ensure credentials are configured
- Check network connectivity

### AWS Permissions Error

**Error**: `An error occurred (AccessDenied)`

**Solution**: Ensure AWS credentials have permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateChangeSet",
        "cloudformation:DescribeChangeSet",
        "cloudformation:ExecuteChangeSet",
        "cloudformation:DescribeStacks",
        "cloudformation:DeleteStack"
      ],
      "Resource": "*"
    }
  ]
}
```

## License

Apache-2.0

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](../../CONTRIBUTING.md)

