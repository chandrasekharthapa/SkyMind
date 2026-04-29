"use client";

import React, { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";
import { Mail, Lock, User, Phone, ArrowRight, ShieldCheck, Zap, Globe } from "lucide-react";
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
      setMessage("Intelligence Verification Sent. Please check your email.");
    } catch (err: any) { setError(err.message); } finally { setLoading(false); }
  };

  const handleSendOTP = async () => {
    if (!phone) { setError("Intelligence Access requires a valid phone identifier."); return; }
    setLoading(true); reset();
    const fp = phone.startsWith("+") ? phone : `+91${phone.replace(/\D/g, "")}`;
    try {
      const { error } = await supabase.auth.signInWithOtp({ phone: fp });
      if (error) throw error;
      setOtpSent(true);
      setMessage(`Intelligence Protocol Active. OTP transmitted to ${fp}`);
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
          <div className="verify-badge">
            <Globe size={10} />
            SKYMIND GLOBAL NETWORK
          </div>
          <h1 className="auth-logo">SKY<em>MIND</em></h1>
          <p className="auth-subtitle">Proprietary Flight Intelligence</p>
        </div>

        <div className="auth-tabs">
          <button 
            className={`auth-tab ${mode === "login" ? "active" : ""}`} 
            onClick={() => { setMode("login"); reset(); }}
          >
            Sign In
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
            Register
          </button>
        </div>

        {error && (
          <div style={{ background: "var(--red-mist)", border: "1px solid rgba(224, 49, 49, 0.1)", color: "var(--red)", padding: "12px", borderRadius: "8px", fontSize: "12px", marginBottom: "20px", display: "flex", gap: "8px" }}>
            <Zap size={14} style={{ flexShrink: 0 }} />
            {error}
          </div>
        )}

        {message && (
          <div style={{ background: "rgba(43, 138, 62, 0.05)", border: "1px solid rgba(43, 138, 62, 0.1)", color: "var(--green)", padding: "12px", borderRadius: "8px", fontSize: "12px", marginBottom: "20px" }}>
            {message}
          </div>
        )}

        <button onClick={handleGoogleLogin} className="auth-btn-secondary">
          <img src="https://www.google.com/favicon.ico" width={16} alt="Google" />
          Continue with Google
        </button>

        <div className="auth-divider">SECURE PROTOCOL</div>

        {mode === "login" && (
          <form onSubmit={handleEmailLogin}>
            <div className="auth-input-group">
              <label className="auth-label">Email Address</label>
              <input 
                type="email" className="auth-inp" placeholder="operator@skymind.app" 
                value={email} onChange={(e) => setEmail(e.target.value)} required 
              />
            </div>
            <div className="auth-input-group">
              <label className="auth-label">Password</label>
              <input 
                type="password" className="auth-inp" placeholder="••••••••" 
                value={password} onChange={(e) => setPassword(e.target.value)} required 
              />
            </div>
            <button type="submit" disabled={loading} className="auth-btn-primary">
              {loading ? "Authenticating..." : "Sign In to Dashboard"}
              <ArrowRight size={18} />
            </button>
          </form>
        )}

        {mode === "signup" && (
          <form onSubmit={handleSignUp}>
            <div className="auth-input-group">
              <label className="auth-label">Full Name</label>
              <input 
                type="text" className="auth-inp" placeholder="Chandra Sekhar Thapa" 
                value={fullName} onChange={(e) => setFullName(e.target.value)} required 
              />
            </div>
            <div className="auth-input-group">
              <label className="auth-label">Email Address</label>
              <input 
                type="email" className="auth-inp" placeholder="operator@skymind.app" 
                value={email} onChange={(e) => setEmail(e.target.value)} required 
              />
            </div>
            <div className="auth-input-group">
              <label className="auth-label">Security Password</label>
              <input 
                type="password" className="auth-inp" placeholder="••••••••" 
                value={password} onChange={(e) => setPassword(e.target.value)} required 
              />
            </div>
            <button type="submit" disabled={loading} className="auth-btn-primary">
              {loading ? "Initializing..." : "Create Operator Account"}
              <ArrowRight size={18} />
            </button>
          </form>
        )}

        {mode === "otp" && (
          <div>
            {!otpSent ? (
              <>
                <div className="auth-input-group">
                  <label className="auth-label">Phone Number</label>
                  <input 
                    type="tel" className="auth-inp" placeholder="+91 XXXXX XXXXX" 
                    value={phone} onChange={(e) => setPhone(e.target.value)} 
                  />
                </div>
                <button onClick={handleSendOTP} disabled={loading} className="auth-btn-primary">
                  {loading ? "Sending..." : "Send Verification Code"}
                  <Phone size={18} />
                </button>
              </>
            ) : (
              <>
                <div className="auth-input-group">
                  <label className="auth-label">Verification Code</label>
                  <input 
                    type="text" className="auth-inp" placeholder="XXXXXX" 
                    value={otp} onChange={(e) => setOtp(e.target.value)} 
                  />
                </div>
                <button onClick={handleVerifyOTP} disabled={loading} className="auth-btn-primary">
                  {loading ? "Verifying..." : "Validate & Sign In"}
                  <ShieldCheck size={18} />
                </button>
              </>
            )}
          </div>
        )}

        <div className="auth-footer">
          By signing in, you agree to SkyMind's <br />
          <Link href="/terms">Terms of Service</Link> & <Link href="/privacy">Privacy Policy</Link>.
        </div>
      </div>
    </div>
  );
}
