"""
SkyMind — Notification Service
Channels: Gmail SMTP · Fast2SMS · Twilio SMS · Twilio WhatsApp
Types:    Booking · OTP · Price Alert · Reminder · Welcome · Cancellation
"""

import hashlib
import logging
import os
import random
import smtplib
import string
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Retry helper
# ══════════════════════════════════════════════════════════════════════

def safe_send(func, *args, retries: int = 2, delay: float = 1.0):
    for attempt in range(retries):
        try:
            result = func(*args)
            if result:
                return True
        except Exception as exc:
            logger.error("Notification attempt %d error: %s", attempt + 1, exc)
        time.sleep(delay)
    return False


# ══════════════════════════════════════════════════════════════════════
# 1. EMAIL SERVICE — Gmail SMTP
# ══════════════════════════════════════════════════════════════════════

class EmailService:
    def __init__(self):
        self.gmail_user     = os.getenv("GMAIL_USER", "")
        self.gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
        self.from_name      = os.getenv("EMAIL_FROM_NAME", "SkyMind Flights")
        self.reply_to       = os.getenv("EMAIL_REPLY_TO", "")
        self.smtp_host      = "smtp.gmail.com"
        self.smtp_port      = 587

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
            logger.info("Email sent → %s | %s", to_email, subject)
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("Gmail auth failed — check GMAIL_APP_PASSWORD")
            return False
        except Exception as exc:
            logger.error("Email error → %s: %s", to_email, exc)
            return False

    # ── HTML wrapper ────────────────────────────────────────────────
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
.card{{max-width:600px;margin:0 auto;background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 6px 32px rgba(0,0,0,.10)}}
.hdr{{background:{header_color};padding:40px 36px;text-align:center;color:#fff}}
.hdr-icon{{font-size:48px;margin-bottom:10px;display:block}}
.hdr h1{{font-size:24px;font-weight:800}}
.hdr p{{margin-top:6px;opacity:.85;font-size:14px}}
.body{{padding:32px 36px}}
.body p{{color:#4a5568;font-size:15px;line-height:1.7;margin-bottom:12px}}
.row{{display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:1px solid #edf2f7}}
.row:last-child{{border-bottom:none}}
.lbl{{color:#a0aec0;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}}
.val{{color:#2d3748;font-weight:700;font-size:14px;text-align:right}}
.btn{{display:inline-block;background:{header_color};color:#fff!important;text-decoration:none;padding:14px 34px;border-radius:10px;font-weight:700;font-size:15px;margin:16px 0}}
.info-box{{background:#f7fafc;border-left:4px solid #0ea5e9;border-radius:0 10px 10px 0;padding:14px 18px;margin:16px 0;font-size:14px;color:#374151}}
.footer{{background:#f7fafc;padding:22px 36px;text-align:center;color:#a0aec0;font-size:12px;line-height:1.8}}
.footer a{{color:#718096;text-decoration:none}}
</style></head><body>
<div class="outer"><div class="card">
<div class="hdr"><span class="hdr-icon">{emoji}</span><h1>{title}</h1><p>{subtitle}</p></div>
<div class="body">{body}</div>
<div class="footer">
  <p><strong>SkyMind Flights</strong> &nbsp;·&nbsp; AI-powered smarter travel</p>
  <p style="margin-top:4px"><a href="https://skymind.app">Website</a> &nbsp;·&nbsp; <a href="https://skymind.app/help">Help</a></p>
  <p style="margin-top:6px;font-size:11px">© {year} SkyMind Technologies · India</p>
</div></div></div></body></html>"""

    # ── Templates ───────────────────────────────────────────────────
    def send_welcome(self, to_email: str, name: str) -> bool:
        body = f"""
<p>Hi <strong>{name}</strong>! 👋</p>
<p>Welcome to SkyMind — India's smartest flight booking platform.</p>
<div class="info-box">🧠 <strong>AI Price Prediction</strong> — Know exactly when to book on 950+ routes</div>
<div class="info-box">📊 <strong>30-Day Forecast</strong> — See fare trends before you decide</div>
<div class="info-box">🔔 <strong>Price Alerts</strong> — SMS + email when fares drop to your budget</div>
<p style="text-align:center;margin-top:24px">
  <a href="https://skymind.app/flights" class="btn">✈️ Search Flights Now</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#0ea5e9,#6366f1)", "✈️", "Welcome to SkyMind!", "Your AI travel companion is ready", body)
        return self.send(to_email, "👋 Welcome to SkyMind — Smarter flights await!", html, f"Welcome {name}! Start at skymind.app")

    def send_otp(self, to_email: str, otp: str, purpose: str = "verification") -> bool:
        body = f"""
<p>Your one-time password for <strong>{purpose}</strong>:</p>
<div style="text-align:center;margin:28px 0">
  <div style="display:inline-block;background:#f0f9ff;border:2px solid #bae6fd;border-radius:14px;padding:24px 44px">
    <div style="font-size:52px;font-weight:900;letter-spacing:12px;color:#0284c7;font-family:'Courier New',monospace">{otp}</div>
    <div style="color:#64748b;font-size:13px;margin-top:8px">Valid for <strong>10 minutes</strong></div>
  </div>
</div>
<div class="info-box" style="border-color:#f59e0b;background:#fffbeb">🔒 SkyMind staff will <em>never</em> ask for this code. Keep it private.</div>"""
        html = self._wrap("linear-gradient(135deg,#0284c7,#0ea5e9)", "🔐", "Verification Code", f"For: {purpose}", body)
        return self.send(to_email, f"🔐 SkyMind OTP: {otp}", html, f"Your SkyMind OTP: {otp}. Valid 10 min. Do not share.")

    def send_booking_confirmation(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>Your booking is confirmed!</p>
<div style="background:#f0fdf4;border:2px solid #86efac;border-radius:12px;padding:18px 24px;text-align:center;margin:20px 0">
  <div style="color:#15803d;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px">Booking Reference</div>
  <div style="font-size:38px;font-weight:900;color:#166534;letter-spacing:6px;font-family:'Courier New',monospace;margin:6px 0">{data.get('booking_ref','------')}</div>
  <div style="color:#64748b;font-size:13px">Show this at the airport</div>
</div>
<div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','---')} → {data.get('destination','---')}</span></div>
  <div class="row"><span class="lbl">Date</span><span class="val">{data.get('departure_date','')}</span></div>
  <div class="row"><span class="lbl">Amount Paid</span><span class="val" style="color:#16a34a;font-size:18px">{data.get('amount','')}</span></div>
</div>
<div class="info-box">⏰ Web check-in opens 48 hours before departure.</div>
<p style="text-align:center"><a href="https://skymind.app/dashboard" class="btn">View Booking</a></p>"""
        html = self._wrap("linear-gradient(135deg,#10b981,#059669)", "🎉", "Booking Confirmed!", "Your flight is booked and ready", body)
        return self.send(to_email, f"✈️ Booking {data.get('booking_ref')} Confirmed | SkyMind", html, f"Booking {data.get('booking_ref')} confirmed. Amount: {data.get('amount')}")

    def send_price_alert(self, to_email: str, data: dict) -> bool:
        try:
            savings = float(data.get("target_price", 0)) - float(data.get("current_price", 0))
        except (TypeError, ValueError):
            savings = 0
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>The price you tracked just <strong style="color:#16a34a">dropped below your target</strong>!</p>
<div style="display:flex;gap:14px;margin:20px 0;flex-wrap:wrap">
  <div style="flex:1;min-width:120px;background:#fef3c7;border:2px solid #fbbf24;border-radius:12px;padding:18px;text-align:center">
    <div style="font-size:11px;font-weight:700;color:#92400e;text-transform:uppercase">Your Target</div>
    <div style="font-size:28px;font-weight:900;color:#d97706;margin:6px 0">₹{float(data.get('target_price',0)):,.0f}</div>
  </div>
  <div style="flex:1;min-width:120px;background:#dcfce7;border:2px solid #4ade80;border-radius:12px;padding:18px;text-align:center">
    <div style="font-size:11px;font-weight:700;color:#14532d;text-transform:uppercase">Current Price</div>
    <div style="font-size:28px;font-weight:900;color:#16a34a;margin:6px 0">₹{float(data.get('current_price',0)):,.0f}</div>
  </div>
</div>
<div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','')} → {data.get('destination','')}</span></div>
  <div class="row"><span class="lbl">Travel Date</span><span class="val">{data.get('departure_date','')}</span></div>
  <div class="row"><span class="lbl">You Save</span><span class="val" style="color:#16a34a">₹{savings:,.0f}</span></div>
</div>
<div class="info-box" style="border-color:#ef4444;background:#fef2f2">⚡ <strong>Act fast!</strong> Prices can change in minutes.</div>
<p style="text-align:center"><a href="https://skymind.app/flights?origin={data.get('origin')}&destination={data.get('destination')}&date={data.get('departure_date')}" class="btn">Book Now →</a></p>"""
        html = self._wrap("linear-gradient(135deg,#10b981,#16a34a)", "🎯", "Price Alert Triggered!", f"{data.get('origin','')} → {data.get('destination','')} price dropped!", body)
        return self.send(to_email, f"🔔 Price Alert: {data.get('origin')}→{data.get('destination')} now ₹{float(data.get('current_price',0)):,.0f}", html, f"Price dropped! Book now at skymind.app")

    def send_cancellation(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>, your booking has been cancelled.</p>
<div>
  <div class="row"><span class="lbl">Booking Ref</span><span class="val">{data.get('booking_ref','')}</span></div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','')} → {data.get('destination','')}</span></div>
  <div class="row"><span class="lbl">Refund Amount</span><span class="val" style="color:#16a34a;font-size:18px">₹{data.get('refund_amount','0')}</span></div>
  <div class="row"><span class="lbl">Refund ETA</span><span class="val">{data.get('refund_eta','5–7 days')}</span></div>
</div>
<p style="text-align:center"><a href="https://skymind.app/flights" class="btn">Book New Flight</a></p>"""
        html = self._wrap("linear-gradient(135deg,#64748b,#475569)", "❌", "Booking Cancelled", f"Refund of ₹{data.get('refund_amount','0')} is on its way", body)
        return self.send(to_email, f"❌ Booking {data.get('booking_ref')} Cancelled | SkyMind", html, "")


# ══════════════════════════════════════════════════════════════════════
# 2. SMS SERVICE — Fast2SMS (India) + Twilio fallback
# ══════════════════════════════════════════════════════════════════════

class SMSService:
    def __init__(self):
        self.fast2sms_key = os.getenv("FAST2SMS_API_KEY", "")
        self.twilio_sid   = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from  = os.getenv("TWILIO_PHONE_NUMBER", "")

    def _clean(self, phone: str) -> str:
        return phone.replace("+91", "").replace(" ", "").replace("-", "").strip()[-10:]

    def _is_indian(self, phone: str) -> bool:
        return phone.startswith("+91") or (phone.isdigit() and len(phone) == 10)

    def _fast2sms(self, phone: str, message: str) -> bool:
        if not self.fast2sms_key:
            return False
        try:
            import httpx
            r = httpx.post(
                "https://www.fast2sms.com/dev/bulkV2",
                headers={"authorization": self.fast2sms_key},
                json={"route": "q", "message": message[:160], "language": "english", "flash": 0, "numbers": self._clean(phone)},
                timeout=10,
            )
            ok = r.json().get("return", False)
            if ok:
                logger.info("Fast2SMS sent → %s", phone)
            else:
                logger.error("Fast2SMS error: %s", r.text[:200])
            return ok
        except Exception as exc:
            logger.error("Fast2SMS exception: %s", exc)
            return False

    def _twilio(self, phone: str, message: str) -> bool:
        if not (self.twilio_sid and self.twilio_token and self.twilio_from):
            return False
        try:
            from twilio.rest import Client  # type: ignore
            msg = Client(self.twilio_sid, self.twilio_token).messages.create(body=message, from_=self.twilio_from, to=phone)
            logger.info("Twilio SMS sent → %s | %s", phone, msg.sid)
            return True
        except Exception as exc:
            logger.error("Twilio SMS error: %s", exc)
            return False

    def send(self, phone: str, message: str) -> bool:
        if not phone:
            return False
        if self._is_indian(phone) and self._fast2sms(phone, message):
            return True
        return self._twilio(phone, message)

    def send_otp(self, phone: str, otp: str) -> bool:
        return self.send(phone, f"SkyMind OTP:{otp} Valid 10min DO NOT SHARE -SKYMND")

    def send_booking_confirmation(self, phone: str, d: dict) -> bool:
        return self.send(phone, f"SkyMind:Bkg {d.get('booking_ref','')} CONFIRMED {d.get('origin','')}>{d.get('destination','')} Rs.{d.get('amount','')} -SKYMND")

    def send_price_alert(self, phone: str, d: dict) -> bool:
        return self.send(phone, f"SkyMind ALERT {d.get('origin','')}>{d.get('destination','')} NOW Rs.{float(d.get('current_price',0)):,.0f} (Target Rs.{float(d.get('target_price',0)):,.0f}) Book:skymind.app -SKYMND")

    def send_cancellation(self, phone: str, d: dict) -> bool:
        return self.send(phone, f"SkyMind:Bkg {d.get('booking_ref','')} CANCELLED Refund Rs.{d.get('refund_amount','0')} in {d.get('refund_eta','5-7 days')} -SKYMND")


# ══════════════════════════════════════════════════════════════════════
# 3. WHATSAPP — Twilio WhatsApp Business API
# ══════════════════════════════════════════════════════════════════════

class WhatsAppService:
    def __init__(self):
        self.twilio_sid  = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token= os.getenv("TWILIO_AUTH_TOKEN", "")
        self.wa_from     = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

    def send(self, phone: str, message: str) -> bool:
        if not (self.twilio_sid and self.twilio_token):
            return False
        try:
            from twilio.rest import Client  # type: ignore
            phone = phone.replace("+", "").strip()
            if not phone.startswith("91"):
                phone = "91" + phone
            to = f"whatsapp:+{phone}"
            msg = Client(self.twilio_sid, self.twilio_token).messages.create(body=message, from_=self.wa_from, to=to)
            logger.info("WhatsApp sent → %s | %s", phone, msg.sid)
            return True
        except Exception as exc:
            logger.error("WhatsApp error: %s", exc)
            return False

    def send_otp(self, phone: str, otp: str) -> bool:
        return self.send(phone, f"🔐 *SkyMind OTP:* {otp}\nValid 10 min. Do NOT share.")

    def send_booking_confirmation(self, phone: str, d: dict) -> bool:
        return self.send(phone, f"✈️ *SkyMind Booking Confirmed!*\n\n*Ref:* {d.get('booking_ref','')}\n*Route:* {d.get('origin','')} → {d.get('destination','')}\n*Amount:* ₹{d.get('amount','')}\n\nBon voyage! 🌟")

    def send_price_alert(self, phone: str, d: dict) -> bool:
        try:
            savings = float(d.get("target_price", 0)) - float(d.get("current_price", 0))
        except (TypeError, ValueError):
            savings = 0
        return self.send(phone, f"🎯 *Price Alert — SkyMind*\n\n{d.get('origin','')} → {d.get('destination','')}\nCurrent: ₹{float(d.get('current_price',0)):,.0f}\nTarget: ₹{float(d.get('target_price',0)):,.0f}\n*Save: ₹{savings:,.0f}*\n\n⚡ Book now at skymind.app/flights")

    def send_cancellation(self, phone: str, d: dict) -> bool:
        return self.send(phone, f"❌ *Booking Cancelled — SkyMind*\n\nRef: {d.get('booking_ref','')}\nRefund: ₹{d.get('refund_amount','0')} in {d.get('refund_eta','5-7 days')}")


# ══════════════════════════════════════════════════════════════════════
# 4. OTP UTILITIES
# ══════════════════════════════════════════════════════════════════════

def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_otp(otp: str, stored_hash: str) -> bool:
    return hashlib.sha256(otp.encode()).hexdigest() == stored_hash


# ══════════════════════════════════════════════════════════════════════
# 5. UNIFIED DISPATCHER
# ══════════════════════════════════════════════════════════════════════

class NotificationDispatcher:
    def __init__(self):
        self.email    = EmailService()
        self.sms      = SMSService()
        self.whatsapp = WhatsAppService()

    def send_welcome(self, email: str, name: str) -> None:
        try:
            self.email.send_welcome(email, name)
        except Exception as exc:
            logger.error("Welcome email error: %s", exc)

    def send_otp(self, email: Optional[str] = None, phone: Optional[str] = None, purpose: str = "verification") -> str:
        otp = generate_otp()
        if email:
            try:
                self.email.send_otp(email, otp, purpose)
            except Exception as exc:
                logger.error("OTP email error: %s", exc)
        if phone:
            try:
                self.sms.send_otp(phone, otp)
            except Exception as exc:
                logger.error("OTP SMS error: %s", exc)
        return otp

    def send_booking_confirmation(self, booking: dict, profile: dict) -> None:
        d = _booking_to_comms(booking)
        if profile.get("notify_email") and booking.get("contact_email"):
            safe_send(self.email.send_booking_confirmation, booking["contact_email"], d)
        if profile.get("notify_sms") and booking.get("contact_phone"):
            safe_send(self.sms.send_booking_confirmation, booking["contact_phone"], d)
        if profile.get("notify_whatsapp") and booking.get("contact_phone"):
            safe_send(self.whatsapp.send_booking_confirmation, booking["contact_phone"], d)

    def send_price_alert(self, alert: dict, current_price: float) -> None:
        d = {
            "name":          alert.get("full_name", "Traveller"),
            "origin":        alert.get("origin_code", ""),
            "destination":   alert.get("destination_code", ""),
            "departure_date":str(alert.get("departure_date", "")),
            "target_price":  float(alert.get("target_price", 0)),
            "current_price": current_price,
        }
        email = alert.get("email")
        phone = alert.get("phone")
        if alert.get("notify_email") and email:
            if safe_send(self.email.send_price_alert, email, d):
                return
        if alert.get("notify_sms") and phone:
            if safe_send(self.sms.send_price_alert, phone, d):
                return
        if alert.get("notify_whatsapp") and phone:
            safe_send(self.whatsapp.send_price_alert, phone, d)

    def send_cancellation(self, booking: dict, profile: dict, refund_data: dict) -> None:
        d = {**_booking_to_comms(booking), **refund_data}
        if profile.get("notify_email") and booking.get("contact_email"):
            safe_send(self.email.send_cancellation, booking["contact_email"], d)
        if profile.get("notify_sms") and booking.get("contact_phone"):
            safe_send(self.sms.send_cancellation, booking["contact_phone"], d)
        if profile.get("notify_whatsapp") and booking.get("contact_phone"):
            safe_send(self.whatsapp.send_cancellation, booking["contact_phone"], d)


def _booking_to_comms(b: dict) -> dict:
    """Extract common communication fields from a booking dict."""
    return {
        "name":         b.get("passengers", [{}])[0].get("first_name", "Traveller") if b.get("passengers") else "Traveller",
        "booking_ref":  b.get("booking_reference", ""),
        "origin":       b.get("origin_code", ""),
        "destination":  b.get("destination_code", ""),
        "departure_date": b.get("departure_date", ""),
        "amount":       f"{b.get('currency','INR')} {float(b.get('total_price',0)):,.2f}",
        "payment_id":   b.get("razorpay_payment_id", ""),
        "refund_amount":str(b.get("refund_amount", "0")),
        "refund_eta":   "5–7 business days",
    }


# ── Singleton ─────────────────────────────────────────────────────────
dispatcher = NotificationDispatcher()
