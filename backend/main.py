"""
SkyMind Flight AI Platform — FastAPI Backend
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import logging

from routers import flights, booking, payment, user, alerts, prediction
from services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("🚀 SkyMind API starting up...")
    start_scheduler()
    yield
    logger.info("🛑 SkyMind API shutting down...")
    stop_scheduler()


app = FastAPI(
    title="SkyMind Flight AI API",
    description="AI-powered flight search, prediction, and booking platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://*.vercel.app",
        # Add your production domain here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(flights.router, prefix="/flights", tags=["Flights"])
app.include_router(prediction.router, prefix="/prediction", tags=["AI Prediction"])
app.include_router(booking.router, prefix="/booking", tags=["Booking"])
app.include_router(payment.router, prefix="/payment", tags=["Payment"])
app.include_router(user.router, prefix="/user", tags=["User"])
app.include_router(alerts.router, prefix="/alerts", tags=["Price Alerts"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "service": "SkyMind Flight AI API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


# Add auth router (append to existing imports block manually if needed)
from routers.auth import router as auth_router
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# Notifications router
from routers.notifications import router as notifications_router
app.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
