"use client";

import React, { useState, useEffect } from "react";
import NavBar from "@/components/layout/NavBar";
import {
  healthCheck, getModelPerformance, getSystemInfo,
  type HealthReport, type SystemInfo, type ModelMetrics
} from "@/lib/api";

// Absence renders as absence. Every figure on this page used to fall back
// through `|| 0`, so a backend publishing no validation metrics at all was
// drawn as "₹0" mean absolute error and "R² 0.0000" — which an observer reads
// as a measurement of a very bad model, not as the absence of a measurement.
const NOT_MEASURED = (
  <span style={{ color: "var(--grey3)", fontWeight: 400, fontStyle: "italic" }}>
    not measured
  </span>
);

function Row({ label, value, color, mono, last }: {
  label: string;
  value: React.ReactNode;
  color?: string;
  mono?: boolean;
  last?: boolean;
}) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", gap: 16,
      borderBottom: last ? "none" : "1px solid var(--grey1)",
      paddingBottom: last ? 0 : 8
    }}>
      <span style={{ color: "var(--grey3)", flexShrink: 0 }}>{label}</span>
      <span style={{
        fontWeight: color ? 700 : 400,
        color: color ?? "var(--grey4)",
        fontFamily: mono ? "var(--fm)" : "inherit",
        textAlign: "right"
      }}>
        {value}
      </span>
    </div>
  );
}

const CARD: React.CSSProperties = { padding: 28, background: "var(--white)" };
const CARD_H: React.CSSProperties = {
  fontFamily: "var(--fd)", fontSize: "1.3rem", marginTop: 0,
  marginBottom: 20, textTransform: "uppercase"
};
const ROWS: React.CSSProperties = {
  display: "flex", flexDirection: "column", gap: 16,
  fontSize: "0.85rem", color: "var(--grey4)"
};

// The sentinels a failed fetch collapses to. `status: "offline"` is a
// client-side value the backend never sends, which is what lets the connection
// row distinguish "unreachable" from the backend's own "degraded".
const UNREACHABLE: HealthReport = {
  status: "offline", model: "unknown", model_load_error: null,
  refused_artifacts: [], degraded_capabilities: [], data_source: "unknown",
  time: "", version: ""
};

const NO_INFO: SystemInfo = {
  model_version: null, feature_set_version: null, validator_version: null,
  training_timestamp: null, dataset_size: null, validation_status: "UNKNOWN",
  last_validation_timestamp: null, trained: false, model_load_error: null,
  refused_artifacts: [], unavailable: ["/system/info was unreachable"]
};

const NO_METRICS: ModelMetrics = {
  mae: null, rmse: null, r2: null, mape: null, training_samples: null,
  unavailable: ["/system/model/metadata was unreachable"]
};

const rupees = (v: number | null) =>
  v == null ? NOT_MEASURED : `₹${Math.round(v).toLocaleString("en-IN")}`;

