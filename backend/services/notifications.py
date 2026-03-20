"""
╔══════════════════════════════════════════════════════════════╗
║  SkyMind — Complete Notification Service                     ║
║  Channels: Gmail SMTP · Fast2SMS · Twilio · WhatsApp         ║
║  Types:    Booking · OTP · Price Alert · Reminder · Welcome  ║
╚══════════════════════════════════════════════════════════════╝
"""

import smtplib
import logging
import os
import random
import string
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ================================================================
# 1. EMAIL SERVICE — Gmail SMTP (free, unlimited)
# ================================================================

class EmailService:
    def __init__(self):
        self.gmail_user     = os.getenv("GMAIL_USER", "")
        self.gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
        self.from_name      = os.getenv("EMAIL_FROM_NAME", "SkyMind Flights")
        self.smtp_host      = "smtp.gmail.com"
        self.smtp_port      = 587
        self.reply_to       = os.getenv("EMAIL_REPLY_TO", "")

    def _connect(self):
        server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
        server.ehlo()
        server.starttls()
        server.login(self.gmail_user, self.gmail_password)
        return server

    def send(self, to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
        if not self.gmail_user or not self.gmail_password:
            logger.warning("Gmail credentials missing — email not sent to %s", to_email)
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"{self.from_name} <{self.gmail_user}>"
            msg["To"]      = to_email
            if self.reply_to:
                msg["Reply-To"] = self.reply_to
            if text_body:
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            with self._connect() as server:
                server.sendmail(self.gmail_user, [to_email], msg.as_string())
            logger.info("Email sent -> %s | %s", to_email, subject)
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("Gmail auth failed. Check GMAIL_APP_PASSWORD.")
            return False
        except Exception as e:
            logger.error("Email error -> %s : %s", to_email, e)
            return False

    @staticmethod
    def _wrap(header_color: str, emoji: str, title: str, subtitle: str, body: str) -> str:
        year = datetime.now().year
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Helvetica,Arial,sans-serif;background:#f0f4f8;color:#1a202c}}
.outer{{padding:28px 12px}}
.card{{max-width:600px;margin:0 auto;background:#fff;border-radius:18px;
       overflow:hidden;box-shadow:0 6px 32px rgba(0,0,0,.10)}}
.hdr{{background:{header_color};padding:40px 36px;text-align:center;color:#fff}}
.hdr-icon{{font-size:48px;margin-bottom:10px;display:block}}
.hdr h1{{font-size:24px;font-weight:800}}
.hdr p{{margin-top:6px;opacity:.85;font-size:14px}}
.body{{padding:32px 36px}}
.body p{{color:#4a5568;font-size:15px;line-height:1.7;margin-bottom:12px}}
.row{{display:flex;justify-content:space-between;align-items:center;
      padding:11px 0;border-bottom:1px solid #edf2f7}}
.row:last-child{{border-bottom:none}}
.lbl{{color:#a0aec0;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}}
.val{{color:#2d3748;font-weight:700;font-size:14px;text-align:right}}
.btn{{display:inline-block;background:{header_color};color:#fff !important;
      text-decoration:none;padding:14px 34px;border-radius:10px;
      font-weight:700;font-size:15px;margin:16px 0}}
.info-box{{background:#f7fafc;border-left:4px solid #0ea5e9;
           border-radius:0 10px 10px 0;padding:14px 18px;margin:16px 0;
           font-size:14px;color:#374151}}
.footer{{background:#f7fafc;padding:22px 36px;text-align:center;
         color:#a0aec0;font-size:12px;line-height:1.8}}
.footer a{{color:#718096;text-decoration:none}}
</style></head><body>
<div class="outer"><div class="card">
<div class="hdr">
  <span class="hdr-icon">{emoji}</span>
  <h1>{title}</h1>
  <p>{subtitle}</p>
</div>
<div class="body">{body}</div>
<div class="footer">
  <p><strong>SkyMind Flights</strong> &nbsp;·&nbsp; AI-powered smarter travel</p>
  <p style="margin-top:4px">
    <a href="https://skymind.app">Website</a> &nbsp;·&nbsp;
    <a href="https://skymind.app/help">Help</a> &nbsp;·&nbsp;
    <a href="https://skymind.app/unsubscribe">Unsubscribe</a>
  </p>
  <p style="margin-top:6px;font-size:11px">© {year} SkyMind Technologies · Bengaluru, India</p>
</div>
</div></div></body></html>"""

    # ── Templates ─────────────────────────────────────────────────

    def send_welcome(self, to_email: str, name: str) -> bool:
        body = f"""
<p>Hi <strong>{name}</strong>! 👋</p>
<p>Welcome to SkyMind — India's smartest flight booking platform. Here's what you unlocked:</p>
<div class="info-box">🧠 <strong>AI Price Prediction</strong> — Know exactly when to book on 950+ routes</div>
<div class="info-box">🗺️ <strong>Hidden Routes</strong> — Discover cheaper multi-stop paths</div>
<div class="info-box">🔔 <strong>Price Alerts</strong> — SMS + email when fares drop to your budget</div>
<div class="info-box">📊 <strong>30-Day Forecast</strong> — See fare trends before you decide</div>
<p style="text-align:center;margin-top:24px">
  <a href="https://skymind.app/flights" class="btn">✈️ Search Flights Now</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#0ea5e9,#6366f1)",
                          "✈️", "Welcome to SkyMind!", "Your AI travel companion is ready", body)
        return self.send(to_email, "👋 Welcome to SkyMind — Smarter flights await!", html,
                         f"Welcome {name}! Start at skymind.app")

    def send_otp(self, to_email: str, otp: str, purpose: str = "verification") -> bool:
        body = f"""
<p>Your one-time password for <strong>{purpose}</strong>:</p>
<div style="text-align:center;margin:28px 0">
  <div style="display:inline-block;background:#f0f9ff;border:2px solid #bae6fd;
              border-radius:14px;padding:24px 44px">
    <div style="font-size:52px;font-weight:900;letter-spacing:12px;color:#0284c7;
                font-family:'Courier New',monospace">{otp}</div>
    <div style="color:#64748b;font-size:13px;margin-top:8px">Valid for <strong>10 minutes</strong></div>
  </div>
</div>
<div class="info-box" style="border-color:#f59e0b;background:#fffbeb">
  🔒 SkyMind staff will <em>never</em> ask for this code. Keep it private.
</div>"""
        html = self._wrap("linear-gradient(135deg,#0284c7,#0ea5e9)",
                          "🔐", "Verification Code", f"For: {purpose}", body)
        return self.send(to_email, f"🔐 SkyMind OTP: {otp}", html,
                         f"Your SkyMind OTP: {otp}. Valid 10 min. Do not share.")

    def send_booking_confirmation(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>Your booking is confirmed and e-ticket is being generated!</p>
<div style="background:#f0fdf4;border:2px solid #86efac;border-radius:12px;
            padding:18px 24px;text-align:center;margin:20px 0">
  <div style="color:#15803d;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px">Booking Reference</div>
  <div style="font-size:38px;font-weight:900;color:#166534;letter-spacing:6px;font-family:'Courier New',monospace;margin:6px 0">
    {data.get('booking_ref','------')}
  </div>
  <div style="color:#64748b;font-size:13px">Show this at the airport</div>
</div>
<div style="background:#f8fafc;border-radius:12px;padding:20px;text-align:center;margin:16px 0">
  <span style="font-size:32px;font-weight:900;color:#0f172a">{data.get('origin','---')}</span>
  &nbsp; ✈ &nbsp;
  <span style="font-size:32px;font-weight:900;color:#0f172a">{data.get('destination','---')}</span>
  <div style="color:#64748b;font-size:13px;margin-top:6px">
    {data.get('origin_city','')} → {data.get('dest_city','')}
  </div>
</div>
<div>
  <div class="row"><span class="lbl">Flight</span><span class="val">{data.get('flight_number','')}</span></div>
  <div class="row"><span class="lbl">Airline</span><span class="val">{data.get('airline','')}</span></div>
  <div class="row"><span class="lbl">Date</span><span class="val">{data.get('departure_date','')}</span></div>
  <div class="row"><span class="lbl">Departure</span><span class="val">{data.get('departure_time','')}</span></div>
  <div class="row"><span class="lbl">Arrival</span><span class="val">{data.get('arrival_time','')}</span></div>
  <div class="row"><span class="lbl">Terminal</span><span class="val">{data.get('terminal','TBA')}</span></div>
  <div class="row"><span class="lbl">Passengers</span><span class="val">{data.get('passengers','1 Adult')}</span></div>
  <div class="row"><span class="lbl">Cabin</span><span class="val">{data.get('cabin','Economy')}</span></div>
  <div class="row"><span class="lbl">PNR</span><span class="val">{data.get('pnr','')}</span></div>
</div>
<div style="background:linear-gradient(135deg,#10b981,#059669);color:#fff;
            border-radius:12px;padding:18px;text-align:center;margin:18px 0">
  <div style="font-size:12px;opacity:.8">Total Amount Paid</div>
  <div style="font-size:40px;font-weight:900">₹{data.get('amount','')}</div>
</div>
<div class="info-box">⏰ Web check-in opens 48 hours before departure. We'll remind you!</div>
<p style="text-align:center"><a href="https://skymind.app/dashboard" class="btn">View Booking</a></p>"""
        html = self._wrap("linear-gradient(135deg,#10b981,#059669)",
                          "🎉", "Booking Confirmed!", "Your flight is booked and ready", body)
        return self.send(to_email,
                         f"✈️ Booking {data.get('booking_ref')} Confirmed | SkyMind", html,
                         f"Booking {data.get('booking_ref')} confirmed. {data.get('origin')}>{data.get('destination')} on {data.get('departure_date')}. Paid: Rs.{data.get('amount')}")

    def send_payment_receipt(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>Payment received successfully. Here is your receipt.</p>
<div style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;margin:20px 0">
  <div style="background:#f8fafc;padding:12px 18px;font-weight:700;font-size:13px;
              text-transform:uppercase;letter-spacing:.5px;color:#374151">Receipt</div>
  <div style="padding:0 18px">
    <div class="row"><span class="lbl">Amount</span>
      <span class="val" style="color:#16a34a;font-size:20px">₹{data.get('amount','')}</span></div>
    <div class="row"><span class="lbl">Transaction ID</span><span class="val">{data.get('payment_id','')}</span></div>
    <div class="row"><span class="lbl">Order ID</span><span class="val">{data.get('order_id','')}</span></div>
    <div class="row"><span class="lbl">Method</span><span class="val">{data.get('payment_method','')}</span></div>
    <div class="row"><span class="lbl">Date</span><span class="val">{data.get('payment_date', datetime.now().strftime('%d %b %Y %H:%M'))}</span></div>
    <div class="row"><span class="lbl">Status</span><span class="val" style="color:#16a34a">✓ SUCCESS</span></div>
  </div>
</div>
<div class="info-box">🎁 <strong>+{data.get('points_earned',0)} SkyMind Points</strong> added to your account!</div>
<p style="text-align:center"><a href="https://skymind.app/dashboard" class="btn">View Booking</a></p>"""
        html = self._wrap("linear-gradient(135deg,#8b5cf6,#6d28d9)",
                          "💳", "Payment Successful!", "Transaction complete", body)
        return self.send(to_email, f"💳 Payment ₹{data.get('amount')} Received | SkyMind", html, "")

    def send_price_alert(self, to_email: str, data: dict) -> bool:
        savings = float(data.get('target_price',0)) - float(data.get('current_price',0))
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>The price you tracked just <strong style="color:#16a34a">dropped below your target</strong>!</p>
<div style="display:flex;gap:14px;margin:20px 0">
  <div style="flex:1;background:#fef3c7;border:2px solid #fbbf24;border-radius:12px;padding:18px;text-align:center">
    <div style="font-size:11px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:.5px">Your Target</div>
    <div style="font-size:28px;font-weight:900;color:#d97706;margin:6px 0">₹{float(data.get('target_price',0)):,.0f}</div>
  </div>
  <div style="flex:1;background:#dcfce7;border:2px solid #4ade80;border-radius:12px;padding:18px;text-align:center">
    <div style="font-size:11px;font-weight:700;color:#14532d;text-transform:uppercase;letter-spacing:.5px">Current Price</div>
    <div style="font-size:28px;font-weight:900;color:#16a34a;margin:6px 0">₹{float(data.get('current_price',0)):,.0f}</div>
  </div>
</div>
<div style="background:linear-gradient(135deg,#10b981,#059669);color:#fff;border-radius:12px;
            padding:18px;text-align:center;margin:14px 0">
  <div style="font-size:13px;opacity:.85">You save</div>
  <div style="font-size:38px;font-weight:900">₹{savings:,.0f}</div>
</div>
<div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin')} → {data.get('destination')}</span></div>
  <div class="row"><span class="lbl">Travel Date</span><span class="val">{data.get('departure_date','')}</span></div>
  <div class="row"><span class="lbl">Cabin</span><span class="val">{data.get('cabin','Economy')}</span></div>
</div>
<div class="info-box" style="border-color:#ef4444;background:#fef2f2">
  ⚡ <strong>Act fast!</strong> Prices can change in minutes.
</div>
<p style="text-align:center">
  <a href="https://skymind.app/flights?origin={data.get('origin')}&destination={data.get('destination')}&date={data.get('departure_date')}"
     class="btn">Book Now →</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#10b981,#16a34a)",
                          "🎯", "Price Alert Triggered!",
                          f"{data.get('origin')} → {data.get('destination')} dropped to ₹{float(data.get('current_price',0)):,.0f}",
                          body)
        return self.send(to_email,
                         f"🔔 Price Alert: {data.get('origin')}→{data.get('destination')} now ₹{float(data.get('current_price',0)):,.0f}",
                         html,
                         f"Price dropped! {data.get('origin')}>{data.get('destination')} Rs.{float(data.get('current_price',0)):,.0f} (target Rs.{float(data.get('target_price',0)):,.0f}). Book at skymind.app")

    def send_checkin_reminder(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>Online check-in is now open for your flight tomorrow!</p>
<div style="background:#fef3c7;border:2px solid #fbbf24;border-radius:12px;
            padding:22px 26px;margin:20px 0">
  <div style="font-size:24px;font-weight:900;color:#92400e">
    {data.get('origin','---')} → {data.get('destination','---')}
  </div>
  <div style="color:#78350f;margin-top:8px">
    ✈ <strong>{data.get('flight_number','')}</strong> &nbsp;·&nbsp;
    {data.get('departure_date','')} &nbsp;·&nbsp;
    Dep <strong>{data.get('departure_time','')}</strong>
  </div>
  <div style="color:#78350f;margin-top:4px;font-size:14px">
    Terminal: <strong>{data.get('terminal','TBA')}</strong>
  </div>
</div>
<div>
  <div class="row"><span class="lbl">Booking Ref</span><span class="val">{data.get('booking_ref','')}</span></div>
  <div class="row"><span class="lbl">Passengers</span><span class="val">{data.get('passengers','')}</span></div>
  <div class="row"><span class="lbl">Baggage</span><span class="val">{data.get('baggage','15 kg')}</span></div>
</div>
<div class="info-box">🕐 Arrive at airport at least <strong>2 hours</strong> before departure.</div>
<div class="info-box" style="border-color:#8b5cf6;background:#f5f3ff">
  📋 Carry: Valid Aadhaar / Passport + booking reference
</div>
<p style="text-align:center">
  <a href="https://skymind.app/checkin/{data.get('booking_id','')}" class="btn">Check In Online →</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#f59e0b,#d97706)",
                          "⏰", "Check-in Is Open!", f"Flight {data.get('flight_number','')} departs tomorrow", body)
        return self.send(to_email,
                         f"⏰ Check-in Open: {data.get('flight_number','')} on {data.get('departure_date','')}",
                         html, "")

    def send_flight_status(self, to_email: str, data: dict) -> bool:
        status = data.get('status','DELAYED')
        colors = {'DELAYED':'linear-gradient(135deg,#f59e0b,#d97706)',
                  'CANCELLED':'linear-gradient(135deg,#ef4444,#dc2626)',
                  'ON TIME':'linear-gradient(135deg,#10b981,#059669)',
                  'DIVERTED':'linear-gradient(135deg,#8b5cf6,#7c3aed)'}
        icons  = {'DELAYED':'⚠️','CANCELLED':'❌','ON TIME':'✅','DIVERTED':'🔀'}
        color  = colors.get(status,'linear-gradient(135deg,#64748b,#475569)')
        icon   = icons.get(status,'ℹ️')
        body   = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>, there is an update for your flight.</p>
<div>
  <div class="row"><span class="lbl">Flight</span><span class="val">{data.get('flight_number','')}</span></div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','')} → {data.get('destination','')}</span></div>
  <div class="row"><span class="lbl">Original Time</span><span class="val">{data.get('original_time','')}</span></div>
  <div class="row"><span class="lbl">New Time</span><span class="val" style="color:#d97706">{data.get('new_time','TBA')}</span></div>
  <div class="row"><span class="lbl">Delay</span><span class="val">{data.get('delay_minutes','')}</span></div>
  <div class="row"><span class="lbl">Reason</span><span class="val">{data.get('reason','Operational')}</span></div>
</div>
<div class="info-box" style="border-color:#ef4444;background:#fef2f2">
  📞 Rebooking / refund: Call 1800-XXX-XXXX or reply to this email
</div>
<p style="text-align:center"><a href="https://skymind.app/dashboard" class="btn">Manage Booking</a></p>"""
        html = self._wrap(color, icon, f"Flight {status}",
                          f"Flight {data.get('flight_number','')} update", body)
        return self.send(to_email,
                         f"{icon} Flight {data.get('flight_number','')} {status} | SkyMind", html, "")

    def send_cancellation(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>, your booking has been cancelled.</p>
<div>
  <div class="row"><span class="lbl">Booking Ref</span><span class="val">{data.get('booking_ref','')}</span></div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','')} → {data.get('destination','')}</span></div>
  <div class="row"><span class="lbl">Travel Date</span><span class="val">{data.get('departure_date','')}</span></div>
  <div class="row"><span class="lbl">Refund Amount</span>
    <span class="val" style="color:#16a34a;font-size:18px">₹{data.get('refund_amount','0')}</span></div>
  <div class="row"><span class="lbl">Refund To</span><span class="val">{data.get('refund_to','Original method')}</span></div>
  <div class="row"><span class="lbl">Refund ETA</span><span class="val">{data.get('refund_eta','5–7 days')}</span></div>
</div>
<div class="info-box">⚡ UPI/Wallet refunds in 2–4 hours. Bank cards take 5–7 working days.</div>
<p style="text-align:center"><a href="https://skymind.app/flights" class="btn">Book New Flight</a></p>"""
        html = self._wrap("linear-gradient(135deg,#64748b,#475569)",
                          "❌", "Booking Cancelled",
                          f"Refund of ₹{data.get('refund_amount','0')} is on its way", body)
        return self.send(to_email,
                         f"❌ Booking {data.get('booking_ref')} Cancelled | SkyMind", html, "")

    def send_refund_processed(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>, your refund has been processed!</p>
<div style="background:linear-gradient(135deg,#10b981,#059669);color:#fff;
            border-radius:12px;padding:22px;text-align:center;margin:20px 0">
  <div style="font-size:13px;opacity:.85">Refund Amount</div>
  <div style="font-size:46px;font-weight:900;margin:6px 0">₹{data.get('amount','')}</div>
  <div style="font-size:13px;opacity:.8">Refund ID: {data.get('refund_id','')}</div>
</div>
<div>
  <div class="row"><span class="lbl">Booking Ref</span><span class="val">{data.get('booking_ref','')}</span></div>
  <div class="row"><span class="lbl">Refund To</span><span class="val">{data.get('refund_to','')}</span></div>
  <div class="row"><span class="lbl">Expected</span><span class="val">{data.get('eta','5-7 business days')}</span></div>
</div>
<p style="text-align:center"><a href="https://skymind.app/dashboard" class="btn">View Dashboard</a></p>"""
        html = self._wrap("linear-gradient(135deg,#10b981,#059669)",
                          "💸", "Refund Processed!", "Money is on its way", body)
        return self.send(to_email,
                         f"💸 Refund ₹{data.get('amount','')} Processed | SkyMind", html, "")

    def send_promotion(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>{data.get('intro_text','We have a special offer just for you!')}</p>
<div style="background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff;
            border-radius:16px;padding:28px;text-align:center;margin:20px 0">
  <div style="font-size:12px;opacity:.8;text-transform:uppercase;letter-spacing:1px">Limited Offer</div>
  <div style="font-size:44px;font-weight:900;margin:10px 0">{data.get('discount_text','')}</div>
  <div style="font-size:16px;opacity:.9">{data.get('offer_description','')}</div>
  <div style="margin-top:14px;background:rgba(255,255,255,.15);border-radius:8px;
              padding:10px;display:inline-block">
    <div style="font-size:11px;opacity:.8;letter-spacing:1px">USE CODE</div>
    <div style="font-size:26px;font-weight:900;letter-spacing:4px;font-family:monospace">
      {data.get('coupon_code','')}
    </div>
  </div>
</div>
<div class="info-box">📅 Valid until: <strong>{data.get('valid_until','')}</strong></div>
<p style="text-align:center">
  <a href="https://skymind.app/flights?coupon={data.get('coupon_code','')}" class="btn">Book & Save →</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#0ea5e9,#6366f1)",
                          "🎁", data.get('offer_title','Special Offer!'),
                          data.get('offer_subtitle',''), body)
        return self.send(to_email,
                         data.get('subject','🎁 Exclusive Offer — SkyMind'), html, "")


# ================================================================
# 2. SMS SERVICE — Fast2SMS (India) + Twilio fallback
# ================================================================

class SMSService:
    def __init__(self):
        self.fast2sms_key = os.getenv("FAST2SMS_API_KEY", "")
        self.twilio_sid   = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from  = os.getenv("TWILIO_PHONE_NUMBER", "")

    def _clean(self, phone: str) -> str:
        return phone.replace("+91","").replace(" ","").replace("-","").strip()[-10:]

    def _is_indian(self, phone: str) -> bool:
        return phone.startswith("+91") or (phone.isdigit() and len(phone) == 10)

    def _fast2sms(self, phone: str, message: str) -> bool:
        if not self.fast2sms_key:
            return False
        try:
            import httpx
            r = httpx.post("https://www.fast2sms.com/dev/bulkV2",
                           headers={"authorization": self.fast2sms_key},
                           json={"route":"q","message":message[:160],
                                 "language":"english","flash":0,
                                 "numbers":self._clean(phone)}, timeout=10)
            ok = r.json().get("return", False)
            if ok: logger.info("Fast2SMS sent -> %s", phone)
            else:  logger.error("Fast2SMS error: %s", r.text)
            return ok
        except Exception as e:
            logger.error("Fast2SMS exception: %s", e)
            return False

    def _twilio(self, phone: str, message: str) -> bool:
        if not (self.twilio_sid and self.twilio_token and self.twilio_from):
            return False
        try:
            from twilio.rest import Client
            msg = Client(self.twilio_sid, self.twilio_token).messages.create(
                body=message, from_=self.twilio_from, to=phone)
            logger.info("Twilio SMS sent -> %s | %s", phone, msg.sid)
            return True
        except Exception as e:
            logger.error("Twilio error: %s", e)
            return False

    def send(self, phone: str, message: str) -> bool:
        if not phone: return False
        if self._is_indian(phone) and self._fast2sms(phone, message):
            return True
        return self._twilio(phone, message)

    def send_otp(self, phone: str, otp: str) -> bool:
        return self.send(phone, f"SkyMind OTP:{otp} Valid 10min DO NOT SHARE -SKYMND")

    def send_booking_confirmation(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"SkyMind:Bkg {d['booking_ref']} CONFIRMED {d['origin']}>{d['destination']} "
            f"{d['departure_date']} {d.get('departure_time','')} Rs.{d['amount']} PNR:{d.get('pnr','')} -SKYMND")

    def send_price_alert(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"SkyMind ALERT {d['origin']}>{d['destination']} NOW Rs.{float(d['current_price']):,.0f} "
            f"(Target Rs.{float(d['target_price']):,.0f}) Book:skymind.app/flights -SKYMND")

    def send_checkin_reminder(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"SkyMind:Checkin OPEN {d['flight_number']} {d['origin']}>{d['destination']} "
            f"Dep:{d['departure_time']} T{d.get('terminal','TBA')} Ref:{d['booking_ref']} -SKYMND")

    def send_flight_status(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"SkyMind:{d['flight_number']} {d.get('status','DELAYED')} "
            f"NewTime:{d.get('new_time','TBA')} Sorry for inconvenience -SKYMND")

    def send_cancellation(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"SkyMind:Bkg {d['booking_ref']} CANCELLED Refund Rs.{d.get('refund_amount','0')} "
            f"in {d.get('refund_eta','5-7 days')} -SKYMND")

    def send_refund_processed(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"SkyMind:Refund Rs.{d['amount']} processed for {d['booking_ref']} "
            f"arrives {d.get('eta','5-7 days')} -SKYMND")

    def send_promotion(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"SkyMind:{d.get('discount_text','')} Use code {d.get('coupon_code','')} "
            f"till {d.get('valid_until','')} Book:skymind.app -SKYMND")


# ================================================================
# 3. WHATSAPP — Twilio WhatsApp Business API
# ================================================================

class WhatsAppService:
    def __init__(self):
        self.twilio_sid  = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token= os.getenv("TWILIO_AUTH_TOKEN", "")
        self.wa_from     = os.getenv("TWILIO_WHATSAPP_NUMBER","whatsapp:+14155238886")

    def send(self, phone: str, message: str) -> bool:
        if not (self.twilio_sid and self.twilio_token): return False
        try:
            from twilio.rest import Client
            to = f"whatsapp:+91{phone.replace('+91','').strip()}"
            msg = Client(self.twilio_sid,self.twilio_token).messages.create(
                body=message, from_=self.wa_from, to=to)
            logger.info("WhatsApp sent -> %s | %s", phone, msg.sid)
            return True
        except Exception as e:
            logger.error("WhatsApp error: %s", e)
            return False

    def send_otp(self, phone: str, otp: str) -> bool:
        return self.send(phone, f"🔐 *SkyMind OTP:* {otp}\nValid 10 min. Do NOT share.")

    def send_booking_confirmation(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"✈️ *SkyMind Booking Confirmed!*\n\n"
            f"*Ref:* {d['booking_ref']}\n"
            f"*Flight:* {d['origin']} → {d['destination']}\n"
            f"*Date:* {d['departure_date']} at {d.get('departure_time','')}\n"
            f"*PNR:* {d.get('pnr','')}\n"
            f"*Paid:* ₹{d['amount']}\n\nBon voyage! 🌟")

    def send_price_alert(self, phone: str, d: dict) -> bool:
        savings = float(d['target_price']) - float(d['current_price'])
        return self.send(phone,
            f"🎯 *Price Alert — SkyMind*\n\n"
            f"{d['origin']} → {d['destination']}\n"
            f"Current: ₹{float(d['current_price']):,.0f}\n"
            f"Target: ₹{float(d['target_price']):,.0f}\n"
            f"*Save: ₹{savings:,.0f}*\n\n⚡ Book now at skymind.app/flights")

    def send_checkin_reminder(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"⏰ *Check-in Open — SkyMind*\n\n"
            f"*Flight:* {d['flight_number']}\n"
            f"*Route:* {d['origin']} → {d['destination']}\n"
            f"*Departs:* {d['departure_time']} tomorrow\n"
            f"*Terminal:* {d.get('terminal','TBA')}\n\nArrive 2 hours early ✓")

    def send_cancellation(self, phone: str, d: dict) -> bool:
        return self.send(phone,
            f"❌ *Booking Cancelled — SkyMind*\n\n"
            f"Ref: {d['booking_ref']}\n"
            f"Refund: ₹{d.get('refund_amount','0')} in {d.get('refund_eta','5-7 days')}")


# ================================================================
# 4. OTP UTILITIES
# ================================================================

def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_otp(otp: str, stored_hash: str) -> bool:
    return hashlib.sha256(otp.encode()).hexdigest() == stored_hash


# ================================================================
# 5. UNIFIED DISPATCHER
# ================================================================

class NotificationDispatcher:
    """Send to all enabled channels in one call."""

    def __init__(self):
        self.email    = EmailService()
        self.sms      = SMSService()
        self.whatsapp = WhatsAppService()

    @staticmethod
    def _booking_data(b: dict) -> dict:
        return {
            "name":           b.get("user_name", b.get("full_name","Traveller")),
            "booking_ref":    b.get("booking_reference",""),
            "booking_id":     b.get("id",""),
            "pnr":            b.get("pnr", b.get("amadeus_booking_id","")),
            "origin":         b.get("origin_code",""),
            "origin_city":    b.get("origin_city",""),
            "destination":    b.get("destination_code",""),
            "dest_city":      b.get("dest_city",""),
            "flight_number":  b.get("flight_number",""),
            "airline":        b.get("airline_name",""),
            "departure_date": b.get("departure_date",""),
            "departure_time": b.get("departure_time",""),
            "arrival_time":   b.get("arrival_time",""),
            "terminal":       b.get("terminal","TBA"),
            "cabin":          b.get("cabin_class","Economy"),
            "passengers":     b.get("passenger_names","1 Adult"),
            "baggage":        b.get("baggage_allowance","15 kg"),
            "amount":         f"{float(b.get('total_price',0)):,.0f}",
            "payment_method": b.get("payment_method","Online"),
            "payment_id":     b.get("payment_id",""),
        }

    def send_welcome(self, email: str, name: str):
        self.email.send_welcome(email, name)

    def send_otp(self, email: str = None, phone: str = None,
                 purpose: str = "verification") -> str:
        otp = generate_otp()
        if email: self.email.send_otp(email, otp, purpose)
        if phone:
            self.sms.send_otp(phone, otp)
            self.whatsapp.send_otp(phone, otp)
        return otp  # caller hashes + stores

    def send_booking_confirmation(self, booking: dict, profile: dict):
        d = self._booking_data(booking)
        if profile.get("notify_email") and booking.get("contact_email"):
            self.email.send_booking_confirmation(booking["contact_email"], d)
        if profile.get("notify_sms") and booking.get("contact_phone"):
            self.sms.send_booking_confirmation(booking["contact_phone"], d)
        if profile.get("notify_whatsapp") and booking.get("contact_phone"):
            self.whatsapp.send_booking_confirmation(booking["contact_phone"], d)

    def send_payment_receipt(self, booking: dict, profile: dict, payment: dict):
        d = {**self._booking_data(booking), **payment}
        if profile.get("notify_email") and booking.get("contact_email"):
            self.email.send_payment_receipt(booking["contact_email"], d)

    def send_price_alert(self, alert: dict, current_price: float):
        d = {
            "name":          alert.get("full_name","Traveller"),
            "origin":        alert.get("origin_code",""),
            "destination":   alert.get("destination_code",""),
            "departure_date": str(alert.get("departure_date","")),
            "target_price":  float(alert.get("target_price",0)),
            "current_price": current_price,
            "cabin":         alert.get("cabin_class","Economy"),
        }
        if alert.get("notify_email") and alert.get("email"):
            self.email.send_price_alert(alert["email"], d)
        if alert.get("notify_sms") and alert.get("phone"):
            self.sms.send_price_alert(alert["phone"], d)
        if alert.get("notify_whatsapp") and alert.get("phone"):
            self.whatsapp.send_price_alert(alert["phone"], d)

    def send_checkin_reminder(self, booking: dict, profile: dict):
        d = self._booking_data(booking)
        if profile.get("notify_email") and booking.get("contact_email"):
            self.email.send_checkin_reminder(booking["contact_email"], d)
        if profile.get("notify_sms") and booking.get("contact_phone"):
            self.sms.send_checkin_reminder(booking["contact_phone"], d)
        if profile.get("notify_whatsapp") and booking.get("contact_phone"):
            self.whatsapp.send_checkin_reminder(booking["contact_phone"], d)

    def send_flight_status(self, booking: dict, profile: dict, status_data: dict):
        d = {**self._booking_data(booking), **status_data}
        if profile.get("notify_email") and booking.get("contact_email"):
            self.email.send_flight_status(booking["contact_email"], d)
        if profile.get("notify_sms") and booking.get("contact_phone"):
            self.sms.send_flight_status(booking["contact_phone"], d)

    def send_cancellation(self, booking: dict, profile: dict, refund_data: dict):
        d = {**self._booking_data(booking), **refund_data}
        if profile.get("notify_email") and booking.get("contact_email"):
            self.email.send_cancellation(booking["contact_email"], d)
        if profile.get("notify_sms") and booking.get("contact_phone"):
            self.sms.send_cancellation(booking["contact_phone"], d)
        if profile.get("notify_whatsapp") and booking.get("contact_phone"):
            self.whatsapp.send_cancellation(booking["contact_phone"], d)

    def send_refund_processed(self, booking: dict, profile: dict, refund_data: dict):
        d = {**self._booking_data(booking), **refund_data}
        if profile.get("notify_email") and booking.get("contact_email"):
            self.email.send_refund_processed(booking["contact_email"], d)
        if profile.get("notify_sms") and booking.get("contact_phone"):
            self.sms.send_refund_processed(booking["contact_phone"], d)

    def send_promotion(self, email: str, phone: str, name: str, promo: dict,
                       notify_email: bool = True, notify_sms: bool = False):
        d = {**promo, "name": name}
        if notify_email and email: self.email.send_promotion(email, d)
        if notify_sms and phone:   self.sms.send_promotion(phone, d)


# Global singleton
dispatcher = NotificationDispatcher()
