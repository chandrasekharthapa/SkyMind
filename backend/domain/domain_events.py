"""SkyMind Domain Events.

Structured event logging and publishing for pipeline monitoring and auditing.
"""

from typing import Dict, Any, List, Callable
from datetime import datetime, timezone
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class DomainEvent(BaseModel):
    """Base schema for all domain events."""
    event_type: str = Field(..., description="Unique type identifier of the event.")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO UTC timestamp.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary.")

class DomainEventDispatcher:
    def __init__(self):
        self._listeners: Dict[str, List[Callable[[DomainEvent], None]]] = {}
        self.events_log: List[DomainEvent] = []

    def subscribe(self, event_type: str, listener: Callable[[DomainEvent], None]) -> None:
        """Register a callback listener for a specific event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def dispatch(self, event: DomainEvent) -> None:
        """Publishes the domain event to registered listeners and logs it."""
        self.events_log.append(event)
        logger.info(f"[DOMAIN EVENT] Dispatched event_type={event.event_type} at {event.timestamp}. Metadata: {event.metadata}")
        
        listeners = self._listeners.get(event.event_type, [])
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error in event listener for {event.event_type}: {e}")

# Global singleton event dispatcher
event_dispatcher = DomainEventDispatcher()
