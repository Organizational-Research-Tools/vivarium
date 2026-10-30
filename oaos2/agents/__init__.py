"""Run model agents and dispatch their permitted tools from the host.

The platform assembles each request, receives the response, and decides which
action to execute next. Providers handle individual model calls. File tools
run through host-side access checks; Python execution uses the agent container."""

from oaos2.agents.model_agent import make_model_agent_behavior
from oaos2.agents.tools import PAPER_TOOLSPECS, ToolContext, dispatch_tool

__all__ = ["PAPER_TOOLSPECS", "ToolContext", "dispatch_tool", "make_model_agent_behavior"]
