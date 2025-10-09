FROM python:3.11-slim

WORKDIR /app

# Install git for repository cloning
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY awslabs/ /app/awslabs/
COPY pyproject.toml /app/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Expose port
EXPOSE 8080

# Set default environment variables
ENV CFN_TEMPLATE_LOCAL_PATH=/tmp/cfn-templates
ENV AWS_REGION=us-east-1

# Run the server
CMD ["python", "-m", "awslabs.cfn_template_manager.server"]

