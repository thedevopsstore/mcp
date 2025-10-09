# Private Git Repository Authentication Guide

Complete guide for accessing private Git repositories with the CloudFormation Template Manager MCP Server.

## 🔐 Supported Authentication Methods

The MCP server supports **three authentication methods** for private repositories:

1. **Personal Access Token (PAT)** - HTTPS with token (recommended for GitHub/GitLab)
2. **SSH Key** - SSH protocol with private key (recommended for automated systems)
3. **Deploy Key** - Repository-specific SSH key (most secure)

## 📊 Method Comparison

| Method | Security | Kubernetes | Ease of Setup | Best For |
|--------|----------|------------|---------------|----------|
| **Personal Access Token** | ⭐⭐⭐ | ✅ Easy | ✅ Simple | Development, GitHub Apps |
| **SSH Key** | ⭐⭐⭐⭐ | ✅ Good | ⚠️ Moderate | Production, CI/CD |
| **Deploy Key** | ⭐⭐⭐⭐⭐ | ✅ Good | ⚠️ Moderate | Production (single repo) |

## 🎯 Method 1: Personal Access Token (PAT)

### For GitHub

#### Step 1: Create Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a name: "CFN MCP Server"
4. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - Or just `repo:status` and `repo_deployment` if read-only
5. Click "Generate token"
6. **Copy the token immediately** (you won't see it again)

#### Step 2: Configure Environment Variables

```bash
# For local development
export GIT_USERNAME="your-github-username"
export GIT_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export CFN_TEMPLATE_REPO_URL="https://github.com/your-org/cfn-templates.git"
```

#### Step 3: For Kubernetes

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: git-credentials
  namespace: cfn-infrastructure
type: Opaque
stringData:
  GIT_USERNAME: "your-github-username"
  GIT_TOKEN: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: cfn-template-manager
        env:
        - name: CFN_TEMPLATE_REPO_URL
          value: "https://github.com/your-org/cfn-templates.git"
        envFrom:
        - secretRef:
            name: git-credentials
```

### For GitLab

#### Step 1: Create Personal Access Token

1. Go to GitLab → Preferences → Access Tokens
2. Create a new token:
   - Name: "CFN MCP Server"
   - Scopes: ✅ `read_repository`
   - Expiration: Set appropriate date
3. Click "Create personal access token"
4. **Copy the token**

#### Step 2: Configure

```bash
export GIT_USERNAME="your-gitlab-username"
export GIT_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"
export CFN_TEMPLATE_REPO_URL="https://gitlab.com/your-org/cfn-templates.git"
```

### For Bitbucket

#### Step 1: Create App Password

1. Go to Bitbucket → Personal settings → App passwords
2. Create app password:
   - Label: "CFN MCP Server"
   - Permissions: ✅ Repositories: Read
3. Copy the password

#### Step 2: Configure

```bash
export GIT_USERNAME="your-bitbucket-username"
export GIT_TOKEN="your-app-password"
export CFN_TEMPLATE_REPO_URL="https://bitbucket.org/your-org/cfn-templates.git"
```

## 🔑 Method 2: SSH Key

### Step 1: Generate SSH Key

```bash
# Generate a new SSH key pair
ssh-keygen -t ed25519 -C "cfn-mcp-server" -f ~/.ssh/cfn_mcp_key -N ""

# Or for older systems that don't support ed25519:
ssh-keygen -t rsa -b 4096 -C "cfn-mcp-server" -f ~/.ssh/cfn_mcp_key -N ""

# This creates:
# - ~/.ssh/cfn_mcp_key (private key - keep secret!)
# - ~/.ssh/cfn_mcp_key.pub (public key - add to Git provider)
```

### Step 2: Add Public Key to Git Provider

#### GitHub

1. Copy public key: `cat ~/.ssh/cfn_mcp_key.pub`
2. Go to GitHub → Settings → SSH and GPG keys
3. Click "New SSH key"
4. Paste the public key
5. Save

#### GitLab

1. Copy public key: `cat ~/.ssh/cfn_mcp_key.pub`
2. Go to GitLab → Preferences → SSH Keys
3. Paste the public key
4. Save

#### Bitbucket

1. Copy public key: `cat ~/.ssh/cfn_mcp_key.pub`
2. Go to Bitbucket → Personal settings → SSH keys
3. Add key

### Step 3: Configure for Local Development

```bash
export GIT_SSH_KEY_PATH="/Users/you/.ssh/cfn_mcp_key"
export CFN_TEMPLATE_REPO_URL="git@github.com:your-org/cfn-templates.git"
```

### Step 4: Configure for Kubernetes

```yaml
# Create secret with SSH key
apiVersion: v1
kind: Secret
metadata:
  name: git-ssh-key
  namespace: cfn-infrastructure
type: Opaque
data:
  ssh-privatekey: |
    # Base64 encoded private key
    # Create with: cat ~/.ssh/cfn_mcp_key | base64
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: cfn-template-manager
        env:
        - name: CFN_TEMPLATE_REPO_URL
          value: "git@github.com:your-org/cfn-templates.git"
        - name: GIT_SSH_KEY_PATH
          value: "/root/.ssh/id_rsa"
        volumeMounts:
        - name: ssh-key
          mountPath: /root/.ssh
          readOnly: true
      volumes:
      - name: ssh-key
        secret:
          secretName: git-ssh-key
          defaultMode: 0400
          items:
          - key: ssh-privatekey
            path: id_rsa
```

**Create the secret:**

```bash
# Create secret from file
kubectl create secret generic git-ssh-key \
  --from-file=ssh-privatekey=/Users/you/.ssh/cfn_mcp_key \
  -n cfn-infrastructure

# OR from command
kubectl create secret generic git-ssh-key \
  --from-literal=ssh-privatekey="$(cat ~/.ssh/cfn_mcp_key)" \
  -n cfn-infrastructure
```

## 🛡️ Method 3: Deploy Key (Most Secure)

Deploy keys are **repository-specific SSH keys** with read-only access to a single repository.

### Step 1: Generate Repository-Specific Key

```bash
# Generate key specifically for this repo
ssh-keygen -t ed25519 -C "cfn-templates-deploy-key" -f ~/.ssh/cfn_templates_deploy -N ""
```

### Step 2: Add Deploy Key to Repository

#### GitHub

1. Go to your repository → Settings → Deploy keys
2. Click "Add deploy key"
3. Title: "CFN MCP Server"
4. Key: Paste contents of `~/.ssh/cfn_templates_deploy.pub`
5. ✅ Allow write access (only if you need to push - usually not needed)
6. Click "Add key"

#### GitLab

1. Go to repository → Settings → Repository → Deploy Keys
2. Expand "Deploy Keys"
3. Add new key:
   - Title: "CFN MCP Server"
   - Key: Paste public key
   - ✅ Grant write permissions (only if needed)
4. Add key

#### Bitbucket

1. Go to repository → Settings → Access keys
2. Add key

### Step 3: Configure

Same as SSH key method, but using the deploy key:

```bash
export GIT_SSH_KEY_PATH="/Users/you/.ssh/cfn_templates_deploy"
export CFN_TEMPLATE_REPO_URL="git@github.com:your-org/cfn-templates.git"
```

## 🧪 Testing Authentication

### Test Locally

```bash
# Set credentials
export GIT_USERNAME="your-username"
export GIT_TOKEN="your-token"
export CFN_TEMPLATE_REPO_URL="https://github.com/your-org/cfn-templates.git"

# Start MCP server
cfn-template-manager-mcp-server

# Check logs for successful clone
# Should see: "Cloned template repository to /tmp/cfn-templates"
```

### Test with SSH

```bash
# Set SSH key
export GIT_SSH_KEY_PATH="/Users/you/.ssh/cfn_mcp_key"
export CFN_TEMPLATE_REPO_URL="git@github.com:your-org/cfn-templates.git"

# Test SSH connection
ssh -i $GIT_SSH_KEY_PATH -T git@github.com
# Should see: "Hi username! You've successfully authenticated..."

# Start MCP server
cfn-template-manager-mcp-server
```

### Test in Kubernetes

```bash
# Get pod name
POD=$(kubectl get pods -n cfn-infrastructure -l app=cfn-template-manager -o jsonpath='{.items[0].metadata.name}')

# Check logs for successful clone
kubectl logs -n cfn-infrastructure $POD | grep -i "clone"

# Should see: "Cloned template repository to /tmp/cfn-templates"

# Check if templates are accessible
kubectl exec -n cfn-infrastructure $POD -- ls -la /tmp/cfn-templates

# Should list your template directories (s3, ec2, lambda, etc.)
```

## 🔧 Complete Kubernetes Example

### Using Personal Access Token

```yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: cfn-infrastructure
---
# Git credentials secret
apiVersion: v1
kind: Secret
metadata:
  name: git-credentials
  namespace: cfn-infrastructure
type: Opaque
stringData:
  GIT_USERNAME: "your-github-username"
  GIT_TOKEN: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
---
# ConfigMap for non-sensitive config
apiVersion: v1
kind: ConfigMap
metadata:
  name: cfn-mcp-config
  namespace: cfn-infrastructure
data:
  CFN_TEMPLATE_REPO_URL: "https://github.com/your-org/cfn-templates.git"
  AWS_REGION: "us-east-1"
  LOG_LEVEL: "INFO"
---
# Service account with IRSA (for AWS credentials)
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cfn-mcp-service-account
  namespace: cfn-infrastructure
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::123456789012:role/cfn-mcp-server-role"
---
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cfn-template-manager
  namespace: cfn-infrastructure
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
      serviceAccountName: cfn-mcp-service-account
      containers:
      - name: cfn-template-manager
        image: cfn-template-manager-mcp-server:latest
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: cfn-mcp-config
        - secretRef:
            name: git-credentials  # Git authentication
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### Using SSH Key

```yaml
---
# SSH key secret
apiVersion: v1
kind: Secret
metadata:
  name: git-ssh-key
  namespace: cfn-infrastructure
type: Opaque
data:
  # Base64 encoded private key
  ssh-privatekey: LS0tLS1CRUdJTi... (base64 encoded)
---
# ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: cfn-mcp-config
  namespace: cfn-infrastructure
data:
  CFN_TEMPLATE_REPO_URL: "git@github.com:your-org/cfn-templates.git"
  GIT_SSH_KEY_PATH: "/root/.ssh/id_rsa"
  AWS_REGION: "us-east-1"
---
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cfn-template-manager
  namespace: cfn-infrastructure
spec:
  template:
    spec:
      serviceAccountName: cfn-mcp-service-account
      containers:
      - name: cfn-template-manager
        image: cfn-template-manager-mcp-server:latest
        envFrom:
        - configMapRef:
            name: cfn-mcp-config
        volumeMounts:
        - name: ssh-key
          mountPath: /root/.ssh
          readOnly: true
      volumes:
      - name: ssh-key
        secret:
          secretName: git-ssh-key
          defaultMode: 0400
          items:
          - key: ssh-privatekey
            path: id_rsa
```

## 🔒 Security Best Practices

### 1. Use Deploy Keys (Recommended)

```bash
# One key per repository
# Read-only access
# Can be revoked without affecting other systems
```

### 2. Rotate Credentials Regularly

```bash
# Personal Access Tokens: Set expiration dates
# SSH Keys: Rotate annually
# Monitor: Check Git provider's access logs
```

### 3. Minimal Permissions

```bash
# GitHub PAT:
# - For read-only: Just "repo:status" and "repo_deployment"
# - Avoid "repo" scope if possible

# Deploy Keys:
# - Read-only unless you need to push
```

### 4. Use Kubernetes Secrets

```bash
# Never hardcode credentials
# Always use Kubernetes secrets
# Use external secret managers (AWS Secrets Manager, Vault)
```

### 5. Audit Access

```bash
# GitHub: Settings → Security log
# GitLab: Admin → Audit Events
# Monitor for unauthorized access
```

## 🐛 Troubleshooting

### Issue 1: Authentication Failed (HTTPS)

**Error:** `Authentication failed for 'https://github.com/org/repo.git'`

**Solution:**
```bash
# Check credentials
echo $GIT_USERNAME
echo $GIT_TOKEN  # Should not be empty

# Test manually
git clone https://$GIT_USERNAME:$GIT_TOKEN@github.com/your-org/cfn-templates.git /tmp/test

# Check token permissions on GitHub
# Go to Settings → Developer settings → Personal access tokens
# Ensure token has 'repo' scope
```

### Issue 2: Permission Denied (SSH)

**Error:** `Permission denied (publickey)`

**Solution:**
```bash
# Test SSH connection
ssh -i $GIT_SSH_KEY_PATH -T git@github.com

# Check key permissions
chmod 600 $GIT_SSH_KEY_PATH

# Verify public key is added to Git provider

# Check SSH key format
cat $GIT_SSH_KEY_PATH
# Should start with: -----BEGIN OPENSSH PRIVATE KEY-----
```

### Issue 3: Host Key Verification Failed

**Error:** `Host key verification failed`

**Solution:**
```bash
# Add GitHub to known hosts
ssh-keyscan github.com >> ~/.ssh/known_hosts

# Or disable strict host checking (development only)
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no"
```

### Issue 4: Repository Not Found

**Error:** `Repository not found`

**Causes:**
1. Wrong repository URL
2. Insufficient permissions
3. Repository is private but no credentials provided

**Solution:**
```bash
# Verify URL
echo $CFN_TEMPLATE_REPO_URL

# Test access manually
git ls-remote $CFN_TEMPLATE_REPO_URL

# Check permissions on Git provider
```

## 📊 Environment Variables Summary

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `CFN_TEMPLATE_REPO_URL` | Yes* | Git repository URL | `https://github.com/org/repo.git` or `git@github.com:org/repo.git` |
| `CFN_TEMPLATE_LOCAL_PATH` | Yes* | Local directory | `/tmp/cfn-templates` |
| `GIT_USERNAME` | For HTTPS | Git username | `your-username` |
| `GIT_TOKEN` | For HTTPS | Personal access token | `ghp_xxxxx` or `glpat_xxxxx` |
| `GIT_SSH_KEY_PATH` | For SSH | Path to private key | `/root/.ssh/id_rsa` |
| `AWS_REGION` | No | AWS region | `us-east-1` |

*Either `CFN_TEMPLATE_REPO_URL` or `CFN_TEMPLATE_LOCAL_PATH` required

## 🎯 Recommended Setup by Environment

### Development
```bash
# Use Personal Access Token
export GIT_USERNAME="your-username"
export GIT_TOKEN="your-pat"
export CFN_TEMPLATE_REPO_URL="https://github.com/org/repo.git"
```

### Staging/Production
```yaml
# Use SSH with Deploy Key in Kubernetes
apiVersion: v1
kind: Secret
metadata:
  name: git-ssh-key
type: Opaque
data:
  ssh-privatekey: <base64-encoded-deploy-key>
```

### CI/CD
```bash
# Use PAT or SSH key from secret manager
# Inject at runtime
# Never commit to version control
```

## 📚 Additional Resources

- [GitHub: Creating a personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
- [GitHub: Managing deploy keys](https://docs.github.com/en/developers/overview/managing-deploy-keys)
- [GitLab: Project access tokens](https://docs.gitlab.com/ee/user/project/settings/project_access_tokens.html)
- [Kubernetes: Managing Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [GitPython Documentation](https://gitpython.readthedocs.io/)

---

## ✅ Quick Start Checklist

- [ ] Choose authentication method (PAT recommended for getting started)
- [ ] Create credentials (token or SSH key)
- [ ] Add credentials to Git provider
- [ ] Set environment variables
- [ ] Test authentication locally
- [ ] Create Kubernetes secret
- [ ] Deploy to Kubernetes
- [ ] Verify in pod logs
- [ ] Test template listing
- [ ] ✅ Ready to create infrastructure!

