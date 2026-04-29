import os
from dotenv import load_dotenv
from supabase import create_client
import uuid
from datetime import datetime, timezone

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

booking_id = str(uuid.uuid4())
now = datetime.now(timezone.utc).isoformat()

payload = {
    "id": booking_id,
    "booking_reference": "TEST123",
    "status": "PENDING",
    "payment_status": "UNPAID",
    "flight_offer_id": "demo",
    "flight_offer_data": {"price": {"total": 100}},
    "passengers": [{"first_name": "Test", "last_name": "User"}],
    "num_passengers": 1,
    "contact_email": "test@example.com",
    "contact_phone": "1234567890",
    "cabin_class": "ECONOMY",
    "total_price": 100.0,
    "currency": "INR",
    "created_at": now,
    "updated_at": now,
}

try:
    res = supabase.table("bookings").insert(payload).execute()
    print("Success:", res.data)
except Exception as e:
    print("Error:", e)
