"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import { supabase, loadProfile, saveProfile, type Profile } from "@/lib/supabase";
import { useTheme, type ThemePreference } from "@/context/ThemeContext";

// Account settings: name, appearance, and sign-in. The service diagnostics
// that used to live at this URL are now at /system.

const EYEBROW: React.CSSProperties = {
  fontFamily: "var(--fm)", fontSize: "0.65rem", fontWeight: 600, letterSpacing: ".14em",
  textTransform: "uppercase", color: "var(--grey4)",
};
const CARD: React.CSSProperties = {
  background: "var(--white)", border: "1px solid var(--grey1)", borderRadius: 20,
  padding: "28px 28px 24px", boxShadow: "var(--shadow-sm)",
};
const CARD_TITLE: React.CSSProperties = {
  fontFamily: "var(--fd)", fontSize: "1.6rem", lineHeight: 1, margin: "0 0 6px",
  textTransform: "uppercase", color: "var(--black)",
};
const CARD_SUB: React.CSSProperties = { margin: "0 0 22px", color: "var(--grey4)", fontSize: "0.9rem", lineHeight: 1.5 };
const LABEL: React.CSSProperties = { display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--grey4)", marginBottom: 6 };
const READONLY: React.CSSProperties = {
  height: 48, display: "flex", alignItems: "center", padding: "0 16px", borderRadius: 12,
  background: "var(--off)", border: "1px solid var(--grey1)", color: "var(--grey4)", fontSize: "0.95rem",
};

function providerLabel(user: any): string {
  const p = user?.app_metadata?.provider;
  if (p === "google") return "Google";
  if (p === "phone" || (!user?.email && user?.phone)) return "Phone number (one-time code)";
  return "Email and password";
}

