"""
Health Check Server

Provides a simple HTTP endpoint for monitoring the agent's health status.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Optional

from src.logger import info, error


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoints."""

    # Class-level provider functions
    _status_provider: Optional[Callable[[], dict]] = None
    _metrics_provider: Optional[Callable[[], str]] = None

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health' or self.path == '/':
            self._handle_health()
        elif self.path == '/ready':
            self._handle_ready()
        elif self.path == '/status':
            self._handle_status()
        elif self.path == '/metrics':
            self._handle_metrics()
        else:
            self._send_response(404, {"error": "Not found"})

    def _handle_health(self):
        """Basic liveness check."""
        self._send_response(200, {"status": "healthy"})

    def _handle_ready(self):
        """Readiness check - are we ready to process work?"""
        if HealthHandler._status_provider:
            status = HealthHandler._status_provider()
            if status.get("running", False):
                self._send_response(200, {"status": "ready", "running": True})
            else:
                self._send_response(503, {"status": "not_ready", "running": False})
        else:
            self._send_response(200, {"status": "ready"})

    def _handle_status(self):
        """Detailed status endpoint."""
        if HealthHandler._status_provider:
            status = HealthHandler._status_provider()
            self._send_response(200, status)
        else:
            self._send_response(200, {"status": "no_status_provider"})

    def _handle_metrics(self):
        """Prometheus-format metrics endpoint."""
        if HealthHandler._metrics_provider:
            metrics = HealthHandler._metrics_provider()
            self._send_text_response(200, metrics, "text/plain; version=0.0.4")
        else:
            self._send_text_response(200, "# No metrics provider configured\n", "text/plain")

    def _send_response(self, code: int, data: dict):
        """Send JSON response."""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_text_response(self, code: int, text: str, content_type: str = "text/plain"):
        """Send plain text response."""
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.end_headers()
        self.wfile.write(text.encode())


class HealthServer:
    """
    Simple HTTP server for health checks.

    Runs in a background thread and exposes:
    - /health  - Basic liveness check
    - /ready   - Readiness check (is agent running?)
    - /status  - Detailed status information (JSON)
    - /metrics - Prometheus-format metrics
    """

    def __init__(
        self,
        port: int = 8080,
        status_provider: Callable[[], dict] = None,
        metrics_provider: Callable[[], str] = None,
    ):
        self.port = port
        self.status_provider = status_provider
        self.metrics_provider = metrics_provider
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the health check server in a background thread."""
        # Set the providers on the handler class
        HealthHandler._status_provider = self.status_provider
        HealthHandler._metrics_provider = self.metrics_provider

        try:
            self._server = HTTPServer(('0.0.0.0', self.port), HealthHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            info(f"Health server started on port {self.port}")
        except Exception as e:
            error(f"Failed to start health server", err=e, port=self.port)

    def stop(self):
        """Stop the health check server."""
        if self._server:
            self._server.shutdown()
            info("Health server stopped")


# Global instance
_health_server: Optional[HealthServer] = None


def start_health_server(
    port: int = 8080,
    status_provider: Callable[[], dict] = None,
    metrics_provider: Callable[[], str] = None,
):
    """Start the global health server."""
    global _health_server
    if _health_server is None:
        _health_server = HealthServer(
            port=port,
            status_provider=status_provider,
            metrics_provider=metrics_provider,
        )
        _health_server.start()


def stop_health_server():
    """Stop the global health server."""
    global _health_server
    if _health_server:
        _health_server.stop()
        _health_server = None
