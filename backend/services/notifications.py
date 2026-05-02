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
from email.mime.application import MIMEApplication
from typing import Any, Optional, List, Tuple

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

    def send(self, to_email: str, subject: str, html_body: str, text_body: str = "", attachments: List[Tuple[str, bytes]] = None) -> bool:
        if not self.gmail_user or not self.gmail_password:
            logger.warning("Gmail credentials missing — email not sent to %s", to_email)
            return False
        try:
            # Using 'mixed' to support both body and attachments
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"]    = f"{self.from_name} <{self.gmail_user}>"
            msg["To"]      = to_email
            if self.reply_to:
                msg["Reply-To"] = self.reply_to

            # Body part (alternative for text/html)
            body = MIMEMultipart("alternative")
            if text_body:
                body.attach(MIMEText(text_body, "plain", "utf-8"))
            body.attach(MIMEText(html_body, "html", "utf-8"))
            msg.attach(body)

            # Attachments
            if attachments:
                for filename, data in attachments:
                    part = MIMEApplication(data)
                    part.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(part)

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
        # Premium Noir Redesign
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#0b0c0d;color:#ffffff;line-height:1.6}}
.outer{{padding:40px 12px;background:#0b0c0d}}
.card{{max-width:600px;margin:0 auto;background:#1a1b1e;border-radius:24px;overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,0.5);border:1px solid #2c2e33}}
.hdr{{background:{header_color};padding:50px 40px;text-align:center;color:#ffffff;border-bottom:1px solid rgba(255,255,255,0.05)}}
.hdr h1{{font-size:36px;font-weight:800;letter-spacing:-1px;text-transform:uppercase;margin-bottom:8px}}
.hdr p{{opacity:.7;font-size:15px;font-weight:500;letter-spacing:1px}}
.body{{padding:40px}}
.body p{{color:#adb5bd;font-size:16px;margin-bottom:18px}}
.row{{display:flex;justify-content:space-between;align-items:center;padding:16px 0;border-bottom:1px solid #2c2e33}}
.row:last-child{{border-bottom:none}}
.lbl{{color:#495057;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1.5px}}
.val{{color:#ffffff;font-weight:700;font-size:16px;text-align:right}}
.btn{{display:inline-block;background:#ff6b6b;color:#ffffff!important;text-decoration:none;padding:18px 40px;border-radius:14px;font-weight:700;font-size:15px;margin:28px 0;box-shadow:0 10px 25px rgba(255,107,107,0.25);transition:all 0.2s}}
.info-box{{background:#0b0c0d;border-left:4px solid #ff6b6b;border-radius:0 14px 14px 0;padding:20px 24px;margin:28px 0;font-size:14px;color:#adb5bd;border:1px solid #2c2e33;border-left:4px solid #ff6b6b}}
.footer{{background:#1a1b1e;padding:36px 40px;text-align:center;color:#495057;font-size:12px;border-top:1px solid #2c2e33}}
.footer a{{color:#adb5bd;text-decoration:none;font-weight:600}}
</style></head><body>
<div class="outer"><div class="card">
<div class="hdr"><h1>{title}</h1><p>{subtitle}</p></div>
<div class="body">{body}</div>
<div class="footer">
  <p><strong>SkyMind Flights</strong> &nbsp;·&nbsp; AI-powered travel infrastructure</p>
  <p style="margin-top:10px"><a href="https://skymind.app">Website</a> &nbsp;·&nbsp; <a href="https://skymind.app/help">Help</a></p>
  <p style="margin-top:14px;font-size:11px;opacity:.4">© {year} SkyMind Technologies · India</p>
</div></div></div></body></html>"""

    # ── Templates ───────────────────────────────────────────────────
    def send_welcome(self, to_email: str, name: str) -> bool:
        body = f"""
<p>Hi <strong>{name}</strong>,</p>
<p>Welcome to SkyMind — the next generation of AI-powered travel infrastructure.</p>
<div class="info-box"><strong>Neural Forecasting</strong> — Predict price drops on 950+ global routes</div>
<div class="info-box"><strong>Manifest Security</strong> — Instant digital tickets and secure itineraries</div>
<div class="info-box"><strong>Priority Alerts</strong> — Real-time price tracking and route updates</div>
<p style="text-align:center;margin-top:32px">
  <a href="https://skymind.app/flights" class="btn">Initiate Flight Search</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#000000,#1a1b1e)", "", "Access Granted", "Welcome to the SkyMind ecosystem", body)
        return self.send(to_email, "Welcome to SkyMind — Smarter travel starts here", html, f"Welcome {name}! Explore skymind.app")

    def send_otp(self, to_email: str, otp: str, purpose: str = "verification") -> bool:
        body = f"""
<p>Your unique security code for <strong>{purpose}</strong>:</p>
<div style="text-align:center;margin:32px 0">
  <div style="display:inline-block;background:#0b0c0d;border:2px solid #2c2e33;border-radius:20px;padding:32px 48px">
    <div style="font-size:56px;font-weight:900;letter-spacing:14px;color:#ff6b6b;font-family:'Courier New',monospace">{otp}</div>
    <div style="color:#495057;font-size:12px;margin-top:12px;text-transform:uppercase;letter-spacing:2px">Valid for <strong>10 minutes</strong></div>
  </div>
</div>
<div class="info-box" style="border-color:#ff6b6b">SkyMind Security: Staff will never ask for this code. If you didn't request this, please secure your account.</div>"""
        html = self._wrap("linear-gradient(135deg,#1a1b1e,#0b0c0d)", "", "Secure Access", f"Protocol: {purpose.upper()}", body)
        return self.send(to_email, f"SkyMind Security Code: {otp}", html, f"Your SkyMind security code: {otp}. Valid 10 min.")

    def send_booking_confirmation(self, to_email: str, data: dict) -> bool:
        try:
            from services.pdf import generate_ticket_pdf
            pdf_bytes = generate_ticket_pdf(data)
            filename = f"SkyMind_Ticket_{data.get('booking_ref', 'BOOKING')}.pdf"
        except Exception as pdf_err:
            logger.error(f"Failed to generate PDF for attachment: {pdf_err}")
            pdf_bytes = None
            filename = None

        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>Your journey is confirmed. We've generated and attached your digital ticket manifest to this email for your convenience.</p>
<div style="background:#0b0c0d;border:1px solid #2c2e33;border-radius:18px;padding:28px;text-align:center;margin:28px 0">
  <div style="color:#495057;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:2px;margin-bottom:8px">Booking Reference</div>
  <div style="font-size:44px;font-weight:900;color:#ff6b6b;letter-spacing:6px;font-family:'Courier New',monospace;margin:8px 0">{data.get('booking_ref','------')}</div>
  <div style="color:#adb5bd;font-size:12px;opacity:.8;text-transform:uppercase;letter-spacing:1px">Manifest Secured & Verified</div>
</div>
<div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','---')} &rarr; {data.get('destination','---')}</span></div>
  <div class="row"><span class="lbl">Departure</span><span class="val">{data.get('departure_date','')}</span></div>
  <div class="row"><span class="lbl">Amount</span><span class="val" style="color:#ff6b6b;font-size:18px">{data.get('amount','')}</span></div>
</div>
<div class="info-box">Your digital ticket is attached as a PDF. Please present it at the airport check-in counter.</div>
<p style="text-align:center">
  <a href="https://skymind.app/dashboard" class="btn">View Booking Details</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#e03131,#ff6b6b)", "", "Ticket Secured", "Your flight is confirmed and ready for departure", body)
        
        attachments = [(filename, pdf_bytes)] if pdf_bytes else []
        return self.send(
            to_email, 
            f"Ticket Secured: {data.get('booking_ref')} | SkyMind", 
            html, 
            f"Booking {data.get('booking_ref')} confirmed. Amount: {data.get('amount')}",
            attachments=attachments
        )

    def send_price_alert(self, to_email: str, data: dict) -> bool:
        try:
            savings = float(data.get("target_price", 0)) - float(data.get("current_price", 0))
        except (TypeError, ValueError):
            savings = 0
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>The price for your tracked route has <strong style="color:#ff6b6b">dropped below your target</strong>.</p>
<div style="display:flex;gap:14px;margin:28px 0;flex-wrap:wrap">
  <div style="flex:1;min-width:120px;background:#0b0c0d;border:1px solid #2c2e33;border-radius:18px;padding:24px;text-align:center">
    <div style="font-size:11px;font-weight:800;color:#495057;text-transform:uppercase;letter-spacing:1px">Your Target</div>
    <div style="font-size:32px;font-weight:900;color:#adb5bd;margin:8px 0">₹{float(data.get('target_price',0)):,.0f}</div>
  </div>
  <div style="flex:1;min-width:120px;background:#1a1b1e;border:1px solid #ff6b6b;border-radius:18px;padding:24px;text-align:center">
    <div style="font-size:11px;font-weight:800;color:#ff6b6b;text-transform:uppercase;letter-spacing:1px">Current Price</div>
    <div style="font-size:32px;font-weight:900;color:#ffffff;margin:8px 0">₹{float(data.get('current_price',0)):,.0f}</div>
  </div>
</div>
<div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','')} &rarr; {data.get('destination','')}</span></div>
  <div class="row"><span class="lbl">Travel Date</span><span class="val">{data.get('departure_date','')}</span></div>
  <div class="row"><span class="lbl">Neural Savings</span><span class="val" style="color:#ff6b6b">₹{savings:,.0f}</span></div>
</div>
<div class="info-box" style="border-color:#ff6b6b"><strong>AI Recommendation:</strong> Price is currently at a 30-day low for this route. Act fast to secure this fare.</div>
<p style="text-align:center">
  <a href="https://skymind.app/flights?origin={data.get('origin')}&destination={data.get('destination')}&date={data.get('departure_date')}" class="btn">Book Now &rarr;</a>
</p>"""
        html = self._wrap("linear-gradient(135deg,#ff6b6b,#e03131)", "", "Price Alert", f"{data.get('origin','')} &rarr; {data.get('destination','')} Trend", body)
        return self.send(to_email, f"Price Alert: {data.get('origin')} &rarr; {data.get('destination')} now ₹{float(data.get('current_price',0)):,.0f}", html, f"Price dropped! Book now at skymind.app")

    def send_cancellation(self, to_email: str, data: dict) -> bool:
        body = f"""
<p>Hi <strong>{data.get('name','Traveller')}</strong>,</p>
<p>Your booking has been successfully cancelled as requested.</p>
<div>
  <div class="row"><span class="lbl">Booking Ref</span><span class="val">{data.get('booking_ref','')}</span></div>
  <div class="row"><span class="lbl">Route</span><span class="val">{data.get('origin','')} &rarr; {data.get('destination','')}</span></div>
  <div class="row"><span class="lbl">Refund Amount</span><span class="val" style="color:#ff6b6b;font-size:18px">₹{data.get('refund_amount','0')}</span></div>
  <div class="row"><span class="lbl">Refund Status</span><span class="val">Processing</span></div>
</div>
<div class="info-box">The refund will be credited to your original payment method within {data.get('refund_eta','5–7 days')}.</div>
<p style="text-align:center"><a href="https://skymind.app/flights" class="btn">Search New Flights</a></p>"""
        html = self._wrap("linear-gradient(135deg,#495057,#1a1b1e)", "", "Booking Cancelled", f"Refund Protocol Initiated", body)
        return self.send(to_email, f"Cancellation Confirmed: {data.get('booking_ref')} | SkyMind", html, "")


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
        return self.send(phone, f"*SkyMind OTP:* {otp}\nValid 10 min. Do NOT share.")

    def send_booking_confirmation(self, phone: str, d: dict) -> bool:
        return self.send(phone, f"*SkyMind Booking Confirmed!*\n\n*Ref:* {d.get('booking_ref','')}\n*Route:* {d.get('origin','')} → {d.get('destination','')}\n*Amount:* ₹{d.get('amount','')}\n\nBon voyage!")

    def send_price_alert(self, phone: str, d: dict) -> bool:
        try:
            savings = float(d.get("target_price", 0)) - float(d.get("current_price", 0))
        except (TypeError, ValueError):
            savings = 0
        return self.send(phone, f"*Price Alert — SkyMind*\n\n{d.get('origin','')} → {d.get('destination','')}\nCurrent: ₹{float(d.get('current_price',0)):,.0f}\nTarget: ₹{float(d.get('target_price',0)):,.0f}\n*Save: ₹{savings:,.0f}*\n\nBook now at skymind.app/flights")

    def send_cancellation(self, phone: str, d: dict) -> bool:
        return self.send(phone, f"*Booking Cancelled — SkyMind*\n\nRef: {d.get('booking_ref','')}\nRefund: ₹{d.get('refund_amount','0')} in {d.get('refund_eta','5-7 days')}")


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
