
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("Error: Missing Supabase credentials in .env")
    exit(1)

supabase = create_client(url, key)

print("Clearing bookings and passengers tables...")

try:
    # Delete all passengers first (foreign key constraint)
    res_p = supabase.table("passengers").delete().neq("booking_id", "00000000-0000-0000-0000-000000000000").execute()
    print(f"Cleared passengers table.")

    # Delete all bookings
    res_b = supabase.table("bookings").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print(f"Cleared bookings table.")
    
    print("Success: Database cleared.")
except Exception as e:
    print(f"Error: {e}")
