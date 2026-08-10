"use client";

import type { ChangeEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Free-tier model calls are genuinely slow (docs: 90-150s/SKU). Below this we
// say nothing; above it we tell the user why, so silence doesn't read as hung.
const SLOW_THRESHOLD_MS = 12_000;

type Evidence = {
  source_url: string;
  source_type: string;
  raw_value: string;
  quote: string;
};

type Attribute = {
  name: string;
  value: string;
  unit: string;
  confidence: number;
  status: string;
  evidence: Evidence[];
  conflicting_values: Evidence[];
  human_reviewed: boolean;
};

type ProductRecord = {
  id: string;
  input: { mpn: string; brand: string; description: string };
  category: string;
  category_confidence: number;
  seo_title: string;
  short_description: string;
  long_description: string;
  attributes: Attribute[];
  search_synonyms: string[];
  certifications: string[];
  equivalent_mpns: string[];
  sources: { url: string; title: string; source_type: string }[];
  status: string;
  cost_usd: number;
  duration_s: number;
};

type AgentEvent = { agent: string; step: string; ts: string };

type RecordSummary = {
  id: string;
  mpn: string;
  brand: string;
  category: string;
  status: string;
  seo_title: string;
  attribute_count: number;
  conflict_count: number;
  duration_s: number;
  cost_usd: number;
};

type Toast = { id: number; kind: "success" | "error" | "info"; text: string };

const AGENT_COLORS: Record<string, string> = {
  scout: "text-sky-400",
  classifier: "text-violet-400",
  extractor: "text-amber-400",
  validator: "text-emerald-400",
  composer: "text-pink-400",
  orchestrator: "text-zinc-400",
};

const STATUS_BADGE: Record<string, string> = {
  verified: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  "single-source": "bg-amber-500/15 text-amber-400 border-amber-500/30",
  conflict: "bg-red-500/15 text-red-400 border-red-500/30",
  generated: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

function statusBadgeClass(status: string) {
  if (status === "auto-approved" || status === "approved") return STATUS_BADGE.verified;
  if (status === "failed") return STATUS_BADGE.conflict;
  return STATUS_BADGE["single-source"];
}

// ---------------------------------------------------------------------------
// Small shared bits: connectivity, toasts, skeletons, retry-able fetch
// ---------------------------------------------------------------------------

function useOnlineStatus() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    setOnline(navigator.onLine);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  const dismiss = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));
  return { toasts, push, dismiss };
}

