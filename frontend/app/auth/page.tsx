"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import { supabase } from "@/lib/supabase";

type AuthMode = "login" | "signup" | "otp";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode]       = useState<AuthMode>("login");
  const [email, setEmail]     = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone]     = useState("");
  const [otp, setOtp]         = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const [message, setMessage] = useState("");
  const [otpSent, setOtpSent] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) router.push("/dashboard");
    });
  }, [router]);

  const reset = () => { setError(""); setMessage(""); };

  const handleGoogleLogin = async () => {
    setLoading(true); reset();
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/dashboard` },
      });
      if (error) throw error;
    } catch (e: any) { setError(e.message || "Google login failed"); setLoading(false); }
  };

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault(); setLoading(true); reset();
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      router.push("/dashboard");
    } catch (e: any) { setError(e.message || "Login failed"); }
    setLoading(false);
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault(); setLoading(true); reset();
    try {
      const { error } = await supabase.auth.signUp({
        email, password,
        options: { data: { full_name: fullName } },
      });
      if (error) throw error;
      setMessage("Account created! Check your email to verify.");
      setMode("login");
    } catch (e: any) { setError(e.message || "Signup failed"); }
    setLoading(false);
  };

  const handleSendOTP = async () => {
    if (!phone) { setError("Enter your phone number"); return; }
    setLoading(true); reset();
    const fp = phone.startsWith("+") ? phone : `+91${phone.replace(/\D/g, "")}`;
    try {
      const { error } = await supabase.auth.signInWithOtp({ phone: fp });
      if (error) throw error;
      setOtpSent(true);
      setMessage(`OTP sent to ${fp}`);
    } catch (e: any) { setError(e.message || "Failed to send OTP"); }
    setLoading(false);
  };

  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault(); setLoading(true); reset();
    const fp = phone.startsWith("+") ? phone : `+91${phone.replace(/\D/g, "")}`;
    try {
      const { error } = await supabase.auth.verifyOtp({ phone: fp, token: otp, type: "sms" });
      if (error) throw error;
      router.push("/dashboard");
    } catch (e: any) { setError(e.message || "Invalid OTP"); }
    setLoading(false);
  };

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop: "60px", minHeight: "100vh", background: "var(--off)", display: "flex", alignItems: "center", justifyContent: "center", padding: "80px 20px" }}>
        <div style={{ width: "100%", maxWidth: "440px" }}>

          {/* Logo */}
          <div style={{ textAlign: "center", marginBottom: "32px" }}>
            <div style={{ fontFamily: "var(--fd)", fontSize: "3rem", letterSpacing: ".04em", color: "var(--black)", lineHeight: 1 }}>
              SKY<span style={{ color: "var(--red)" }}>MIND</span>
            </div>
            <div style={{ fontSize: ".9rem", color: "var(--grey4)", marginTop: "8px" }}>
              {mode === "login" ? "Sign in to your account" : mode === "signup" ? "Create your account" : "Sign in with phone"}
            </div>
          </div>

          <div style={{ background: "#fff", border: "1px solid var(--grey1)", padding: "32px" }}>
            {/* Tabs */}
            <div className="trip-tabs" style={{ marginBottom: "24px" }}>
              <button className={`trip-tab${mode === "login" ? " active" : ""}`} onClick={() => { setMode("login"); reset(); }}>Email Login</button>
              <button className={`trip-tab${mode === "otp" ? " active" : ""}`} onClick={() => { setMode("otp"); reset(); }}>Phone OTP</button>
              <button className={`trip-tab${mode === "signup" ? " active" : ""}`} onClick={() => { setMode("signup"); reset(); }}>Sign Up</button>
            </div>

            {/* Messages */}
            {error && <div style={{ padding: "12px 16px", background: "rgba(232,25,26,.08)", border: "1px solid var(--red)", color: "var(--red)", fontSize: ".82rem", marginBottom: "16px" }}>{error}</div>}
            {message && <div style={{ padding: "12px 16px", background: "#dcfce7", border: "1px solid #86efac", color: "#166534", fontSize: ".82rem", marginBottom: "16px" }}>{message}</div>}

            {/* Google */}
            <button type="button" onClick={handleGoogleLogin} disabled={loading} style={{ width: "100%", padding: "12px", display: "flex", alignItems: "center", justifyContent: "center", gap: "10px", background: "#fff", border: "1.5px solid #d8d6d2", cursor: "pointer", marginBottom: "20px", fontFamily: "var(--fb)", fontWeight: 600, fontSize: ".875rem", color: "var(--black)", transition: "border-color .15s" }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = "#131210")}
              onMouseLeave={e => (e.currentTarget.style.borderColor = "#d8d6d2")}
            >
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
              </svg>
              Continue with Google
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
              <div style={{ flex: 1, height: "1px", background: "var(--grey2)" }} />
              <span style={{ fontSize: ".72rem", color: "var(--grey3)", letterSpacing: ".06em", textTransform: "uppercase", fontFamily: "var(--fm)" }}>or</span>
              <div style={{ flex: 1, height: "1px", background: "var(--grey2)" }} />
            </div>

            {/* Email Login */}
            {mode === "login" && (
              <form onSubmit={handleEmailLogin}>
                <div style={{ marginBottom: "12px" }}><label className="field-label">Email</label><input type="email" className="inp" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" /></div>
                <div style={{ marginBottom: "20px" }}><label className="field-label">Password</label><input type="password" className="inp" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" /></div>
                <button type="submit" className="search-submit" disabled={loading} style={{ fontSize: ".9rem" }}>{loading ? "Signing in…" : "Sign In →"}</button>
              </form>
            )}

            {/* Phone OTP */}
            {mode === "otp" && (
              <div>
                <div style={{ marginBottom: "12px" }}>
                  <label className="field-label">Phone Number</label>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <input className="inp" value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91 98765 43210" style={{ flex: 1 }} disabled={otpSent} />
                    {!otpSent && <button type="button" onClick={handleSendOTP} disabled={loading} className="btn btn-primary" style={{ whiteSpace: "nowrap" }}>{loading ? "…" : "Send OTP"}</button>}
                  </div>
                </div>
                {otpSent && (
                  <form onSubmit={handleVerifyOTP}>
                    <div style={{ marginBottom: "20px" }}>
                      <label className="field-label">Enter OTP</label>
                      <input className="inp" value={otp} onChange={e => setOtp(e.target.value)} placeholder="6-digit OTP" maxLength={6} style={{ fontFamily: "var(--fm)", letterSpacing: ".2em", fontSize: "1.2rem", textAlign: "center" }} required autoFocus />
                    </div>
                    <button type="submit" className="search-submit" disabled={loading} style={{ fontSize: ".9rem" }}>{loading ? "Verifying…" : "Verify OTP →"}</button>
                    <button type="button" onClick={() => { setOtpSent(false); setOtp(""); setMessage(""); }} style={{ width: "100%", marginTop: "10px", background: "none", border: "none", color: "var(--grey4)", cursor: "pointer", fontSize: ".82rem" }}>Change number</button>
                  </form>
                )}
              </div>
            )}

            {/* Sign Up */}
            {mode === "signup" && (
              <form onSubmit={handleSignup}>
                <div style={{ marginBottom: "12px" }}><label className="field-label">Full Name</label><input className="inp" value={fullName} onChange={e => setFullName(e.target.value)} required placeholder="Rahul Sharma" /></div>
                <div style={{ marginBottom: "12px" }}><label className="field-label">Email</label><input type="email" className="inp" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" /></div>
                <div style={{ marginBottom: "20px" }}><label className="field-label">Password</label><input type="password" className="inp" value={password} onChange={e => setPassword(e.target.value)} required placeholder="Min. 8 characters" minLength={8} /></div>
                <button type="submit" className="search-submit" disabled={loading} style={{ fontSize: ".9rem" }}>{loading ? "Creating account…" : "Create Account →"}</button>
              </form>
            )}

            <p style={{ textAlign: "center", fontSize: ".78rem", color: "var(--grey3)", marginTop: "20px" }}>
              By continuing, you agree to SkyMind&apos;s Terms of Service and Privacy Policy.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
