"""
Streamlit UI for DevOps Supervisor Agent
REST Client interface connecting to the persistent backend server

This is a "dumb" view layer that communicates with the backend via A2A protocol.
The backend runs as a persistent server with FileSessionManager for state persistence.
"""

import streamlit as st
import requests
import json
from datetime import datetime
from typing import Optional
import uuid

# Backend Configuration - Default URL
DEFAULT_BACKEND_URL = "http://localhost:9000"

def get_user_session_id() -> str:
    """Get or create a unique session ID for this Streamlit user"""
    if 'user_session_id' not in st.session_state:
        st.session_state.user_session_id = str(uuid.uuid4())
    return st.session_state.user_session_id

def send_message_to_backend(message: str, backend_url: str, session_id: str = None) -> Optional[str]:
    """
    Send a message to the backend A2A server and get response
    
    Args:
        message: User message to send
        backend_url: Backend server URL
        session_id: Session ID for this user (if None, uses default)
        
    Returns:
        Response text from the agent, or None if error
    """
    try:
        # Use provided session_id or get from session state
        if session_id is None:
            session_id = get_user_session_id()
        
        # A2A protocol message format
        # Include session_id in the message text so SessionAwareAgent can extract it
        # Alternatively, we could use contextId if A2A protocol supports it
        message_with_session = f"session_id:{session_id}\n\n{message}"
        
        payload = {
            "kind": "message",
            "role": "user",
            "parts": [{"kind": "text", "text": message_with_session}],
            "message_id": str(uuid.uuid4()),
            "contextId": session_id  # Also include in contextId if supported
        }
        
        # Send POST request to /send-message endpoint
        response = requests.post(
            f"{backend_url}/send-message",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300  # 5 minute timeout for long-running queries
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # A2A protocol response can have different structures
            # Try to extract the response text from various possible formats
            
            # Format 1: Direct response with parts
            if 'result' in result:
                task = result['result']
                # If it's a task, we might need to extract the response
                if isinstance(task, dict):
                    if 'response' in task:
                        response_obj = task['response']
                        if isinstance(response_obj, dict) and 'parts' in response_obj:
                            text_parts = [part.get('text', '') for part in response_obj['parts'] if part.get('kind') == 'text']
                            return '\n'.join(text_parts) if text_parts else str(response_obj)
                        return str(response_obj)
                    # Check for text directly in task
                    if 'text' in task:
                        return task['text']
            
            # Format 2: Response with message object
            if 'response' in result:
                response_obj = result['response']
                if isinstance(response_obj, dict):
                    if 'parts' in response_obj:
                        text_parts = [part.get('text', '') for part in response_obj['parts'] if part.get('kind') == 'text']
                        return '\n'.join(text_parts) if text_parts else str(response_obj)
                    if 'text' in response_obj:
                        return response_obj['text']
                return str(response_obj)
            
            # Format 3: Direct text field
            if 'text' in result:
                return result['text']
            
            # Format 4: Message field
            if 'message' in result:
                msg = result['message']
                if isinstance(msg, dict) and 'parts' in msg:
                    text_parts = [part.get('text', '') for part in msg['parts'] if part.get('kind') == 'text']
                    return '\n'.join(text_parts) if text_parts else str(msg)
                return str(msg)
            
            # Format 5: Fallback - return formatted JSON for debugging
            return json.dumps(result, indent=2)
        else:
            return f"Error: Backend returned status {response.status_code}: {response.text}"
            
    except requests.exceptions.ConnectionError:
        return "Error: Could not connect to backend server. Make sure supervisor_with_aws_agent.py is running."
    except requests.exceptions.Timeout:
        return "Error: Request timed out. The agent may be processing a long-running task."
    except Exception as e:
        return f"Error: {str(e)}"

def get_backend_url() -> str:
    """Get the backend URL from session state or default"""
    return st.session_state.get('backend_url', DEFAULT_BACKEND_URL)

def check_backend_health(backend_url: str) -> bool:
    """Check if backend server is accessible"""
    try:
        response = requests.get(f"{backend_url}/card", timeout=5)
        return response.status_code == 200
    except:
        return False

def initialize_session_state():
    """Initialize Streamlit session state"""
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    
    if 'backend_url' not in st.session_state:
        st.session_state.backend_url = DEFAULT_BACKEND_URL
    
    # Initialize user session ID (unique per Streamlit user session)
    if 'user_session_id' not in st.session_state:
        st.session_state.user_session_id = str(uuid.uuid4())

def display_agent_info():
    """Display DevOps Supervisor Agent information"""
    st.header("🎯 DevOps Supervisor Agent")
    
    backend_url = get_backend_url()
    # Check backend health
    backend_healthy = check_backend_health(backend_url)
    
    if backend_healthy:
        st.success("✅ **Connected to backend server**")
        st.info("🤖 **Supervisor Agent** - Coordinates multiple specialized agents for infrastructure monitoring and management")
    else:
        st.error("❌ **Backend server not accessible**")
        st.warning("⚠️ Make sure `python supervisor_with_aws_agent.py` is running")
        st.info(f"Trying to connect to: `{backend_url}`")
    
    st.write("**Capabilities:**")
    st.write("• Route queries to appropriate specialized agents")
    st.write("• AWS CloudWatch monitoring and troubleshooting")
    st.write("• Multi-agent coordination")
    st.write("• Intelligent query routing")
    st.write("• Email monitoring and processing")
    
    return backend_healthy

def display_chat_interface():
    """Display chat interface for agent interaction"""
    backend_url = get_backend_url()
    backend_healthy = check_backend_health(backend_url)
    
    if not backend_healthy:
        st.warning("⚠️ Cannot connect to backend. Please start the server first.")
        st.code("python supervisor_with_aws_agent.py", language="bash")
        return
    
    st.header("💬 Chat with Agent")
    
    # Display conversation history
    if st.session_state.conversation_history:
        for message in st.session_state.conversation_history:
            with st.chat_message(message["role"]):
                st.write(message["content"])
                if "timestamp" in message:
                    st.caption(f"🕒 {message['timestamp']}")
    
    # Chat input
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        # Add user message to history
        user_message = {
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        st.session_state.conversation_history.append(user_message)
        
        # Display user message
        with st.chat_message("user"):
            st.write(user_input)
        
        # Get agent response
        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking..."):
                try:
                    session_id = get_user_session_id()
                    response = send_message_to_backend(user_input, backend_url, session_id)
                    
                    if response:
                        st.write(response)
                        
                        # Add agent response to history
                        agent_message = {
                            "role": "assistant",
                            "content": response,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.session_state.conversation_history.append(agent_message)
                    else:
                        error_msg = "No response received from backend"
                        st.error(error_msg)
                        st.session_state.conversation_history.append({
                            "role": "assistant",
                            "content": error_msg,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    st.error(error_msg)
                    
                    # Add error to history
                    error_message = {
                        "role": "assistant",
                        "content": error_msg,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.session_state.conversation_history.append(error_message)

def display_sidebar():
    """Display sidebar with additional information"""
    with st.sidebar:
        st.header("ℹ️ Connection Info")
        
        # Backend URL configuration
        st.subheader("🔗 Backend Configuration")
        backend_url = st.text_input(
            "Backend URL",
            value=st.session_state.get('backend_url', DEFAULT_BACKEND_URL),
            key="backend_url_input"
        )
        st.session_state.backend_url = backend_url
        
        # Check connection
        if st.button("🔍 Check Connection"):
            if check_backend_health(backend_url):
                st.success("✅ Connected")
            else:
                st.error("❌ Not connected")
        
        st.divider()
        
        st.subheader("📊 Chat Stats")
        st.write(f"**Messages:** {len(st.session_state.conversation_history)}")
        st.write(f"**Session ID:** `{get_user_session_id()[:16]}...`")
        st.caption("Each user has an isolated session with persistent conversation history")
        
        st.divider()
        
        # Clear conversation button
        if st.button("🗑️ Clear Conversation"):
            st.session_state.conversation_history = []
            st.rerun()
        
        # Export conversation button
        if st.session_state.conversation_history:
            if st.button("📥 Export Conversation"):
                conversation_data = {
                    "backend_url": st.session_state.backend_url,
                    "timestamp": datetime.now().isoformat(),
                    "messages": st.session_state.conversation_history
                }
                
                st.download_button(
                    label="Download JSON",
                    data=json.dumps(conversation_data, indent=2),
                    file_name=f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        
        st.divider()
        
        st.subheader("📖 Instructions")
        st.write("1. Start the backend server:")
        st.code("python supervisor_with_aws_agent.py", language="bash")
        st.write("2. The server will run on port 9000 by default")
        st.write("3. Chat with the agent using the interface below")

def main():
    """Main Streamlit application"""
    st.set_page_config(
        page_title="DevOps Supervisor Agent",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🎯 DevOps Supervisor Agent")
    st.markdown("Infrastructure monitoring and management with intelligent agent coordination")
    
    # Initialize session state
    initialize_session_state()
    
    # Display sidebar
    display_sidebar()
    
    # Main content - show agent info
    display_agent_info()
    
    st.divider()
    
    # Chat interface
    display_chat_interface()

if __name__ == "__main__":
    main()
