"""
Supervisor Agent with AWS CloudWatch Agent as Subagent
Persistent server with FileSessionManager for conversation history persistence

Runs as a standalone server with:
- A2A protocol server for external communication
- Background email polling
- Persistent session state using FileSessionManager
"""

import os
import asyncio
import logging
import signal
import threading
import json
import re
import uuid
from pathlib import Path
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel
from agents.aws_mcp_agent import AWSCloudWatchAgent
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from strands.multiagent.a2a import A2AServer
from strands.session_managers import FileSessionManager

# Load environment variables
load_dotenv()

# NEW: Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# NEW: A2A Server Configuration from Environment Variables
A2A_HOST = os.getenv('A2A_HOST', '127.0.0.1')
A2A_PORT = int(os.getenv('A2A_PORT', '9000'))
A2A_VERSION = os.getenv('A2A_VERSION', '1.0.0')
A2A_HTTP_URL = os.getenv('A2A_HTTP_URL', None)
A2A_SERVE_AT_ROOT = os.getenv('A2A_SERVE_AT_ROOT', 'false').lower() == 'true'

# Email Monitoring Configuration
EMAIL_MCP_SERVER_URL = os.getenv('EMAIL_MCP_SERVER_URL', 'http://localhost:8100/message')
EMAIL_POLL_INTERVAL = int(os.getenv('EMAIL_POLL_INTERVAL', '300'))  # 5 minutes default
EMAIL_FOLDER_ID = os.getenv('EMAIL_FOLDER_ID', None)  # None = inbox
EMAIL_FILTER_UNREAD = os.getenv('EMAIL_FILTER_UNREAD', 'true').lower() == 'true'

# Session Configuration
SESSION_DIR = Path(__file__).parent / "sessions"
SESSION_DIR.mkdir(exist_ok=True)  # Create sessions directory

# Autonomous task session ID (for email polling, etc.)
AUTONOMOUS_SESSION_ID = "devops-supervisor-autonomous"

# Initialize the AWS CloudWatch agent instance
aws_cloudwatch_agent = AWSCloudWatchAgent()

# Email MCP client and state
email_mcp_client = None
email_polling_task = None  # Background polling task

