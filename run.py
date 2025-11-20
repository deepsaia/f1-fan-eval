"""
F1 Fan Evaluation - Neuro-san Server Runner

This script starts the Neuro-san AI agent server backend for F1 fan evaluation.
Optionally, it can also start the nsflow web UI if installed.

Usage:
    # Start server only (recommended for production)
    python run.py

    # Start server + nsflow UI (if nsflow is installed)
    python run.py --with-ui

    # Start server on custom ports
    python run.py --http-port 8080

Configuration:
    Copy .env.example to .env and customize the settings.
    In production, use environment variables instead of .env files.
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict

from dotenv import load_dotenv


class NeuroSanRunner:
    """Simplified runner for Neuro-san AI agent server backend."""

    def __init__(self):
        """Initialize configuration and parse CLI arguments."""
        self.is_windows = os.name == "nt"
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.logs_dir = os.path.join(self.root_dir, "logs")

        print(f"F1 Fan Evaluation - Neuro-san Server")
        print(f"Root directory: {self.root_dir}\n")

        # Load environment variables (.env in dev, OS env in production)
        self._load_env_variables()

        # Default Configuration
        self.args: Dict[str, Any] = {
            "server_host": os.getenv("NEURO_SAN_SERVER_HOST", "localhost"),
            "server_http_port": int(os.getenv("NEURO_SAN_SERVER_HTTP_PORT", "8080")),
            "server_connection": os.getenv("NEURO_SAN_SERVER_CONNECTION", "http"),
            "manifest_update_period_seconds": int(os.getenv("AGENT_MANIFEST_UPDATE_PERIOD_SECONDS", "5")),
            "nsflow_port": int(os.getenv("NSFLOW_PORT", "4173")),
            "agent_manifest_file": os.getenv(
                "AGENT_MANIFEST_FILE",
                os.path.join(self.root_dir, "registries", "manifest.hocon")
            ),
            "agent_tool_path": os.getenv(
                "AGENT_TOOL_PATH",
                os.path.join(self.root_dir, "coded_tools")
            ),
        }

        # Ensure logs directory exists
        os.makedirs(self.logs_dir, exist_ok=True)

        # Parse command-line arguments
        self.args.update(self._parse_args())

        # Process references
        self.server_process = None
        self.nsflow_process = None

        # Check if nsflow is available
        self.nsflow_available = self._check_nsflow_available()

    def _load_env_variables(self):
        """Load environment variables from .env file (dev) or OS environment (prod)."""
        env_path = os.path.join(self.root_dir, ".env")

        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
            print(f"✓ Loaded environment variables from: {env_path}")
        else:
            print(f"ℹ No .env file found. Using environment variables.")
            print(f"  Copy .env.example to .env for local development.\n")

    def _check_nsflow_available(self) -> bool:
        """Check if nsflow is installed."""
        try:
            import nsflow  # noqa: F401
            return True
        except ImportError:
            return False

    def _parse_args(self):
        """Parse command-line arguments for configuration."""
        parser = argparse.ArgumentParser(
            description="Run the Neuro-san AI agent server for F1 fan evaluation.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument(
            "--http-port",
            type=int,
            default=self.args["server_http_port"],
            help="HTTP port for Neuro-san server",
        )
        parser.add_argument(
            "--with-ui",
            action="store_true",
            help="Start nsflow web UI (requires nsflow to be installed)",
        )
        parser.add_argument(
            "--ui-port",
            type=int,
            default=self.args["nsflow_port"],
            help="Port for nsflow web UI",
        )

        args = parser.parse_args()

        # Update args dict with parsed values
        return {
            "server_http_port": args.http_port,
            "with_ui": args.with_ui,
            "nsflow_port": args.ui_port,
        }

    def _set_environment_variables(self):
        """Set required environment variables for Neuro-san server."""
        print("=" * 60)
        print("Setting environment variables...\n")

        # Core Neuro-san configuration
        os.environ["PYTHONPATH"] = self.root_dir
        os.environ["AGENT_MANIFEST_FILE"] = self.args["agent_manifest_file"]
        os.environ["AGENT_TOOL_PATH"] = self.args["agent_tool_path"]
        os.environ["NEURO_SAN_SERVER_CONNECTION"] = self.args["server_connection"]
        os.environ["AGENT_MANIFEST_UPDATE_PERIOD_SECONDS"] = str(
            self.args["manifest_update_period_seconds"]
        )

        # Server connection info
        os.environ["NEURO_SAN_SERVER_HOST"] = self.args["server_host"]
        os.environ["NEURO_SAN_SERVER_HTTP_PORT"] = str(self.args["server_http_port"])

        print(f"  PYTHONPATH: {os.environ['PYTHONPATH']}")
        print(f"  AGENT_MANIFEST_FILE: {os.environ['AGENT_MANIFEST_FILE']}")
        print(f"  AGENT_TOOL_PATH: {os.environ['AGENT_TOOL_PATH']}")
        print(f"  SERVER_HOST: {os.environ['NEURO_SAN_SERVER_HOST']}")
        print(f"  SERVER_HTTP_PORT: {os.environ['NEURO_SAN_SERVER_HTTP_PORT']}")

        # nsflow-specific env variables (only if UI is enabled)
        if self.args.get("with_ui") and self.nsflow_available:
            os.environ["NSFLOW_PORT"] = str(self.args["nsflow_port"])
            os.environ["VITE_API_PROTOCOL"] = os.getenv("VITE_API_PROTOCOL", "http")
            os.environ["VITE_WS_PROTOCOL"] = os.getenv("VITE_WS_PROTOCOL", "ws")
            print(f"  NSFLOW_PORT: {os.environ['NSFLOW_PORT']}")

        print("\n" + "=" * 60 + "\n")

    @staticmethod
    def _stream_output(pipe, log_file, prefix):
        """Stream subprocess output to console and log file in real-time."""
        with open(log_file, "a", encoding="utf-8") as log:
            for line in iter(pipe.readline, ""):
                formatted_line = f"{prefix}: {line.strip()}"
                print(formatted_line)
                log.write(formatted_line + "\n")
        pipe.close()

    def _start_process(self, command, process_name, log_file):
        """Start a subprocess and capture logs."""
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if self.is_windows else 0

        # Initialize log file
        with open(log_file, "w", encoding="utf-8") as log:
            log.write(f"Starting {process_name}...\n")

        # pylint: disable=consider-using-with
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            start_new_session=not self.is_windows,
            creationflags=creation_flags,
        )

        print(f"✓ Started {process_name} with PID {process.pid}")

        # Stream logs in separate threads
        stdout_thread = threading.Thread(
            target=self._stream_output,
            args=(process.stdout, log_file, process_name)
        )
        stderr_thread = threading.Thread(
            target=self._stream_output,
            args=(process.stderr, log_file, process_name)
        )
        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        return process

    def _start_neuro_san_server(self):
        """Start the Neuro-san AI agent server."""
        print("\n🚀 Starting Neuro-san AI Agent Server...")

        command = [
            sys.executable,
            "-u",
            "-m",
            "neuro_san.service.main_loop.server_main_loop",
            "--http_port",
            str(self.args["server_http_port"]),
        ]

        log_file = os.path.join(self.logs_dir, "server.log")
        self.server_process = self._start_process(command, "NeuroSan", log_file)

        print(f"   HTTP endpoint: {self.args['server_host']}:{self.args['server_http_port']}")
        print(f"   Logs: {log_file}\n")

    def _start_nsflow_ui(self):
        """Start nsflow web UI (optional)."""
        if not self.nsflow_available:
            print("\n⚠ nsflow not installed. Skipping UI.")
            print("   Install with: uv pip install -e '.[ui]'\n")
            return

        print("\n🌐 Starting nsflow Web UI...")

        command = [
            sys.executable,
            "-u",
            "-m",
            "uvicorn",
            "nsflow.backend.main:app",
            "--port",
            str(self.args["nsflow_port"]),
            "--reload",
        ]

        log_file = os.path.join(self.logs_dir, "nsflow.log")
        self.nsflow_process = self._start_process(command, "nsflow", log_file)

        print(f"   UI available at: http://localhost:{self.args['nsflow_port']}")
        print(f"   Logs: {log_file}\n")

    # pylint: disable=unused-argument
    def _signal_handler(self, signum, frame):
        """Handle termination signals to cleanly exit."""
        print("\n\n🛑 Shutdown signal received. Stopping processes...")

        if self.server_process:
            print(f"  Stopping Neuro-san server (PID {self.server_process.pid})...")
            if self.is_windows:
                self.server_process.terminate()
            else:
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGKILL)

        if self.nsflow_process:
            print(f"  Stopping nsflow UI (PID {self.nsflow_process.pid})...")
            if self.is_windows:
                self.nsflow_process.terminate()
            else:
                os.killpg(os.getpgid(self.nsflow_process.pid), signal.SIGKILL)

        print("\n✓ All processes stopped. Goodbye!\n")
        sys.exit(0)

    @staticmethod
    def _is_port_in_use(host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a port is already in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect((host, port))
                return True
            except (ConnectionRefusedError, TimeoutError, OSError):
                return False

    def _check_port_availability(self):
        """Check if required ports are available, exit if conflicts exist."""
        conflicts = []

        # Check server ports
        if self._is_port_in_use(self.args["server_host"], self.args["server_http_port"]):
            conflicts.append(
                f"HTTP port {self.args['server_http_port']} is already in use"
            )

        # Check nsflow port if UI is requested
        if self.args.get("with_ui") and self.nsflow_available:
            if self._is_port_in_use("localhost", self.args["nsflow_port"]):
                conflicts.append(
                    f"nsflow UI port {self.args['nsflow_port']} is already in use"
                )

        if conflicts:
            print("\n❌ Port conflicts detected:\n")
            for conflict in conflicts:
                print(f"  • {conflict}")
            print("\nPlease stop the conflicting services or use different ports.\n")
            sys.exit(1)

    def run(self):
        """Main entry point - start the Neuro-san server and optionally the UI."""
        # Set environment variables
        self._set_environment_variables()

        # Check port availability
        self._check_port_availability()

        # Set up signal handling for clean shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        if not self.is_windows:
            signal.signal(signal.SIGTERM, self._signal_handler)

        # Start Neuro-san server (always)
        self._start_neuro_san_server()

        # Wait a moment for server to initialize
        time.sleep(2)

        # Start nsflow UI (optional)
        if self.args.get("with_ui"):
            self._start_nsflow_ui()

        # Show status
        print("=" * 60)
        print("✓ F1 Fan Evaluation System - Backend Running")
        print("=" * 60)
        print("\n  Press Ctrl+C to stop all processes\n")
        print("=" * 60 + "\n")

        # Wait for processes to complete
        try:
            if self.server_process:
                self.server_process.wait()
        except KeyboardInterrupt:
            self._signal_handler(None, None)


if __name__ == "__main__":
    runner = NeuroSanRunner()
    runner.run()
