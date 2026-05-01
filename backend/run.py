import logging
# This line is the "Volume Knob" — it must be set to INFO to see MAE/Accuracy
logging.basicConfig(level=logging.INFO, format='%(message)s')

from ml.price_model import PricePredictor

print("SkyMind Manual Training Start...")
model = PricePredictor()
model.train()

print("Uploading model to Supabase Storage...")
from database.database import database as db
from ml.price_model import MODEL_PATH
if db.upload_model(MODEL_PATH):
    print("Model successfully stored in cloud.")
else:
    print("Cloud storage failed.")

print("Training sequence complete.")