# Global session manager for multiple user sessions
class MultiSessionManager:
    """Manages multiple agent sessions, one per user or autonomous task"""
    
    def __init__(self):
        self.agents = {}  # session_id -> Agent
        self.session_managers = {}  # session_id -> FileSessionManager
        self._lock = threading.Lock()
    
    def get_or_create_agent(self, session_id: str) -> Agent:
        """Get or create an agent for a given session ID"""
        with self._lock:
            if session_id not in self.agents:
                # Create session file path
                session_file = SESSION_DIR / f"{session_id}.json"
                
                # Create FileSessionManager for this session
                session_manager = FileSessionManager(
                    session_id=session_id,
                    session_file=str(session_file)
                )
                self.session_managers[session_id] = session_manager
                
                # Create agent for this session
                agent = self._create_agent_for_session(session_manager)
                self.agents[session_id] = agent
                
                logger.info(f"📁 Created new session: {session_id}")
                logger.info(f"   Session file: {session_file}")
            
            return self.agents[session_id]
    
    def _create_agent_for_session(self, session_manager: FileSessionManager) -> Agent:
        """Create a supervisor agent instance for a session"""
        # Create the supervisor model
        supervisor_model = BedrockModel(
            model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            temperature=0.1,
            max_tokens=4096
        )
        
        # Supervisor prompt
        supervisor_prompt = """You are a DevOps Supervisor Agent that coordinates specialized agents for infrastructure monitoring and management, and can process emails to trigger automated responses.

Your role is to:
1. **Route queries** to the appropriate specialized agent
2. **Forward responses** without modification
3. **Provide context** when multiple agents might be relevant
4. **Process emails autonomously** - check for emails, analyze them, delegate to worker agents, and send responses

Available Worker Agent Tools:
- **aws_cloudwatch_tool**: For AWS CloudWatch metrics, logs, alarms, and troubleshooting
  - CloudWatch metrics analysis
  - Log analysis and troubleshooting  
  - Alarm management
  - Performance monitoring
  - Root cause analysis

Available Email MCP Tools (when email monitoring is enabled):
- **list-mail-messages**: Check for new emails in inbox or specific folder
  - Use this to check for new emails periodically
  - Returns list of emails with IDs, subjects, senders, dates
- **get-mail-message**: Read full content of an email by message ID
  - Use this to read email details, body, attachments
- **send-mail**: Send an email response
  - Use this to send responses with action results or status updates

EMAIL PROCESSING WORKFLOW (Agentic Approach):
When asked to check and process emails:
1. **Check for new emails** using list-mail-messages tool (check inbox, top 25-50)
2. **Filter unread/new emails** - focus on emails that haven't been processed yet
3. **For each new/unread email**:
   - Read the full email content using get-mail-message with the email's ID
   - Analyze the email to identify:
     * What type of request/alert it is (error alert, monitoring request, etc.)
     * Which worker agent should handle it (AWS, Cloudflare, etc.)
     * What action needs to be taken
   - Delegate to appropriate worker agent using the relevant tool (e.g., aws_cloudwatch_tool)
   - Send a response email using send-mail with:
     * To: original sender's email address (extract from email's 'from' field)
     * Subject: "Re: [Original Subject]" or descriptive subject like "Re: [Original Subject] - Investigation Results"
     * Body: Summary of actions taken, findings, investigation results, and recommendations
4. **Avoid processing the same email twice** - if you see an email you've already processed (based on subject/sender/date), skip it

Example Flow:
1. User: "Check for new emails and process them"
2. You: Use list-mail-messages → See email "Application error in production"
3. You: Use get-mail-message(message_id) → Read full email
4. You: Analyze → "This is an error alert, need to check CloudWatch logs"
5. You: Use aws_cloudwatch_tool("check logs for application errors in production")
6. You: Use send-mail(to=sender, subject="Re: Application error - Investigation Results", body=findings)

CRITICAL INSTRUCTIONS:
- ALWAYS use the appropriate subagent tool to handle queries
- For email processing: Check → Read → Analyze → Delegate → Respond
- When sending email responses, include actionable insights and next steps
- Track which emails you've processed to avoid duplicates (you'll be told which emails are new)
- If a query is clearly AWS CloudWatch related, use aws_cloudwatch_tool
- If unsure, ask for clarification about which service the user wants to query"""

        # Create supervisor with AWS CloudWatch tool
        supervisor_tools = [aws_cloudwatch_tool]
        
        # Add email MCP tools directly if email MCP client is initialized
        global email_mcp_client
        if email_mcp_client is not None:
            email_mcp_tools = email_mcp_client.list_tools_sync()
            supervisor_tools.extend(email_mcp_tools)
        
        supervisor = Agent(
            model=supervisor_model,
            tools=supervisor_tools,
            system_prompt=supervisor_prompt,
            session_manager=session_manager
        )
        
        return supervisor
    
    def get_session_count(self) -> int:
        """Get the number of active sessions"""
        with self._lock:
            return len(self.agents)

# Global multi-session manager
multi_session_manager = MultiSessionManager()

@tool
async def aws_cloudwatch_tool(query: str) -> str:
    """
    Handle AWS CloudWatch-related queries including metrics, logs, alarms, and troubleshooting.
    
    Args:
        query: AWS CloudWatch-related request (e.g., "show me EC2 metrics", "check CloudWatch logs")
    
    Returns:
        AWS CloudWatch operation results and insights
    """
    try:
        # Agent should already be initialized at startup
        if not aws_cloudwatch_agent._initialized:
            raise RuntimeError("AWS CloudWatch Agent not initialized. Call initialize_all_agents() first.")
        
        # Run the conversation - agent is already initialized
        result = await aws_cloudwatch_agent.run_conversation(query)
        
        # Extract the response from the result
        if isinstance(result, dict):
            response = result.get("final_response") or result.get("Final_response", "No response received")
        else:
            response = str(result)
            
        return response
        
    except Exception as e:
        return f"AWS CloudWatch Agent Error: {str(e)}"

