import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Imported when a logger is first constructed rather than at module import.
# `google.cloud.logging` costs about four seconds to import, and this module is
# reached from the route table, so that was four seconds every boot spent on a
# client that is only built when an agent finishes a run. Boot time is not free
# here: the platform gives the app a fixed window to open its port, and the
# import chain runs before uvicorn binds one.
def _cloud_logging_module():
    """The Cloud Logging module, or None where the package is absent."""
    try:
        from google.cloud import logging as cloud_logging
        return cloud_logging
    except ImportError:
        return None


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

        cloud_logging = _cloud_logging_module()
        if cloud_logging is not None:
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
