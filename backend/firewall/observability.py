from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Initialize OpenTelemetry Tracer
trace.set_tracer_provider(TracerProvider())

# For this implementation, we'll export to the console. 
# In a real environment, you'd use OTLPSpanExporter to send to Jaeger/Prometheus.
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(ConsoleSpanExporter())
)

tracer = trace.get_tracer("skymind.firewall")

def get_tracer():
    return tracer