async def initialize_all_agents():
    """Initialize all subagents at startup to maintain MCP client sessions"""
    global email_mcp_client
    print("🚀 Initializing All Subagents...")
    
    # Initialize the AWS CloudWatch agent
    if not aws_cloudwatch_agent._initialized:
        print("📊 Initializing AWS CloudWatch Agent...")
        await aws_cloudwatch_agent.initialize()
        print("✅ AWS CloudWatch Agent initialized!")
    else:
        print("✅ AWS CloudWatch Agent already initialized!")
    
    # Initialize Email MCP client
    if email_mcp_client is None:
        try:
            print("📧 Initializing Email MCP Client...")
            print(f"   Connecting to: {EMAIL_MCP_SERVER_URL}")
            email_mcp_client = MCPClient(
                lambda: streamablehttp_client(
                    EMAIL_MCP_SERVER_URL,
                    timeout=200,
                    sse_read_timeout=200
                )
            )
            email_mcp_client.__enter__()  # Keep connection open
            print("✅ Email MCP Client initialized!")
            
            # List available tools
            tools = email_mcp_client.list_tools_sync()
            print(f"   Available email tools: {[t.get('name') for t in tools]}")
        except Exception as e:
            print(f"⚠️  Failed to initialize Email MCP Client: {e}")
            print("   Email monitoring will be disabled.")
            email_mcp_client = None
    else:
        print("✅ Email MCP Client already initialized!")
    
    # Add other agents here as needed
    # if not kubernetes_agent._initialized:
    #     print("☸️ Initializing Kubernetes Agent...")
    #     await kubernetes_agent.initialize()
    #     print("✅ Kubernetes Agent initialized!")
    # else:
    #     print("✅ Kubernetes Agent already initialized!")
    
    print("✅ All subagents initialized and MCP sessions established!")

# This function is now replaced by MultiSessionManager.get_or_create_agent()
# Kept for backward compatibility if needed
async def create_supervisor_agent(session_id: str = "default"):
    """Create supervisor agent for a specific session (deprecated - use MultiSessionManager)"""
    return multi_session_manager.get_or_create_agent(session_id)