function ToastStack({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: number) => void }) {
  if (toasts.length === 0) return null;
  const style: Record<Toast["kind"], string> = {
    success: "border-emerald-500/40 bg-emerald-950/90 text-emerald-200",
    error: "border-red-500/40 bg-red-950/90 text-red-200",
    info: "border-zinc-700 bg-zinc-900/95 text-zinc-200",
  };
  return (
    <div
      className="fixed bottom-3 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 w-[calc(100%-1.5rem)] max-w-sm sm:left-auto sm:right-4 sm:translate-x-0 sm:bottom-4"
      role="status"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={`text-sm px-3.5 py-2.5 rounded-lg border shadow-lg backdrop-blur cursor-pointer motion-safe:animate-[toast-in_0.2s_ease-out] ${style[t.kind]}`}
        >
          {t.text}
        </div>
      ))}
      <style>{`@keyframes toast-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}

function OfflineBanner({ online }: { online: boolean }) {
  if (online) return null;
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-950/40 text-amber-200 text-sm px-4 py-2.5 flex items-center gap-2">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 motion-safe:animate-pulse" />
      No internet connection — actions will fail until it&apos;s back.
    </div>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-red-500/30 bg-red-950/30 text-red-200 text-sm px-4 py-2.5 flex items-center justify-between gap-3 flex-wrap">
      <span>{message}</span>
      <button
        onClick={onRetry}
        className="shrink-0 px-2.5 py-1 rounded border border-red-500/40 hover:bg-red-500/10 text-xs font-medium min-h-[32px]"
      >
        Retry
      </button>
    </div>
  );
}

function StatSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 sm:gap-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="bg-zinc-900 border border-zinc-800 rounded-lg py-3 motion-safe:animate-pulse"
        >
          <div className="h-5 w-12 bg-zinc-800 rounded mx-auto" />
          <div className="h-3 w-16 bg-zinc-800 rounded mx-auto mt-2" />
        </div>
      ))}
    </div>
  );
}

function RowSkeleton() {
  return (
    <div className="motion-safe:animate-pulse space-y-2 p-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-8 bg-zinc-800/60 rounded" />
      ))}
    </div>
  );
}

/** Wraps fetch with a timeout + a distinct "still going" flag so slow free-tier
 * requests are visibly explained instead of just looking frozen. */
async function fetchSlow(
  input: string,
  init: RequestInit | undefined,
  onSlow: () => void,
  timeoutMs = 30_000,
): Promise<Response> {
  const slowTimer = window.setTimeout(onSlow, SLOW_THRESHOLD_MS);
  const controller = new AbortController();
  const abortTimer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(input, { ...init, signal: controller.signal });
    return res;
  } finally {
    window.clearTimeout(slowTimer);
    window.clearTimeout(abortTimer);
  }
}

// ---------------------------------------------------------------------------

function ConfidenceBar({ value }: { value: number }) {
  const color =
    value >= 0.8 ? "bg-emerald-500" : value >= 0.5 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 w-20 sm:w-28 shrink-0">
      <div className="h-1.5 flex-1 rounded bg-zinc-800">
        <div
          className={`h-1.5 rounded ${color} transition-[width] duration-500`}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-zinc-400 w-8 shrink-0">
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

function AttributeRow({
  attr,
  recordId,
  onUpdated,
  notify,
}: {
  attr: Attribute;
  recordId: string;
  onUpdated: (r: ProductRecord) => void;
  notify: (kind: Toast["kind"], text: string) => void;
}) {
  const [open, setOpen] = useState(attr.status === "conflict");
  const [busy, setBusy] = useState(false);

  const review = async (action: string, newValue = "", newUnit = "") => {
    setBusy(true);
    try {
      const res = await fetchSlow(
        `${API}/api/records/${recordId}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            attribute_name: attr.name,
            action,
            new_value: newValue,
            new_unit: newUnit,
          }),
        },
        () => {},
      );
      if (res.ok) {
        onUpdated(await res.json());
        notify(
          "success",
          action === "approve"
            ? `${attr.name} approved`
            : action === "reject"
              ? `${attr.name} rejected`
              : `${attr.name} updated`,
        );
      } else {
        notify("error", `Couldn't update ${attr.name} — try again.`);
      }
    } catch {
      notify("error", `Network error updating ${attr.name}.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-zinc-800 last:border-0">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex flex-wrap sm:flex-nowrap items-center gap-x-3 gap-y-1.5 py-3 px-3 min-h-[44px] hover:bg-zinc-900/60 active:bg-zinc-900 text-left transition-colors"
      >
        <span className="font-mono text-sm text-zinc-300 w-full sm:w-44 sm:shrink-0 truncate order-1">
          {attr.name}
        </span>
        <span className="text-sm text-zinc-100 flex-1 order-3 sm:order-2 min-w-0 truncate">
          {attr.value} {attr.unit}
        </span>
        <span
          className={`text-[11px] px-2 py-0.5 rounded-full border shrink-0 order-2 sm:order-3 ${STATUS_BADGE[attr.status] ?? STATUS_BADGE.generated}`}
        >
          {attr.human_reviewed ? "human-verified" : attr.status}
        </span>
        <span className="order-4 shrink-0">
          <ConfidenceBar value={attr.confidence} />
        </span>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2">
          {attr.evidence.map((ev, i) => (
            <div key={i} className="text-xs bg-zinc-900 rounded p-2 border border-zinc-800">
              <div className="flex justify-between gap-2 flex-wrap">
                <a
                  href={ev.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sky-400 hover:underline break-all"
                >
                  {ev.source_url}
                </a>
                <span className="text-zinc-500 shrink-0">{ev.source_type}</span>
              </div>
              {ev.quote && (
                <p className="mt-1 text-zinc-400 italic">&ldquo;{ev.quote}&rdquo;</p>
              )}
            </div>
          ))}

          {attr.conflicting_values.length > 0 && (
            <div className="text-xs bg-red-950/40 border border-red-500/30 rounded p-2 space-y-1.5">
              <p className="text-red-400 font-medium">
                Conflicting values from other sources:
              </p>
              {attr.conflicting_values.map((ev, i) => (
                <div key={i} className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-zinc-200">
                    {ev.raw_value}{" "}
                    <span className="text-zinc-500">({ev.source_type})</span>
                  </span>
                  <button
                    disabled={busy}
                    onClick={() => review("edit", ev.raw_value, attr.unit)}
                    className="text-sky-400 hover:underline disabled:opacity-40 min-h-[32px] px-1"
                  >
                    use this value
                  </button>
                </div>
              ))}
            </div>
          )}

          {!attr.human_reviewed && (
            <div className="flex gap-2 text-xs">
              <button
                disabled={busy}
                onClick={() => review("approve")}
                className="px-3 py-1.5 rounded bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600/30 disabled:opacity-40 min-h-[36px] transition-colors"
              >
                {busy ? "…" : "Approve"}
              </button>
              <button
                disabled={busy}
                onClick={() => review("reject")}
                className="px-3 py-1.5 rounded bg-red-600/20 text-red-400 border border-red-500/30 hover:bg-red-600/30 disabled:opacity-40 min-h-[36px] transition-colors"
              >
                {busy ? "…" : "Reject"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [mpn, setMpn] = useState("HOM230CP");
  const [brand, setBrand] = useState("Square D");
  const [desc, setDesc] = useState("30A 2 pole breaker");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [record, setRecord] = useState<ProductRecord | null>(null);
  const [running, setRunning] = useState(false);
  const [runSlow, setRunSlow] = useState(false);
  const [enrichError, setEnrichError] = useState("");

  const [stats, setStats] = useState<Record<string, number | boolean> | null>(null);
  const [catalog, setCatalog] = useState<RecordSummary[]>([]);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState("");

  const [uploading, setUploading] = useState(false);
  const [batchNote, setBatchNote] = useState<{ kind: "info" | "error"; text: string } | null>(null);

  const [recordLoading, setRecordLoading] = useState(false);
  const [recordError, setRecordError] = useState("");
  const [pendingRecordId, setPendingRecordId] = useState<string | null>(null);

  const online = useOnlineStatus();
  const { toasts, push, dismiss } = useToasts();
  const logRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const refreshStats = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([
        fetch(`${API}/api/stats`),
        fetch(`${API}/api/records`),
      ]);
      if (s.ok) setStats(await s.json());
      if (r.ok) setCatalog(await r.json());
      if (!s.ok && !r.ok) throw new Error("both requests failed");
      setStatsError("");
    } catch {
      setStatsError("Couldn't reach the server. It may be waking up (free-tier hosting sleeps when idle) — retry in a few seconds.");
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStats();
    // The catalog view is a live picture of a running batch.
    const t = setInterval(refreshStats, 5000);
    return () => clearInterval(t);
  }, [refreshStats]);

  useEffect(() => () => esRef.current?.close(), []);

  const onUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setBatchNote({ kind: "error", text: "That doesn't look like a CSV file." });
      e.target.value = "";
      return;
    }
    setUploading(true);
    setBatchNote(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetchSlow(`${API}/api/batch`, { method: "POST", body }, () => {});
      const data = await res.json();
      if (res.ok) {
        setBatchNote({
          kind: "info",
          text: `Enriching ${data.count} SKUs — the catalog below fills in as each finishes.`,
        });
        push("success", `Batch started: ${data.count} SKUs`);
      } else {
        setBatchNote({ kind: "error", text: `Upload failed: ${data.detail ?? res.statusText}` });
      }
    } catch (err) {
      setBatchNote({
        kind: "error",
        text: err instanceof DOMException && err.name === "AbortError"
          ? "Upload timed out — check your connection and try again."
          : `Upload failed: ${String(err)}`,
      });
    } finally {
      setUploading(false);
      e.target.value = "";
      refreshStats();
    }
  };

  const openRecord = async (id: string) => {
    setRecordLoading(true);
    setRecordError("");
    setPendingRecordId(id);
    try {
      const r = await fetchSlow(`${API}/api/records/${id}`, undefined, () => {});
      if (r.ok) {
        setRecord(await r.json());
        setEvents([]);
      } else {
        setRecordError("Couldn't load that record.");
      }
    } catch {
      setRecordError("Network error loading that record.");
    } finally {
      setRecordLoading(false);
      setPendingRecordId(null);
    }
  };

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [events]);

  const enrich = async () => {
    setRunning(true);
    setRunSlow(false);
    setEnrichError("");
    setEvents([]);
    setRecord(null);
    esRef.current?.close();

    let record_id: string;
    try {
      const res = await fetchSlow(
        `${API}/api/enrich`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mpn, brand, description: desc }),
        },
        () => setRunSlow(true),
        20_000,
      );
      if (!res.ok) throw new Error(`server returned ${res.status}`);
      ({ record_id } = await res.json());
    } catch (err) {
      setRunning(false);
      setEnrichError(
        err instanceof DOMException && err.name === "AbortError"
          ? "Server took too long to respond. It may be waking up — try again."
          : "Couldn't start enrichment — check your connection and try again.",
      );
      return;
    }

    const es = new EventSource(`${API}/api/events/${record_id}`);
    esRef.current = es;
    let finished = false;
    const slowTimer = window.setTimeout(() => setRunSlow(true), SLOW_THRESHOLD_MS);

    es.onmessage = (e) => {
      setRunSlow(false);
      window.clearTimeout(slowTimer);
      const ev = JSON.parse(e.data);
      setEvents((prev) => [...prev, ev]);
    };
    es.addEventListener("done", async () => {
      finished = true;
      window.clearTimeout(slowTimer);
      es.close();
      try {
        const r = await fetch(`${API}/api/records/${record_id}`);
        if (r.ok) {
          setRecord(await r.json());
          push("success", "Enrichment complete");
        }
      } catch {
        setEnrichError("Finished, but couldn't load the result. Refresh and check the catalog.");
      }
      setRunning(false);
      refreshStats();
    });
    es.onerror = () => {
      window.clearTimeout(slowTimer);
      es.close();
      setRunning(false);
      if (!finished) {
        setEnrichError("Connection to the server was lost mid-run. Check the catalog below — it may have finished anyway.");
      }
    };
  };

  const statCards: [string, string][] = stats
    ? [
        ["Records", String(stats.completed)],
        ["Auto-approved", `${Math.round((stats.auto_approval_rate as number) * 100)}%`],
        ["Avg cost/SKU", `$${stats.avg_cost_usd}`],
        ["Avg time", `${stats.avg_duration_s}s`],
        ["Flagged attrs", String(stats.attributes_flagged_for_review)],
      ]
    : [];

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 p-3 sm:p-6 font-sans">
      <div className="max-w-6xl mx-auto space-y-4 sm:space-y-6">
        <header className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">
            SKU<span className="text-sky-400">Forge</span>
          </h1>
          <p className="text-xs sm:text-sm text-zinc-500">
            minimal input → commerce-ready product intelligence, with proof
          </p>
        </header>

        <OfflineBanner online={online} />

        {statsLoading ? (
          <StatSkeleton />
        ) : statsError ? (
          <ErrorBanner message={statsError} onRetry={refreshStats} />
        ) : stats ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 sm:gap-3 text-center">
            {statCards.map(([label, value]) => (
              <div
                key={label}
                className="bg-zinc-900 border border-zinc-800 rounded-lg py-3"
              >
                <div className="text-base sm:text-lg font-semibold tabular-nums">{value}</div>
                <div className="text-[11px] sm:text-xs text-zinc-500">{label}</div>
              </div>
            ))}
          </div>
        ) : null}

        <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 sm:p-4">
          <div className="flex flex-col sm:flex-row gap-2.5 sm:gap-3">
            <input
              value={mpn}
              onChange={(e) => setMpn(e.target.value)}
              placeholder="MPN"
              className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2.5 sm:py-2 text-sm w-full sm:w-40 min-h-[44px]"
            />
            <input
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="Brand"
              className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2.5 sm:py-2 text-sm w-full sm:w-40 min-h-[44px]"
            />
            <input
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="One-line description"
              onKeyDown={(e) => e.key === "Enter" && !running && mpn && brand && enrich()}
              className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2.5 sm:py-2 text-sm flex-1 min-h-[44px]"
            />
            <button
              onClick={enrich}
              disabled={running || !mpn || !brand || !online}
              className="px-5 py-2.5 sm:py-2 rounded bg-sky-600 hover:bg-sky-500 active:bg-sky-700 disabled:opacity-40 text-sm font-medium min-h-[44px] transition-colors shrink-0"
            >
              {running ? (
                <span className="inline-flex items-center gap-2">
                  <span className="w-3.5 h-3.5 rounded-full border-2 border-white/30 border-t-white motion-safe:animate-spin" />
                  Enriching…
                </span>
              ) : (
                "Enrich"
              )}
            </button>
          </div>

          {running && runSlow && (
            <p className="text-xs text-amber-400/90 mt-2 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 motion-safe:animate-pulse" />
              Still working — free-tier models can take 60–150s per SKU.
            </p>
          )}
          {enrichError && (
            <div className="mt-2.5">
              <ErrorBanner message={enrichError} onRetry={enrich} />
            </div>
          )}

          <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 sm:gap-3 mt-3 pt-3 border-t border-zinc-800">
            <span className="text-xs text-zinc-500">
              Or enrich a whole catalog — CSV with columns{" "}
              <code className="text-zinc-400">mpn,brand,description</code>
            </span>
            <label className="sm:ml-auto text-xs px-3 py-2 sm:py-1.5 rounded border border-zinc-700 hover:bg-zinc-800 cursor-pointer min-h-[36px] flex items-center justify-center w-full sm:w-auto transition-colors">
              {uploading ? "Uploading…" : "Upload CSV"}
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={onUpload}
                disabled={uploading || !online}
              />
            </label>
          </div>
          {batchNote && (
            <p className={`text-xs mt-2 ${batchNote.kind === "error" ? "text-red-400" : "text-zinc-400"}`}>
              {batchNote.text}
            </p>
          )}
        </section>

        {events.length > 0 && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg">
            <h2 className="text-sm font-medium text-zinc-400 px-4 pt-3">
              Agent pipeline
            </h2>
            <div
              ref={logRef}
              className="p-4 pt-2 max-h-52 overflow-y-auto font-mono text-xs space-y-1"
            >
              {events.map((e, i) => (
                <div key={i} className="flex gap-2">
                  <span className={`w-24 shrink-0 ${AGENT_COLORS[e.agent] ?? ""}`}>
                    [{e.agent}]
                  </span>
                  <span className="text-zinc-300 break-words">{e.step}</span>
                </div>
              ))}
              {running && <div className="text-zinc-500 motion-safe:animate-pulse">▌</div>}
            </div>
          </section>
        )}

        {statsLoading ? (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg">
            <div className="px-4 py-3 border-b border-zinc-800">
              <div className="h-4 w-40 bg-zinc-800 rounded motion-safe:animate-pulse" />
            </div>
            <RowSkeleton />
          </section>
        ) : catalog.length > 0 ? (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg">
            <h2 className="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">
              Catalog — {catalog.length} enriched SKU{catalog.length === 1 ? "" : "s"}
              <span className="text-zinc-600 font-normal hidden sm:inline">
                {" "}· tap any row to inspect its evidence
              </span>
            </h2>

            {/* Mobile: card list. Desktop: table. Same data, different density. */}
            <div className="max-h-80 overflow-y-auto divide-y divide-zinc-800/70 sm:hidden">
              {catalog.map((r) => (
                <button
                  key={r.id}
                  onClick={() => openRecord(r.id)}
                  disabled={recordLoading}
                  className="w-full text-left px-4 py-3 min-h-[44px] hover:bg-zinc-800/40 active:bg-zinc-800 transition-colors disabled:opacity-60"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm text-zinc-200">{r.mpn}</span>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full border shrink-0 ${statusBadgeClass(r.status)}`}>
                      {pendingRecordId === r.id ? "loading…" : r.status}
                    </span>
                  </div>
                  <div className="text-xs text-zinc-500 mt-0.5 flex items-center gap-1.5 flex-wrap">
                    <span>{r.brand}</span>
                    <span>·</span>
                    <span>{r.category || "uncategorized"}</span>
                    <span>·</span>
                    <span>{r.attribute_count} attrs</span>
                    {r.conflict_count > 0 && (
                      <span className="text-red-400">· {r.conflict_count} conflict</span>
                    )}
                  </div>
                </button>
              ))}
            </div>

            <div className="hidden sm:block max-h-72 overflow-y-auto">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[560px]">
                  <tbody>
                    {catalog.map((r) => (
                      <tr
                        key={r.id}
                        onClick={() => openRecord(r.id)}
                        className="border-b border-zinc-800/70 last:border-0 hover:bg-zinc-800/40 cursor-pointer transition-colors"
                      >
                        <td className="px-4 py-2.5 font-mono text-zinc-300 w-36">
                          {r.mpn}
                        </td>
                        <td className="py-2.5 text-zinc-400 w-28">{r.brand}</td>
                        <td className="py-2.5 text-zinc-500 w-40">{r.category || "—"}</td>
                        <td className="py-2.5 text-zinc-300 w-20 tabular-nums">
                          {r.attribute_count} attrs
                        </td>
                        <td className="py-2.5 w-24">
                          {r.conflict_count > 0 ? (
                            <span className="text-red-400">
                              {r.conflict_count} conflict
                            </span>
                          ) : (
                            <span className="text-zinc-600">clean</span>
                          )}
                        </td>
                        <td className="py-2.5 pr-4 text-right">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full border ${statusBadgeClass(r.status)}`}>
                            {pendingRecordId === r.id ? "loading…" : r.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-8 text-center">
            <p className="text-sm text-zinc-500">
              No enriched SKUs yet — run one above, or upload a CSV to build a catalog.
            </p>
          </section>
        )}

        {recordError && (
          <ErrorBanner message={recordError} onRetry={() => pendingRecordId && openRecord(pendingRecordId)} />
        )}

        {recordLoading && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg">
            <RowSkeleton />
          </section>
        )}

        {record && !recordLoading && (
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between gap-2 flex-wrap">
                <h2 className="text-sm font-medium text-zinc-400">
                  Attributes — {record.category}{" "}
                  <span className="text-zinc-600">
                    ({Math.round(record.category_confidence * 100)}%)
                  </span>
                </h2>
                <span className={`text-[11px] px-2 py-0.5 rounded-full border ${statusBadgeClass(record.status)}`}>
                  {record.status}
                </span>
              </div>
              {record.attributes.length === 0 ? (
                <p className="text-sm text-zinc-500 px-4 py-6 text-center">
                  No attributes extracted — every source may have been blocked or unreachable.
                </p>
              ) : (
                record.attributes.map((a) => (
                  <AttributeRow
                    key={a.name}
                    attr={a}
                    recordId={record.id}
                    onUpdated={setRecord}
                    notify={push}
                  />
                ))
              )}
            </div>

            <div className="space-y-4 min-w-0">
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2">
                <h3 className="text-xs text-zinc-500 uppercase tracking-wide">
                  Commerce copy
                </h3>
                <p className="text-sm font-medium">{record.seo_title || "—"}</p>
                <p className="text-xs text-zinc-400">{record.short_description}</p>
                <div className="flex flex-wrap gap-1 pt-1">
                  {record.search_synonyms.map((s) => (
                    <span
                      key={s}
                      className="text-[11px] bg-zinc-800 rounded-full px-2 py-0.5 text-zinc-400"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2 min-w-0">
                <h3 className="text-xs text-zinc-500 uppercase tracking-wide">
                  Sources ({record.sources.length})
                </h3>
                {record.sources.map((s) => (
                  <a
                    key={s.url}
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block text-xs text-sky-400 hover:underline truncate"
                  >
                    [{s.source_type}] {s.title || s.url}
                  </a>
                ))}
                {record.certifications.length > 0 && (
                  <p className="text-xs text-zinc-400 pt-1 break-words">
                    Certs: {record.certifications.join(", ")}
                  </p>
                )}
                {record.equivalent_mpns.length > 0 && (
                  <p className="text-xs text-zinc-400 break-words">
                    Equivalents: {record.equivalent_mpns.join(", ")}
                  </p>
                )}
                <p className="text-xs text-zinc-500 pt-1 tabular-nums">
                  ${record.cost_usd.toFixed(4)} · {record.duration_s}s
                </p>
                <a
                  href={`${API}/api/export/${record.id}.csv`}
                  className="inline-block text-xs text-sky-400 hover:underline pt-1 min-h-[32px] leading-[32px]"
                >
                  Export CSV →
                </a>
              </div>
            </div>
          </section>
        )}
      </div>

      <ToastStack toasts={toasts} dismiss={dismiss} />
    </main>
  );
}
