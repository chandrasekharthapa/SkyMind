import sys
import os

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.notifications import dispatcher
from services.pdf import generate_ticket_pdf

def test_pdf():
    print("Testing PDF Generation...")
    data = {
        "name": "Chandra Sekhar",
        "booking_ref": "SKY2W3Y3C",
        "origin": "DEL",
        "destination": "BOM",
        "departure_date": "2026-05-03 08:04:00",
        "amount": "INR 13,049.00",
        "cabin": "ECONOMY"
    }
    pdf_bytes = generate_ticket_pdf(data)
    with open("test_ticket.pdf", "wb") as f:
        f.write(pdf_bytes)
    print("PDF saved to test_ticket.pdf")

def test_email_html():
    print("Testing Email HTML Generation...")
    data = {
        "name": "Chandra Sekhar",
        "booking_ref": "SKY2W3Y3C",
        "origin": "DEL",
        "destination": "BOM",
        "departure_date": "2026-05-03 08:04:00",
        "amount": "INR 13,049.00",
    }
    # Mocking _wrap call or just looking at the output of a template
    body = f"""
<p>Hi <strong>{data.get('name')}</strong>,</p>
<p>Your journey is confirmed.</p>
<div style="background:#0b0c0d;border:1px solid #2c2e33;border-radius:18px;padding:28px;text-align:center;margin:28px 0">
  <div style="color:#495057;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:2px;margin-bottom:8px">Booking Reference</div>
  <div style="font-size:44px;font-weight:900;color:#ff6b6b;letter-spacing:6px;font-family:'Courier New',monospace;margin:8px 0">{data.get('booking_ref')}</div>
</div>
"""
    html = dispatcher.email._wrap("linear-gradient(135deg,#e03131,#ff6b6b)", "", "Ticket Secured", "Confirmed", body)
    with open("test_email.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Email HTML saved to test_email.html")

if __name__ == "__main__":
    test_pdf()
    test_email_html()
