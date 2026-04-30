"""
SkyMind — Unified Daily Pipeline
Handles: Ingestion, Alerts, Retraining, and Persistence.
Designed for GitHub Actions.
"""

import os
import logging
import sys
from datetime import datetime, timezone

# Ensure backend is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SkyMindPipeline")

def run_ingestion():
    logger.info(">>> TASK 1: Starting Synthetic Data Ingestion...")
    try:
        from services.scheduler import _ingest_synthetic_batch, ROUTE_BATCHES
        for i in range(len(ROUTE_BATCHES)):
            _ingest_synthetic_batch(i)
        logger.info("Ingestion complete.")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")

def run_alerts():
    logger.info(">>> TASK 2: Checking Price Alerts...")
    try:
        from services.scheduler import _check_price_alerts
        _check_price_alerts()
        logger.info("Alert check complete.")
    except Exception as e:
        logger.error(f"Alert check failed: {e}")

def run_retraining():
    logger.info(">>> TASK 3: Retraining XGBoost Model...")
    try:
        from ml.price_model import get_predictor, MODEL_PATH
        from database.database import database as db
        
        predictor = get_predictor()
        predictor.train()
        
        logger.info(">>> TASK 4: Uploading Model to Supabase Storage...")
        if os.path.exists(MODEL_PATH):
            success = db.upload_model(MODEL_PATH)
            if success:
                logger.info("Model persistence successful.")
            else:
                logger.error("Model persistence failed.")
                sys.exit(1)
        else:
            logger.error("Model file not found after training.")
            
    except Exception as e:
        logger.error(f"Retraining failed: {e}")

if __name__ == "__main__":
    logger.info("=== SkyMind Pipeline Initialized ===")
    start_time = datetime.now()
    
    # Run the sequence
    run_ingestion()
    run_alerts()
    run_retraining()
    
    end_time = datetime.now()
    duration = end_time - start_time
    logger.info(f"=== SkyMind Pipeline Completed in {duration.total_seconds():.1f}s ===")
