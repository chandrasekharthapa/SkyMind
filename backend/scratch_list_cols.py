import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

try:
    res = supabase.table("bookings").select("*").limit(1).execute()
    if res.data:
        print("Columns:", res.data[0].keys())
    else:
        print("No data in bookings table.")
except Exception as e:
    print("Error:", e)