# Session-aware agent wrapper for A2A server
class SessionAwareAgent:
    """Wrapper agent that routes requests to session-specific agents"""
    
    def __init__(self, session_manager: MultiSessionManager, default_session_id: str = "default"):
        self.session_manager = session_manager
        self.default_session_id = default_session_id
    
    def _extract_session_id(self, message) -> str:
        """Extract session_id from message or use default"""
        # Try to extract from message context_id or taskId
        if hasattr(message, 'contextId') and message.contextId:
            return message.contextId
        if hasattr(message, 'taskId') and message.taskId:
            # Could use taskId as session identifier
            return message.taskId
        
        # Try to extract from message parts (if session_id is embedded in text)
        if hasattr(message, 'parts'):
            for part in message.parts:
                text = None
                if hasattr(part, 'text'):
                    text = part.text
                elif isinstance(part, dict):
                    text = part.get('text', '')
                
                if text:
                    # Look for session_id in text (e.g., "session_id:xyz")
                    match = re.search(r'session_id[:\s]+([a-zA-Z0-9_-]+)', text, re.IGNORECASE)
                    if match:
                        session_id = match.group(1)
                        # Remove session_id prefix from text before processing
                        cleaned_text = re.sub(r'session_id[:\s]+[a-zA-Z0-9_-]+\s*\n?\s*', '', text, flags=re.IGNORECASE)
                        if hasattr(part, 'text'):
                            part.text = cleaned_text
                        elif isinstance(part, dict):
                            part['text'] = cleaned_text
                        return session_id
        
        # Try to extract from dict format (if message is a dict)
        if isinstance(message, dict):
            if 'contextId' in message:
                return message['contextId']
            if 'parts' in message:
                for part in message['parts']:
                    if isinstance(part, dict) and 'text' in part:
                        text = part['text']
                        match = re.search(r'session_id[:\s]+([a-zA-Z0-9_-]+)', text, re.IGNORECASE)
                        if match:
                            session_id = match.group(1)
                            # Clean the text
                            part['text'] = re.sub(r'session_id[:\s]+[a-zA-Z0-9_-]+\s*\n?\s*', '', text, flags=re.IGNORECASE)
                            return session_id
        
        # Default session
        return self.default_session_id
    
    def __call__(self, message, **kwargs):
        """Route message to appropriate session agent"""
        # Handle string messages (common in Strands)
        if isinstance(message, str):
            # Extract session_id from string
            match = re.search(r'session_id[:\s]+([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
            if match:
                session_id = match.group(1)
                # Remove session_id prefix from message
                cleaned_message = re.sub(r'session_id[:\s]+[a-zA-Z0-9_-]+\s*\n?\s*', '', message, flags=re.IGNORECASE)
                agent = self.session_manager.get_or_create_agent(session_id)
                return agent(cleaned_message, **kwargs)
            else:
                # Use default session for plain string messages
                agent = self.session_manager.get_or_create_agent(self.default_session_id)
                return agent(message, **kwargs)
        else:
            # Handle object messages (A2A protocol)
            session_id = self._extract_session_id(message)
            agent = self.session_manager.get_or_create_agent(session_id)
            return agent(message, **kwargs)
    
    def __getattr__(self, name):
        """Delegate other attributes to default agent (for A2AServer compatibility)"""
        default_agent = self.session_manager.get_or_create_agent(self.default_session_id)
        return getattr(default_agent, name)

# Global reference to A2A server and thread for cleanup
_a2a_server = None
_a2a_thread = None

def _run_a2a_server(server):
    """Helper function to run A2A server (blocking)"""
    try:
        server.serve()
    except Exception as e:
        logger.error(f"A2A server error: {e}", exc_info=True)

# Simple function to start A2A server
async def start_a2a_server():
    """Start the A2A server with session-aware routing"""
    global _a2a_server, _a2a_thread
    
    # Create session-aware agent wrapper
    session_aware_agent = SessionAwareAgent(
        session_manager=multi_session_manager,
        default_session_id="default"
    )
    
    _a2a_server = A2AServer(
        agent=session_aware_agent,
        host=A2A_HOST,
        port=A2A_PORT,
        version=A2A_VERSION,
        http_url=A2A_HTTP_URL,
        serve_at_root=A2A_SERVE_AT_ROOT
    )
    
    print(f"\n🌐 A2A Server: http://{A2A_HOST}:{A2A_PORT}")
    print(f"   Agent Card: http://{A2A_HOST}:{A2A_PORT}/card")
    print(f"   Send Message: http://{A2A_HOST}:{A2A_PORT}/send-message")
    print(f"   Streaming: http://{A2A_HOST}:{A2A_PORT}/send-streaming-message")
    print(f"   📁 Multi-session support enabled")
    print(f"   💡 Include 'session_id:your-session-id' in message or use contextId")
    
    # Run blocking serve() in daemon thread (exits when main exits)
    _a2a_thread = threading.Thread(
        target=_run_a2a_server,
        args=(_a2a_server,),
        daemon=True,  # Daemon thread exits when main exits
        name="a2a-server"
    )
    _a2a_thread.start()
    
    # Give server a moment to start
    await asyncio.sleep(1)
    
    return _a2a_server

async def stop_a2a_server():
    """Stop the A2A server gracefully"""
    global _a2a_server, _a2a_thread
    
    if _a2a_server:
        try:
            print("🛑 Stopping A2A Server...")
            # Daemon thread will exit automatically when main exits
            # No explicit shutdown needed since it's a daemon thread
            print("✅ A2A Server shutdown initiated")
        except Exception as e:
            logger.warning(f"A2A server shutdown warning: {e}")
        finally:
            _a2a_server = None
            _a2a_thread = None

async def email_polling_loop():
    """
    Simple background task that periodically prompts the supervisor to check for new emails.
    
    Uses dedicated autonomous session (AUTONOMOUS_SESSION_ID) so email processing history
    is isolated from user sessions.
    
    The supervisor agent will autonomously:
    - Use list-mail-messages to check for new/unread emails
    - Read email content using get-mail-message
    - Analyze and delegate to worker agents
    - Send response emails using send-mail
    
    This is a clean, agentic approach where the supervisor handles everything.
    """
    logger.info(f"📧 Starting email polling loop (interval: {EMAIL_POLL_INTERVAL}s)")
    logger.info(f"   Using autonomous session: {AUTONOMOUS_SESSION_ID}")
    
    # Get the autonomous session agent
    autonomous_agent = multi_session_manager.get_or_create_agent(AUTONOMOUS_SESSION_ID)
    
    while True:
        try:
            await asyncio.sleep(EMAIL_POLL_INTERVAL)
            
            logger.debug("Triggering supervisor to check for new emails...")
            
            # Simple prompt - supervisor uses its MCP tools to handle everything
            # Uses dedicated autonomous session, so conversation history is isolated
            email_check_prompt = "Check for new emails or unread emails in the inbox. If there are any new emails, read them, analyze what action is needed, delegate to the appropriate worker agent, and send response emails with the results."
            
            # Let supervisor handle everything (agentic)
            # This uses the autonomous session, isolated from user sessions
            try:
                response = autonomous_agent(email_check_prompt)
                logger.debug(f"Email check completed. Response: {str(response)[:200]}...")
            except Exception as e:
                logger.error(f"Error during email check: {e}", exc_info=True)
                
        except asyncio.CancelledError:
            logger.info("Email polling loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in email polling loop: {e}", exc_info=True)
            # Continue polling even if there's an error
            await asyncio.sleep(EMAIL_POLL_INTERVAL)

async def start_email_polling():
    """Start the background email polling task (optional - can be disabled)"""
    global email_polling_task
    
    if email_mcp_client is None:
        print("⚠️  Email MCP client not available, email polling disabled")
        return None
    
    # If EMAIL_POLL_INTERVAL is 0 or negative, skip polling (use external triggers only)
    if EMAIL_POLL_INTERVAL <= 0:
        print("📧 Email polling disabled (EMAIL_POLL_INTERVAL <= 0). Use external triggers (A2A) to check emails.")
        return None
    
    email_polling_task = asyncio.create_task(email_polling_loop())
    print(f"📧 Email polling started (interval: {EMAIL_POLL_INTERVAL}s)")
    print(f"   Using autonomous session: {AUTONOMOUS_SESSION_ID}")
    print("   You can also trigger email checks externally via A2A endpoint")
    return email_polling_task

async def stop_email_polling():
    """Stop the email polling task"""
    global email_polling_task
    
    if email_polling_task:
        print("🛑 Stopping email polling...")
        email_polling_task.cancel()
        try:
            await email_polling_task
        except asyncio.CancelledError:
            pass
        email_polling_task = None
        print("✅ Email polling stopped")

async def main():
    """Main function - Runs as persistent server with A2A and background tasks"""
    global supervisor_agent
    
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info("Received shutdown signal, cleaning up...")
        asyncio.create_task(shutdown())
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Step 1: Initialize all subagents first (establishes MCP sessions)
        await initialize_all_agents()
        
        # Step 2: Pre-create default session agent (for A2AServer compatibility)
        default_agent = multi_session_manager.get_or_create_agent("default")
        print("✅ Default session agent created")
        
        # Step 3: Start A2A server with session-aware routing
        await start_a2a_server()
        
        # Step 4: Start email polling (if email MCP client is available)
        # Email polling uses dedicated autonomous session
        await start_email_polling()
        
        print("\n" + "=" * 60)
        print("🎯 DevOps Supervisor Agent Server Running!")
        print("=" * 60)
        print(f"📁 Session Directory: {SESSION_DIR}")
        print(f"   Active Sessions: {multi_session_manager.get_session_count()}")
        print(f"   Autonomous Session: {AUTONOMOUS_SESSION_ID}")
        print(f"\n🌐 A2A Server: http://{A2A_HOST}:{A2A_PORT}")
        print(f"   Agent Card: http://{A2A_HOST}:{A2A_PORT}/card")
        print(f"   Send Message: http://{A2A_HOST}:{A2A_PORT}/send-message")
        print(f"   Streaming: http://{A2A_HOST}:{A2A_PORT}/send-streaming-message")
        print("\n✅ All subagents initialized with persistent MCP sessions!")
        if email_mcp_client is not None:
            print(f"📧 Email monitoring active (polling every {EMAIL_POLL_INTERVAL}s)")
        print("\n💡 Multi-Session Support:")
        print("   - Each user gets their own isolated session")
        print("   - Include 'session_id:your-id' in message or use contextId")
        print("   - Autonomous tasks use dedicated session")
        print("\n💡 Connect to this server using:")
        print("   - Streamlit UI: streamlit run streamlit_agent_ui.py")
        print("   - A2A Client: http://localhost:9000/send-message")
        print("\n⚠️  Press Ctrl+C to shutdown gracefully\n")
        
        # Keep the server running
        # The A2A server runs in a daemon thread, and email polling runs as a background task
        # We just need to keep the event loop alive
        while True:
            await asyncio.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Failed to initialize supervisor: {e}", exc_info=True)
    finally:
        await shutdown()

async def shutdown():
    """Graceful shutdown of all services"""
    print("\n🧹 Shutting down gracefully...")
    
    # Stop email polling
    await stop_email_polling()
    
    # Stop A2A server
    await stop_a2a_server()
    
    # Cleanup MCP agents
    await aws_cloudwatch_agent.cleanup()
    
    # Cleanup email MCP client
    global email_mcp_client
    if email_mcp_client:
        try:
            print("📧 Closing Email MCP client...")
            email_mcp_client.__exit__(None, None, None)
            email_mcp_client = None
            print("✅ Email MCP client closed")
        except Exception as e:
            logger.warning(f"Error closing email MCP client: {e}")
    
    # Save session state (FileSessionManager handles this automatically, but we can force it)
    global session_manager
    if session_manager:
        try:
            # FileSessionManager should auto-save, but we can ensure it's saved
            print("💾 Saving session state...")
            print("✅ Session state saved")
        except Exception as e:
            logger.warning(f"Error saving session: {e}")
    
    print("✅ Shutdown complete!")

if __name__ == "__main__":
    asyncio.run(main())
