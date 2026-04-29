import logging
# This line is the "Volume Knob" — it must be set to INFO to see MAE/Accuracy
logging.basicConfig(level=logging.INFO, format='%(message)s')

from ml.price_model import PricePredictor

print("SkyMind Manual Training Start...")
model = PricePredictor()
model.train()
print("Training sequence complete.")