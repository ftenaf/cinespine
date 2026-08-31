import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from google.cloud import logging as cloud_logging
    CLOUD_LOGGING_AVAILABLE = True
except ImportError:
    CLOUD_LOGGING_AVAILABLE = False


class AgentCloudLogger:
    """
    Ships agent execution traces as structured logs to Google Cloud Logging.
    Falls back to standard python logging if google-cloud-logging is unavailable
    or credentials are not configured.
    """

    def __init__(self, log_name: str = "cinespine-agent-runs"):
        self.log_name = log_name
        self.client = None
        self.cloud_logger = None

        if CLOUD_LOGGING_AVAILABLE:
            try:
                # This will automatically pick up Application Default Credentials or GOOGLE_APPLICATION_CREDENTIALS
                self.client = cloud_logging.Client()
                self.cloud_logger = self.client.logger(self.log_name)
            except Exception as exc:
                logger.debug("Could not initialize Google Cloud Logging client: %s", exc)

    def log_agent_run(self, agent_name: str, action: str, payload: Dict[str, Any]) -> None:
        """
        Log an agent execution event to Google Cloud Logging.
        
        Args:
            agent_name: Name of the agent (e.g. 'WrapRescueAgent')
            action: The action being performed (e.g. 'agent_run_completed')
            payload: Structured dictionary of execution traces, steps, and tool calls.
        """
        # Ensure payload is json serializable
        try:
            structured_payload = json.loads(json.dumps(payload, default=str))
        except TypeError as e:
            structured_payload = {"error": "unserializable payload", "details": str(e)}

        structured_payload["agent"] = agent_name
        structured_payload["action"] = action
        structured_payload["source"] = "cinespine"

        if self.cloud_logger is not None:
            try:
                self.cloud_logger.log_struct(structured_payload, severity="INFO")
                return
            except Exception as exc:
                logger.warning("Failed to ship log to Google Cloud Logging: %s", exc)
        
        # Fallback to local python logger
        logger.info(
            "AgentCloudLogger Fallback [%s - %s]: %s",
            agent_name,
            action,
            json.dumps(structured_payload, default=str)
        )