export default function SettingsPage() {
  const router = useRouter();
  const { preference, setPreference } = useTheme();
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [signingOut, setSigningOut] = useState<"" | "local" | "global">("");

  useEffect(() => {
    (async () => {
      const { data: { session } } = await supabase.auth.getSession();
      const u = session?.user ?? null;
      setUser(u);
      if (u) {
        const p = await loadProfile(u.id);
        setProfile(p);
        setName(p?.display_name || p?.full_name || u.user_metadata?.full_name || "");
      }
      setLoading(false);
    })();
  }, []);

  const savedName = profile?.display_name || profile?.full_name || user?.user_metadata?.full_name || "";
  const nameChanged = name.trim() !== savedName.trim();

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !name.trim() || !nameChanged) return;
    setSaving(true);
    setSaveMsg(null);
    const clean = name.trim().slice(0, 80);
    const { error } = await saveProfile(user.id, profile, {
      display_name: clean,
      full_name: profile?.full_name || clean,
      ...(profile ? {} : { email: user.email ?? null, phone: user.phone ?? null }),
    });
    if (error) {
      setSaveMsg({ ok: false, text: "Couldn't save your name. Please try again." });
      console.error("Profile save failed:", error);
    } else {
      setProfile(await loadProfile(user.id));
      setSaveMsg({ ok: true, text: "Saved." });
    }
    setSaving(false);
  };

  const signOut = async (scope: "local" | "global") => {
    setSigningOut(scope);
    await supabase.auth.signOut({ scope });
    router.push("/");
  };

  if (!loading && !user) {
    return (
      <div style={{ background: "var(--off)", minHeight: "100vh" }}>
        <NavBar />
        <div className="ui-wrap" style={{ paddingTop: 140, paddingBottom: 100 }}>
          <div style={{ ...CARD, maxWidth: 560, margin: "0 auto", textAlign: "center", padding: "56px 32px" }}>
            <div style={{ ...EYEBROW, marginBottom: 12 }}>Account</div>
            <h1 style={{ fontFamily: "var(--fd)", fontSize: "clamp(2.4rem, 6vw, 3.4rem)", lineHeight: 0.95, textTransform: "uppercase", marginBottom: 16 }}>
              Sign in to change your <em style={{ fontStyle: "normal", color: "var(--red)" }}>settings</em>
            </h1>
            <p style={{ color: "var(--grey4)", fontSize: "0.95rem", lineHeight: 1.6, maxWidth: 400, margin: "0 auto 28px" }}>
              Light or dark mode works without an account. Use the switch at the top of the page.
            </p>
            <Link href="/auth" className="ui-btn ui-btn-red">Sign in</Link>
          </div>
        </div>
      </div>
    );
  }

  const themeOptions: { value: ThemePreference; label: string; hint: string }[] = [
    { value: "light", label: "Light", hint: "Always light" },
    { value: "dark", label: "Dark", hint: "Always dark" },
    { value: "system", label: "Match device", hint: "Follows your phone or computer" },
  ];

  return (
    <div style={{ background: "var(--off)", minHeight: "100vh" }}>
      <NavBar />
      <div className="ui-wrap" style={{ paddingTop: 116, paddingBottom: 100 }}>
        <div style={{ maxWidth: 760 }}>
          <div style={{ ...EYEBROW, marginBottom: 12 }}>Your account</div>
          <h1 style={{ fontFamily: "var(--fd)", fontSize: "clamp(2.8rem, 6vw, 4.5rem)", lineHeight: 0.9, textTransform: "uppercase", margin: "0 0 36px" }}>
            Account <span style={{ color: "var(--red)" }}>settings.</span>
          </h1>

          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {[0, 1, 2].map(i => <div key={i} className="skel" style={{ height: 180, borderRadius: 20 }} />)}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

              {/* Profile */}
              <section style={CARD} aria-labelledby="profile-title">
                <h2 id="profile-title" style={CARD_TITLE}>Profile</h2>
                <p style={CARD_SUB}>The name shown on your account and bookings.</p>
                <form onSubmit={onSave}>
                  <div className="settings-grid">
                    <div>
                      <label htmlFor="settings-name" style={LABEL}>Name</label>
                      <input
                        id="settings-name"
                        className="ui-input"
                        value={name}
                        maxLength={80}
                        autoComplete="name"
                        onChange={e => { setName(e.target.value); setSaveMsg(null); }}
                        placeholder="Your name"
                      />
                    </div>
                    <div>
                      <span style={LABEL}>{user?.email ? "Email" : "Phone"}</span>
                      <div style={READONLY}>{user?.email || user?.phone || "Not set"}</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 20 }}>
                    <button type="submit" className="ui-btn ui-btn-red" disabled={!nameChanged || !name.trim() || saving}
                      style={{ opacity: !nameChanged || !name.trim() ? 0.5 : 1 }}>
                      {saving ? "Saving…" : "Save name"}
                    </button>
                    {saveMsg && (
                      <span role="status" style={{ fontSize: "0.875rem", fontWeight: 600, color: saveMsg.ok ? "var(--green)" : "var(--red)" }}>
                        {saveMsg.text}
                      </span>
                    )}
                  </div>
                  <p style={{ margin: "14px 0 0", fontSize: "0.8125rem", color: "var(--grey3)" }}>
                    Your {user?.email ? "email" : "phone number"} is how you sign in, so it can&apos;t be changed here.
                  </p>
                </form>
              </section>

              {/* Appearance */}
              <section style={CARD} aria-labelledby="appearance-title">
                <h2 id="appearance-title" style={CARD_TITLE}>Appearance</h2>
                <p style={CARD_SUB}>Saved in this browser.</p>
                <div role="radiogroup" aria-labelledby="appearance-title" className="settings-theme">
                  {themeOptions.map(o => {
                    const active = preference === o.value;
                    return (
                      <button
                        key={o.value}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        onClick={() => setPreference(o.value)}
                        className={`settings-theme-opt${active ? " active" : ""}`}
                      >
                        <span className="settings-theme-label">{o.label}</span>
                        <span className="settings-theme-hint">{o.hint}</span>
                      </button>
                    );
                  })}
                </div>
              </section>

              {/* Sign-in */}
              <section style={CARD} aria-labelledby="signin-title">
                <h2 id="signin-title" style={CARD_TITLE}>Sign-in</h2>
                <p style={CARD_SUB}>
                  You sign in with: <strong style={{ color: "var(--black)" }}>{providerLabel(user)}</strong>
                  {user?.created_at && (
                    <> · Member since {new Date(user.created_at).toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</>
                  )}
                </p>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <button type="button" className="ui-btn ui-btn-white" onClick={() => signOut("local")} disabled={!!signingOut}>
                    {signingOut === "local" ? "Signing out…" : "Sign out"}
                  </button>
                  <button type="button" className="ui-btn ui-btn-white" onClick={() => signOut("global")} disabled={!!signingOut}>
                    {signingOut === "global" ? "Signing out…" : "Sign out on all devices"}
                  </button>
                </div>
              </section>

              <p style={{ fontSize: "0.875rem", color: "var(--grey4)", margin: "4px 0 0" }}>
                Bookings and price alerts are under <Link href="/dashboard" style={{ color: "var(--red)", fontWeight: 600 }}>Your trips</Link>.
                {" "}Is something not working? See the <Link href="/system" style={{ color: "var(--red)", fontWeight: 600 }}>service status</Link>.
              </p>
            </div>
          )}
        </div>
      </div>

      <style jsx global>{`
        .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .settings-theme { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
        .settings-theme-opt {
          text-align: left; padding: 14px 16px; border-radius: 12px; cursor: pointer;
          background: var(--white); border: 1px solid var(--grey2); color: var(--black);
          display: flex; flex-direction: column; gap: 4px; transition: border-color .15s;
        }
        .settings-theme-opt:hover { border-color: var(--grey3); }
        .settings-theme-opt.active { border: 2px solid var(--red); padding: 13px 15px; }
        .settings-theme-label { font-weight: 700; font-size: 0.95rem; }
        .settings-theme-hint { font-size: 0.8125rem; color: var(--grey4); }
        @media (max-width: 640px) {
          .settings-grid, .settings-theme { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}
