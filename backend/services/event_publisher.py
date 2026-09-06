"""SkyMind Event Publisher Abstraction.

Defines the EventPublisher ABC and its concrete implementations:
NullEventPublisher, AuditLogEventPublisher, OpenTelemetryEventPublisher,
KafkaEventPublisher, and RabbitMQEventPublisher.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
import logging
from opentelemetry import metrics

logger = logging.getLogger(__name__)

# OpenTelemetry Setup
meter = metrics.get_meter("skymind.event_publisher")
events_counter = meter.create_counter(
    name="published_events_total",
    description="Total number of domain events published",
)

class EventPublisher(ABC):
    """Abstract interface for pipeline event publishing."""
    
    @abstractmethod
    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publishes a pipeline event with payload."""
        pass


class NullEventPublisher(EventPublisher):
    """Event publisher that drops all messages (No-op/Null object pattern)."""
    
    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        pass


class AuditLogEventPublisher(EventPublisher):
    """Event publisher that writes events to standard secure audit logs."""
    
    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        logger.info(f"[AUDIT LOG] event_type={event_type} payload={payload}")


class OpenTelemetryEventPublisher(EventPublisher):
    """Event publisher that registers event counts in OpenTelemetry."""
    
    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        events_counter.add(1, {
            "event_type": event_type,
            "status": "success"
        })
        logger.debug(f"[OTEL EVENT] Recorded event={event_type}")


class KafkaEventPublisher(EventPublisher):
    """Event publisher simulating serialization and transport to Kafka cluster."""
    
    def __init__(self, bootstrap_servers: str = "localhost:9092", topic: str = "skymind.events"):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        # Simulate serialization & socket transmission
        logger.info(f"[KAFKA PUBLISH] Topic '{self.topic}' on servers '{self.bootstrap_servers}' — "
                    f"Event: {event_type} Payload: {payload}")


class RabbitMQEventPublisher(EventPublisher):
    """Event publisher simulating serialization and routing to AMQP exchange."""
    
    def __init__(self, host: str = "localhost", exchange: str = "skymind.exchange"):
        self.host = host
        self.exchange = exchange

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        # Simulate AMQP publish
        logger.info(f"[RABBITMQ PUBLISH] Exchange '{self.exchange}' on host '{self.host}' — "
                    f"RoutingKey: {event_type} Payload: {payload}")
