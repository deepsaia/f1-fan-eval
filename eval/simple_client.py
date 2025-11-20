"""
SimpleClient - Interface to Neuro-san AI evaluation system.

This module provides a simplified client for communicating with the Neuro-san
AI agents that score F1 fan submissions. It handles:
- Session management (creating/tracking AI conversations)
- Input processing (sending text to AI for evaluation)
- Response handling (extracting scores and token metrics)
- Logging (saving AI thinking process to files)
"""

import logging
import os
import uuid
from typing import Any, Dict

from neuro_san.client.agent_session_factory import AgentSessionFactory

# from utils.agent_log_processor import AgentLogProcessor
from neuro_san.client.streaming_input_processor import StreamingInputProcessor

# Configure logging format
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Directory where AI thinking logs will be stored
LOGS_DIR = "logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Global dictionary to track active user sessions
# Key: session_id (string), Value: dict with input_processor and state
user_sessions: Dict[str, Dict[str, Any]] = {}


class SimpleClient:
    """
    Simplified client for interacting with Neuro-san AI agents.

    This client:
    - Connects to a Neuro-san AI agent (e.g., f1_fan_knowledge, f1_fan_humor)
    - Manages conversation sessions (each evaluation gets its own session)
    - Sends text input and receives structured responses (scores + metadata)
    - Logs AI "thinking" process to files for debugging

    Typical usage:
        client = SimpleClient(agent_name="f1_fan_knowledge")
        response = client.process_user_input(session_id, user_text)
        score = response["evaluation"]["score"]
    """

    def __init__(
        self,
        agent_name: str,
        default_dir: str = "default_dir",
        local_test: bool = False,
    ):
        """
        Initialize a client for a specific Neuro-san agent.

        Args:
            agent_name: Name of the AI agent to use (e.g., "f1_fan_knowledge")
            default_dir: Directory name for storing logs (under logs/)
            local_test: If True, skip loading .env file (for testing)

        The agent_name determines which evaluation criteria this client handles:
        - "f1_fan_knowledge" → scores F1 knowledge
        - "f1_fan_enthusiasm" → scores enthusiasm
        - "f1_fan_humor" → scores humor
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        # Load environment variables (server connection info) unless in test mode
        if not local_test:
            self.load_env_variables()

        # Store configuration
        self.agent_name = agent_name
        self.connection = os.getenv("NEUROSAN_CONNECTION_TYPE", "http")  # http, https, or grpc
        self.server_host = os.getenv("NEUROSAN_SERVER_HOST", "localhost")
        self.server_port = os.getenv("NEUROSAN_SERVER_PORT", "8080")
        self.use_direct = False  # Direct vs. load-balanced connection

        # Validate configuration
        self.check_env_variables()

        # Create directory for storing AI thinking logs
        self.thinking_dir = os.path.join(LOGS_DIR, default_dir)
        if not os.path.exists(self.thinking_dir):
            os.makedirs(self.thinking_dir)

        # Establish connection to the AI agent
        self.session = self._create_agent_session()

    def load_env_variables(self):
        """
        Load environment variables from .env file.

        This reads the .env file line by line and sets environment variables
        for server connection (host, port, connection type).

        Expected .env format:
            NEUROSAN_CONNECTION_TYPE=http
            NEUROSAN_SERVER_HOST=localhost
            NEUROSAN_SERVER_PORT=8080
        """
        env_file = ".env"
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    # Skip empty lines and comments
                    if line.strip() and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        # Remove quotes if present
                        os.environ[key] = value.strip('"')
            self.logger.info(f"Loaded environment variables from {env_file}")
        else:
            self.logger.warning(
                f"No .env file found at {env_file}. Using default environment variables."
            )

    def check_env_variables(self):
        """
        Validate that environment variables are set correctly.

        Checks:
        - NEUROSAN_CONNECTION_TYPE is valid (http, https, or grpc)
        - Logs warnings if using default values
        """
        if self.connection not in ["https", "http", "grpc"]:
            raise ValueError(
                "Invalid NEUROSAN_CONNECTION_TYPE. Must be 'https', 'http' or 'grpc'."
            )
        if not os.getenv("NEUROSAN_CONNECTION_TYPE"):
            self.logger.info(
                "=========="
                "NEUROSAN_CONNECTION_TYPE environment variable is not set. Using default 'http'"
            )
        if not os.getenv("NEUROSAN_SERVER_HOST"):
            self.logger.info(
                "=========="
                "NEUROSAN_SERVER_HOST environment variable is not set. Using localhost"
            )
        if not os.getenv("NEUROSAN_SERVER_PORT"):
            self.logger.info(
                "=========="
                "NEUROSAN_SERVER_PORT environment variable is not set. Using default port 8080"
            )

    def _create_agent_session(self):
        """
        Create a connection to the Neuro-san AI agent.

        Returns:
            A session object that can send/receive messages to the AI agent

        This establishes the connection to the AI server using the configured
        connection type (http/https/grpc), host, and port.
        """
        factory: AgentSessionFactory = AgentSessionFactory()

        # Metadata to identify this client (for logging/tracking on server side)
        metadata: Dict[str, str] = {"user_id": os.environ.get("USER", "default_user")}

        # Create session with specified connection parameters
        session = factory.create_session(
            self.connection,
            self.agent_name,
            self.server_host,
            self.server_port,
            self.use_direct,
            metadata,
        )
        self.logger.info(
            f"Created agent session for {self.agent_name} at {self.server_host}:{self.server_port}"
        )
        return session

    def create_user_session(self, session_id: str) -> Dict[str, Any]:
        """
        Create a new user session for processing evaluations.

        Args:
            session_id: Unique identifier for this evaluation session

        Returns:
            Dictionary containing input_processor and state

        Each session maintains its own state (conversation history, metrics, etc.)
        and has a dedicated log file for the AI's thinking process.
        """
        # Chat filter configuration (MAXIMAL = show all output)
        chat_filter: Dict[str, Any] = {"chat_filter_type": "MAXIMAL"}

        # Initial session state
        state: Dict[str, Any] = {
            "last_chat_response": None,      # Last AI response
            "num_input": 0,                  # Number of inputs processed
            "chat_filter": chat_filter,      # Output filter settings
            "sly_data": {},                  # Custom data (scores, etc.)
        }

        # Create a unique thinking file for this agent
        thinking_file = os.path.join(
            self.thinking_dir, f"agent_thinking_{self.agent_name}.txt"
        )
        self.logger.info(f"[{session_id}] Using thinking file: {thinking_file}")

        # Create input processor (handles communication with AI agent)
        # (use AsyncStreamingInputProcessor here, if needed)
        input_processor = StreamingInputProcessor(
            default_input="",
            thinking_file=thinking_file,
            session=self.session,
            thinking_dir=self.thinking_dir,
        )

        # Attach agent log processor (uncomment to see logs on terminal)
        # agent_log_processor = AgentLogProcessor(session_id)
        # input_processor.processor.add_processor(agent_log_processor)

        # Store session in global dictionary
        user_session = {"input_processor": input_processor, "state": state}
        user_sessions[session_id] = user_session
        return user_session

    def process_user_input(
        self, session_id: str, user_input: str, sly_data: Dict[str, Any] = None
    ) -> str:
        """
        Send text to the AI agent and get back structured evaluation results.

        Args:
            session_id: Unique identifier for this evaluation session
            user_input: The text to evaluate (F1 fan description)
            sly_data: Optional additional data to pass to the agent

        Returns:
            Dictionary containing:
            - evaluation: {"score": float, "brief_description": str}
            - token_accounting: {total_tokens, prompt_tokens, completion_tokens, etc.}

        This is the main method for getting AI evaluations. It:
        1. Creates a session if needed
        2. Sends the input text to the AI
        3. Waits for response
        4. Extracts scores and metrics
        5. Returns structured data
        """
        if sly_data is None:
            sly_data = {}

        # Fetch or create session
        user_session = user_sessions.get(session_id)
        if not user_session:
            self.logger.info(f"[{session_id}] Creating new user session")
            user_session = self.create_user_session(session_id)

        input_processor = user_session["input_processor"]
        state = user_session["state"]

        # Update state with new input
        state["user_input"] = user_input
        state["sly_data"].update(sly_data)

        self.logger.info(f"[{session_id}] Processing user input")

        try:
            # Send to AI and wait for response
            state = input_processor.process_once(state)
            user_session["state"] = state

            # Extract results from state
            # last_response = state.get("last_chat_response", "")  # Full text response
            final_sly_data = state.get("sly_data", {})              # Structured data (scores)
            self.logger.info(
                f"[{session_id}] Received response from {self.agent_name}."
            )

            # Extract token accounting for cost tracking
            final_token_accounting = state.get("token_accounting", {})

            # Combine all results into a single response
            # Note: The response contains sly_data (with scores) + token_accounting
            final_response = {
                **final_sly_data,
                "token_accounting": final_token_accounting,
            }
            # self.logger.info(f"========== Final_sly_data: {final_sly_data}")
            # self.logger.info(f"========== Final response: {final_response}")
            return final_response
        except Exception as e:
            self.logger.error(
                f"[{session_id}] Error during processing: {e}", exc_info=True
            )
            return f"Error: {e}"

    def reset_session(self, session_id: str):
        """
        Clean up a session after evaluation is complete.

        Args:
            session_id: The session to delete

        This removes the session from memory, freeing up resources.
        Call this after you're done processing a submission.
        """
        if session_id in user_sessions:
            del user_sessions[session_id]


if __name__ == "__main__":
    client = SimpleClient(agent_name="f1_fan_humor")
    session_id = str(uuid.uuid4())
    user_input = """
    I approach a new planet in a ferrari and wish to send greetings to the orb.
    """
    response = client.process_user_input(session_id, user_input=user_input)
    print("Response:", response)
    client.reset_session(session_id)