// "trained_model" | "none" | "unknown" — what `/health` now reports in place of
// the old "SKYMIND_INTELLIGENCE", which named the product rather than a source.
const SOURCE_LABEL: Record<string, string> = {
  trained_model: "TRAINED MODEL",
  none: "NO MODEL SERVING",
  unknown: "UNKNOWN"
};

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthReport>(UNREACHABLE);
  const [info, setInfo] = useState<SystemInfo>(NO_INFO);
  const [perf, setPerf] = useState<ModelMetrics>(NO_METRICS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      const [h, i, p] = await Promise.all([
        healthCheck().catch(() => UNREACHABLE),
        getSystemInfo().catch(() => NO_INFO),
        getModelPerformance().then(r => r.metrics).catch(() => NO_METRICS)
      ]);
      if (!alive) return;
      setHealth(h);
      setInfo(i);
      setPerf(p);
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  const reachable = health.status !== "offline";
  const conn = !reachable
    ? { text: "OFFLINE", color: "var(--red)" }
    : health.status === "ok"
      ? { text: "ONLINE", color: "var(--green)" }
      // The process is up and answering; the model is not serving. Rendering
      // this as "OFFLINE" (which `status === "ok" ? … : …` did) mislabels a
      // backend that is still serving search, airports and the chatbot.
      : { text: "ONLINE / DEGRADED", color: "#ca8a04" };

  // "failed" and "lazy" were one bucket, both drawn as "LAZY / UNTRAINED".
  // They call for opposite responses: lazy means the model loads on first use,
  // failed means go and look at the artifacts.
  const inference =
    health.model === "ready" ? { text: "ACTIVE / LOADED", color: "var(--green)" }
    : health.model === "failed" ? { text: "LOAD FAILED", color: "var(--red)" }
    : health.model === "lazy" ? { text: "NOT LOADED YET", color: "#ca8a04" }
    : { text: "UNKNOWN", color: "var(--grey3)" };

  const refused = health.refused_artifacts.length
    ? health.refused_artifacts
    : info.refused_artifacts;
  const loadError = health.model_load_error ?? info.model_load_error;

  return (
    <>
      <NavBar />
      <div style={{ background: "var(--white)", minHeight: "100vh", paddingTop: "120px", paddingBottom: "100px" }}>
        <div className="ui-wrap">

          <div style={{ marginBottom: 40, borderBottom: "1px solid var(--grey1)", paddingBottom: 24 }}>
            <div style={{ fontFamily: "var(--fm)", fontSize: "10px", fontWeight: 700, color: "var(--red)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
              SkyMind Neural Hub Specs
            </div>
            <h1 style={{ fontFamily: "var(--fd)", fontSize: "clamp(2rem, 5vw, 4rem)", margin: 0, textTransform: "uppercase", letterSpacing: "-0.02em" }}>
              System <span style={{ color: "var(--red)" }}>Information.</span>
            </h1>
          </div>

          {loading ? (
            <div className="ui-card" style={{ padding: "80px 24px", textAlign: "center" }}>
              <div className="status-dot pulse" style={{ width: 16, height: 16, margin: "0 auto 24px" }} />
              <div style={{ fontFamily: "var(--fd)", fontSize: "1.5rem" }}>QUERYING NEURAL DIAGNOSTICS...</div>
            </div>
          ) : (
            <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 32 }}>

              <div className="ui-card" style={CARD}>
                <h3 style={CARD_H}>Backend Server status</h3>
                <div style={ROWS}>
                  <Row label="Connection Status" value={conn.text} color={conn.color} />
                  <Row label="Inference State" value={inference.text} color={inference.color} />
                  <Row
                    label="Degraded Capabilities"
                    value={health.degraded_capabilities.length
                      ? health.degraded_capabilities.join(", ")
                      : (reachable ? "none" : NOT_MEASURED)}
                    mono
                  />
                  <Row label="API Engine Version" value={health.version || NOT_MEASURED} mono />
                  <Row
                    label="Response Time Stamp"
                    value={health.time ? new Date(health.time).toLocaleString("en-IN") : NOT_MEASURED}
                    mono
                    last
                  />
                </div>
              </div>

              <div className="ui-card" style={CARD}>
                <h3 style={CARD_H}>ML Estimator Performance</h3>
                <div style={ROWS}>
                  <Row label="Mean Absolute Error (MAE)" value={rupees(perf.mae)} mono />
                  <Row label="Root Mean Squared Error (RMSE)" value={rupees(perf.rmse)} mono />
                  <Row
                    label="Reliability Index (R²)"
                    value={perf.r2 == null ? NOT_MEASURED : perf.r2.toFixed(4)}
                    color={perf.r2 == null ? undefined : "var(--red)"}
                    mono
                  />
                  <Row
                    label="Training Samples size"
                    value={perf.training_samples == null
                      ? NOT_MEASURED
                      : `${perf.training_samples.toLocaleString("en-IN")} rows`}
                    mono
                  />
                  <Row
                    label="Last Trained"
                    value={perf.training_date
                      ? new Date(perf.training_date).toLocaleString("en-IN")
                      : NOT_MEASURED}
                    mono
                    last
                  />
                </div>
              </div>

              <div className="ui-card" style={CARD}>
                <h3 style={CARD_H}>Policy Enforcement</h3>
                <div style={ROWS}>
                  {/* Was two green "ENFORCED ✓" ticks, a typed "feature_set_v1"
                      and "LIVE_SEARCH MCP STREAM" — four literals that rendered
                      identically on a deployment with no model, no validation
                      report and no data. Each row now shows what was measured. */}
                  <Row
                    label="Leak audit on model load"
                    value={refused.length
                      ? `${refused.length} ARTIFACT(S) REFUSED`
                      : info.trained ? "LOADED, NONE REFUSED" : "NO ARTIFACT LOADED"}
                    color={refused.length ? "var(--red)" : info.trained ? "var(--green)" : "#ca8a04"}
                  />
                  <Row
                    label="Pipeline validation status"
                    value={info.validation_status}
                    color={info.validation_status === "PASS" ? "var(--green)" : "#ca8a04"}
                  />
                  <Row
                    label="Last validated"
                    value={info.last_validation_timestamp
                      ? new Date(info.last_validation_timestamp).toLocaleString("en-IN")
                      : NOT_MEASURED}
                    mono
                  />
                  <Row
                    label="Active Feature Set version"
                    value={info.feature_set_version ?? NOT_MEASURED}
                    mono
                  />
                  <Row
                    label="Data Source Origin"
                    value={SOURCE_LABEL[health.data_source] ?? health.data_source}
                    color={health.data_source === "trained_model" ? "var(--green)" : "#ca8a04"}
                    last
                  />
                </div>
              </div>

            </div>

            {(loadError || refused.length > 0 || info.unavailable.length > 0 || perf.unavailable.length > 0) && (
              <div className="ui-card" style={{ ...CARD, marginTop: 32, borderLeft: "3px solid var(--red)" }}>
                <h3 style={CARD_H}>Why fields above are missing</h3>
                <div style={{ ...ROWS, gap: 10 }}>
                  {loadError && (
                    <div style={{ fontFamily: "var(--fm)", fontSize: "12px", color: "var(--red)" }}>
                      model load error: {loadError}
                    </div>
                  )}
                  {refused.map((r, idx) => (
                    <div key={`r${idx}`} style={{ fontFamily: "var(--fm)", fontSize: "12px" }}>
                      refused artifact: {r}
                    </div>
                  ))}
                  {[...info.unavailable, ...perf.unavailable].map((u, idx) => (
                    <div key={`u${idx}`} style={{ fontFamily: "var(--fm)", fontSize: "12px", color: "var(--grey3)" }}>
                      {u}
                    </div>
                  ))}
                </div>
              </div>
            )}
            </>
          )}

        </div>
      </div>
    </>
  );
}
