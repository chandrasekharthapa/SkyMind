"use client";

import React, { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";
import { Phone, ArrowRight, ShieldCheck, AlertCircle } from "lucide-react";
import Link from "next/link";

export default function AuthPage() {
  const [mode, setMode] = useState<"login" | "signup" | "otp">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [otpSent, setOtpSent] = useState(false);
  const router = useRouter();

  const reset = () => { setError(null); setMessage(null); };

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); reset();
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      router.push("/dashboard");
    } catch (err: any) { setError(err.message); } finally { setLoading(false); }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); reset();
    try {
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: fullName } }
      });
      if (error) throw error;
      setMessage("Account created. Check your email for a confirmation link, then sign in.");
    } catch (err: any) { setError(err.message); } finally { setLoading(false); }
  };

  const handleSendOTP = async () => {
    if (!phone) { setError("Enter your phone number first."); return; }
    setLoading(true); reset();
    const fp = phone.startsWith("+") ? phone : `+91${phone.replace(/\D/g, "")}`;
    try {
      const { error } = await supabase.auth.signInWithOtp({ phone: fp });
      if (error) throw error;
      setOtpSent(true);
      setMessage(`We sent a 6-digit code to ${fp}.`);
    } catch (err: any) { setError(err.message); } finally { setLoading(false); }
  };

  const handleVerifyOTP = async () => {
    setLoading(true); reset();
    const fp = phone.startsWith("+") ? phone : `+91${phone.replace(/\D/g, "")}`;
    try {
      const { error } = await supabase.auth.verifyOtp({ phone: fp, token: otp, type: "sms" });
      if (error) throw error;
      router.push("/dashboard");
    } catch (err: any) { setError(err.message); } finally { setLoading(false); }
  };

  const handleGoogleLogin = async () => {
    try {
      await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: `${window.location.origin}/dashboard` } });
    } catch (err: any) { setError(err.message); }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <Link href="/" className="auth-logo" style={{ textDecoration: "none", display: "inline-block" }}>SKY<em>MIND</em></Link>
          <p className="auth-subtitle">
            {mode === "signup" ? "Create your account" : "Sign in to your account"}
          </p>
        </div>

        <div className="auth-tabs">
          <button 
            className={`auth-tab ${mode === "login" ? "active" : ""}`} 
            onClick={() => { setMode("login"); reset(); }}
          >
            Sign in
          </button>
          <button 
            className={`auth-tab ${mode === "otp" ? "active" : ""}`} 
            onClick={() => { setMode("otp"); reset(); }}
          >
            Phone OTP
          </button>
          <button 
            className={`auth-tab ${mode === "signup" ? "active" : ""}`} 
            onClick={() => { setMode("signup"); reset(); }}
          >
            Create account
          </button>
        </div>

        {error && (
          <div role="alert" style={{ background: "var(--red-mist)", border: "1px solid rgba(224, 49, 49, 0.1)", color: "var(--red)", padding: "12px", borderRadius: "8px", fontSize: "12px", marginBottom: "20px", display: "flex", gap: "8px" }}>
            <AlertCircle size={14} style={{ flexShrink: 0 }} />
            {error}
          </div>
        )}

        {message && (
          <div role="status" style={{ background: "rgba(43, 138, 62, 0.05)", border: "1px solid rgba(43, 138, 62, 0.1)", color: "var(--green)", padding: "12px", borderRadius: "8px", fontSize: "12px", marginBottom: "20px" }}>
            {message}
          </div>
        )}

        <button onClick={handleGoogleLogin} className="auth-btn-secondary">
          <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
            <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
            <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
            <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
          </svg>
          Continue with Google
        </button>

        <div className="auth-divider">OR</div>

        {mode === "login" && (
          <form onSubmit={handleEmailLogin}>
            <div className="auth-input-group">
              <label className="auth-label" htmlFor="login-email">Email</label>
              <input 
                id="login-email" type="email" autoComplete="email" className="auth-inp" placeholder="you@example.com" 
                value={email} onChange={(e) => setEmail(e.target.value)} required 
              />
            </div>
            <div className="auth-input-group">
              <label className="auth-label" htmlFor="login-password">Password</label>
              <input 
                id="login-password" type="password" autoComplete="current-password" className="auth-inp" placeholder="Your password" 
                value={password} onChange={(e) => setPassword(e.target.value)} required 
              />
            </div>
            <button type="submit" disabled={loading} className="auth-btn-primary">
              {loading ? "Signing in…" : "Sign in"}
              <ArrowRight size={18} />
            </button>
          </form>
        )}

        {mode === "signup" && (
          <form onSubmit={handleSignUp}>
            <div className="auth-input-group">
              <label className="auth-label" htmlFor="signup-name">Full name</label>
              <input 
                id="signup-name" type="text" autoComplete="name" className="auth-inp" placeholder="As on your ID" 
                value={fullName} onChange={(e) => setFullName(e.target.value)} required 
              />
            </div>
            <div className="auth-input-group">
              <label className="auth-label" htmlFor="signup-email">Email</label>
              <input 
                id="signup-email" type="email" autoComplete="email" className="auth-inp" placeholder="you@example.com" 
                value={email} onChange={(e) => setEmail(e.target.value)} required 
              />
            </div>
            <div className="auth-input-group">
              <label className="auth-label" htmlFor="signup-password">Password</label>
              <input 
                id="signup-password" type="password" autoComplete="new-password" minLength={6} className="auth-inp" placeholder="At least 6 characters" 
                value={password} onChange={(e) => setPassword(e.target.value)} required 
              />
            </div>
            <button type="submit" disabled={loading} className="auth-btn-primary">
              {loading ? "Creating account…" : "Create account"}
              <ArrowRight size={18} />
            </button>
          </form>
        )}

        {mode === "otp" && (
          <div>
            {!otpSent ? (
              <>
                <div className="auth-input-group">
                  <label className="auth-label" htmlFor="otp-phone">Phone number</label>
                  <input 
                    id="otp-phone" type="tel" autoComplete="tel" className="auth-inp" placeholder="98765 43210" 
                    value={phone} onChange={(e) => setPhone(e.target.value)} 
                  />
                </div>
                <button onClick={handleSendOTP} disabled={loading} className="auth-btn-primary">
                  {loading ? "Sending…" : "Send code"}
                  <Phone size={18} />
                </button>
              </>
            ) : (
              <>
                <div className="auth-input-group">
                  <label className="auth-label" htmlFor="otp-code">6-digit code</label>
                  <input 
                    id="otp-code" type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={6} className="auth-inp" placeholder="123456" 
                    value={otp} onChange={(e) => setOtp(e.target.value)} 
                  />
                </div>
                <button onClick={handleVerifyOTP} disabled={loading} className="auth-btn-primary">
                  {loading ? "Checking…" : "Verify and sign in"}
                  <ShieldCheck size={18} />
                </button>
                <button type="button" onClick={() => { setOtpSent(false); setOtp(""); reset(); }}
                  style={{ marginTop: 12, background: "none", border: "none", color: "var(--grey4)", fontSize: "13px", cursor: "pointer", textDecoration: "underline" }}>
                  Use a different number
                </button>
              </>
            )}
          </div>
        )}

        <div className="auth-footer">
          Your account is only used to save your bookings and price alerts.<br />
          <Link href="/">Back to SkyMind</Link>
        </div>
      </div>
    </div>
  );
}
