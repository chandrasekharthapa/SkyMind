class FirewallError(Exception):
    """Base exception for all firewall-related errors."""
    pass

class FirewallTimeoutError(FirewallError):
    """Raised when a guardrail execution exceeds the configured timeout."""
    pass

class GuardrailExecutionError(FirewallError):
    """Raised when an underlying guardrail check fails unexpectedly."""
    pass
