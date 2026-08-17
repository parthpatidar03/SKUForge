"use client";

import type { ChangeEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import ThemeToggle from "./ThemeToggle";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Free tier model calls run 60 to 150 s. Below this we stay quiet; above it we
// explain, so silence is never mistaken for a hang.
const SLOW_MS = 12_000;

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
  attribute_count: number;
  conflict_count: number;
  duration_s: number;
  cost_usd: number;
};

type Toast = { id: number; kind: "ok" | "bad"; text: string };

const AGENT_TONE: Record<string, string> = {
  scout: "text-accent",
  classifier: "text-ink-2",
  extractor: "text-single",
  validator: "text-verified",
  composer: "text-accent",
  orchestrator: "text-ink-3",
};

function stateClass(status: string) {
  if (status === "verified" || status === "human-verified")
    return "text-verified bg-verified-bg border-verified/30";
  if (status === "conflict") return "text-conflict bg-conflict-bg border-conflict/30";
  if (status === "generated") return "text-ink-3 bg-sunken border-line-strong";
  return "text-single bg-single-bg border-single/30";
}

function recordStateClass(status: string) {
  if (status === "auto-approved" || status === "approved")
    return "text-verified bg-verified-bg border-verified/30";
  if (status === "failed") return "text-conflict bg-conflict-bg border-conflict/30";
  return "text-single bg-single-bg border-single/30";
}

function barColor(v: number) {
  return v >= 0.8 ? "bg-verified" : v >= 0.5 ? "bg-single" : "bg-conflict";
}

/* ---------------------------------------------------------------- chrome */

function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <rect width="32" height="32" rx="7" className="fill-accent" />
      <g fill="white" fillOpacity="0.34">
        <rect x="6" y="6" width="4.5" height="4.5" rx="1.2" />
        <rect x="13" y="6" width="4.5" height="4.5" rx="1.2" />
        <rect x="20" y="6" width="4.5" height="4.5" rx="1.2" />
        <rect x="6" y="13" width="4.5" height="4.5" rx="1.2" />
        <rect x="20" y="13" width="4.5" height="4.5" rx="1.2" />
        <rect x="6" y="20" width="4.5" height="4.5" rx="1.2" />
        <rect x="13" y="20" width="4.5" height="4.5" rx="1.2" />
        <rect x="20" y="20" width="4.5" height="4.5" rx="1.2" />
      </g>
      <g fill="white">
        <rect x="6" y="20" width="4.5" height="4.5" rx="1.2" />
        <rect x="13" y="13" width="4.5" height="4.5" rx="1.2" />
        <rect x="20" y="6" width="4.5" height="4.5" rx="1.2" />
      </g>
    </svg>
  );
}

function Header({ online }: { online: boolean }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-blur-[2px]">
      <div className="mx-auto max-w-[1200px] px-4 sm:px-6 h-14 flex items-center gap-3">
        <Mark />
        <div className="min-w-0">
          <div className="font-semibold tracking-tight text-[15px] leading-none">
            SKUForge
          </div>
          <div className="hidden sm:block text-[11px] text-ink-3 leading-none mt-1">
            Verified product enrichment
          </div>
        </div>
        <div className="ml-auto flex items-center gap-3">
          {!online && (
            <span className="text-xs text-conflict">Offline</span>
          )}
          <a
            href="https://github.com/parthpatidar03/SKUForge"
            target="_blank"
            rel="noreferrer"
            className="text-xs text-ink-2 hover:text-accent transition-colors"
          >
            Source
          </a>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="mt-auto border-t border-line">
      <div className="mx-auto max-w-[1200px] px-4 sm:px-6 py-5 flex flex-col sm:flex-row gap-2 sm:items-center justify-between text-xs text-ink-3">
        <span>
          SKUForge, built for UniHack 2026. Every attribute carries its source.
        </span>
        <span className="tnum">
          Confidence at or above 0.80 auto approves. Everything else reaches a
          human.
        </span>
      </div>
    </footer>
  );
}

/* --------------------------------------------------------------- helpers */

function useOnline() {
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

async function fetchSlow(
  url: string,
  init: RequestInit | undefined,
  onSlow: () => void,
  timeoutMs = 30_000,
) {
  const slow = window.setTimeout(onSlow, SLOW_MS);
  const ctl = new AbortController();
  const kill = window.setTimeout(() => ctl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctl.signal });
  } finally {
    window.clearTimeout(slow);
    window.clearTimeout(kill);
  }
}

function Notice({
  tone = "bad",
  children,
  onRetry,
}: {
  tone?: "bad" | "warn";
  children: React.ReactNode;
  onRetry?: () => void;
}) {
  const c =
    tone === "bad"
      ? "border-conflict/30 bg-conflict-bg text-conflict"
      : "border-single/30 bg-single-bg text-single";
  return (
    <div
      className={`rounded-lg border ${c} px-4 py-3 text-sm flex flex-wrap items-center gap-3 justify-between`}
      role="status"
    >
      <span>{children}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 rounded-md border border-current/30 px-2.5 py-1 text-xs font-medium hover:bg-current/5 transition-colors min-h-8"
        >
          Retry
        </button>
      )}
    </div>
  );
}

function Bar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2 w-[86px] sm:w-[108px] shrink-0">
      <div className="h-1.5 flex-1 rounded-full bg-line overflow-hidden">
        <div
          className={`h-full rounded-full bar-fill ${barColor(value)}`}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      <span className="tnum text-xs text-ink-2 w-8 text-right">
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

/* ------------------------------------------------------------ attributes */

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
        notify("ok", `${attr.name} ${action === "reject" ? "removed" : "confirmed"}`);
      } else notify("bad", `Could not update ${attr.name}`);
    } catch {
      notify("bad", `Network error updating ${attr.name}`);
    } finally {
      setBusy(false);
    }
  };

  const label = attr.human_reviewed ? "human-verified" : attr.status;

  return (
    <div className="border-b border-line last:border-0">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full text-left px-3 sm:px-4 py-3 min-h-11 hover:bg-accent-weak/60 transition-colors grid grid-cols-[1fr_auto] sm:grid-cols-[190px_1fr_auto_auto] items-center gap-x-3 gap-y-1"
      >
        <span className="font-mono text-[13px] text-ink-2 truncate">
          {attr.name}
        </span>
        <span className="font-mono text-[13px] font-medium col-start-1 sm:col-start-2 truncate">
          {attr.value}
          {attr.unit ? ` ${attr.unit}` : ""}
        </span>
        <span
          className={`justify-self-end row-start-1 col-start-2 sm:row-auto sm:col-auto text-[11px] px-2 py-0.5 rounded-full border ${stateClass(label)}`}
        >
          {label}
        </span>
        <span className="col-span-2 sm:col-auto justify-self-end">
          <Bar value={attr.confidence} />
        </span>
      </button>

      {open && (
        <div className="px-3 sm:px-4 pb-4 space-y-2">
          {attr.evidence.map((ev, i) => (
            <div key={i} className="rounded-md border border-line bg-sunken p-2.5">
              <div className="flex justify-between gap-3 flex-wrap">
                <a
                  href={ev.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-accent hover:underline break-all"
                >
                  {ev.source_url}
                </a>
                <span className="text-[11px] text-ink-3 shrink-0 track uppercase">
                  {ev.source_type}
                </span>
              </div>
              {ev.quote && (
                <p className="mt-1.5 font-mono text-xs text-ink-2">
                  &ldquo;{ev.quote}&rdquo;
                </p>
              )}
            </div>
          ))}

          {attr.conflicting_values.length > 0 && (
            <div className="rounded-md border border-conflict/30 bg-conflict-bg p-2.5 space-y-2">
              <p className="text-xs font-medium text-conflict">
                Sources disagree. Pick the correct value.
              </p>
              {attr.conflicting_values.map((ev, i) => (
                <div key={i} className="flex items-center justify-between gap-3 flex-wrap">
                  <span className="font-mono text-xs">
                    {ev.raw_value}{" "}
                    <span className="text-ink-3">({ev.source_type})</span>
                  </span>
                  <button
                    disabled={busy}
                    onClick={() => review("edit", ev.raw_value, attr.unit)}
                    className="text-xs text-accent hover:underline disabled:opacity-40 min-h-8 px-1"
                  >
                    Use this
                  </button>
                </div>
              ))}
            </div>
          )}

          {!attr.human_reviewed && (
            <div className="flex gap-2 pt-0.5">
              <button
                disabled={busy}
                onClick={() => review("approve")}
                className="rounded-md border border-verified/30 bg-verified-bg text-verified px-3 py-1.5 text-xs font-medium hover:bg-verified/10 disabled:opacity-40 transition-colors min-h-8"
              >
                {busy ? "Saving" : "Confirm"}
              </button>
              <button
                disabled={busy}
                onClick={() => review("reject")}
                className="rounded-md border border-line bg-card px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-sunken disabled:opacity-40 transition-colors min-h-8"
              >
                Remove
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ page */

export default function Home() {
  const [mpn, setMpn] = useState("HOM230CP");
  const [brand, setBrand] = useState("Square D");
  const [desc, setDesc] = useState("30A 2 pole breaker");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [record, setRecord] = useState<ProductRecord | null>(null);
  const [running, setRunning] = useState(false);
  const [slow, setSlow] = useState(false);
  const [runError, setRunError] = useState("");

  const [stats, setStats] = useState<Record<string, number | boolean> | null>(null);
  const [catalog, setCatalog] = useState<RecordSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [uploading, setUploading] = useState(false);
  const [batchNote, setBatchNote] = useState<{ bad: boolean; text: string } | null>(null);

  const [openingId, setOpeningId] = useState<string | null>(null);
  const [recordError, setRecordError] = useState("");

  const [toasts, setToasts] = useState<Toast[]>([]);
  const online = useOnline();
  const logRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const notify = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([
        fetch(`${API}/api/stats`),
        fetch(`${API}/api/records`),
      ]);
      if (s.ok) setStats(await s.json());
      if (r.ok) setCatalog(await r.json());
      if (!s.ok && !r.ok) throw new Error("unreachable");
      setLoadError("");
    } catch {
      setLoadError(
        "Cannot reach the server. Free tier hosting sleeps when idle, so give it a few seconds.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => () => esRef.current?.close(), []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [events]);

  const onUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setBatchNote({ bad: true, text: "That file is not a CSV." });
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
          bad: false,
          text: `Running ${data.count} SKUs. The catalog fills in as each finishes.`,
        });
        notify("ok", `Batch started, ${data.count} SKUs`);
      } else {
        setBatchNote({ bad: true, text: `Upload failed. ${data.detail ?? res.statusText}` });
      }
    } catch (err) {
      setBatchNote({
        bad: true,
        text:
          err instanceof DOMException && err.name === "AbortError"
            ? "Upload timed out. Check your connection."
            : "Upload failed.",
      });
    } finally {
      setUploading(false);
      e.target.value = "";
      refresh();
    }
  };

  const openRecord = async (id: string) => {
    setOpeningId(id);
    setRecordError("");
    try {
      const r = await fetchSlow(`${API}/api/records/${id}`, undefined, () => {});
      if (r.ok) {
        setRecord(await r.json());
        setEvents([]);
        requestAnimationFrame(() =>
          resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
        );
      } else setRecordError("That record could not be loaded.");
    } catch {
      setRecordError("Network error loading that record.");
    } finally {
      setOpeningId(null);
    }
  };

  const enrich = async () => {
    setRunning(true);
    setSlow(false);
    setRunError("");
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
        () => setSlow(true),
        20_000,
      );
      if (!res.ok) throw new Error(String(res.status));
      ({ record_id } = await res.json());
    } catch (err) {
      setRunning(false);
      setRunError(
        err instanceof DOMException && err.name === "AbortError"
          ? "The server took too long to respond. It may be waking up."
          : "Could not start enrichment. Check your connection.",
      );
      return;
    }

    const es = new EventSource(`${API}/api/events/${record_id}`);
    esRef.current = es;
    let done = false;
    const slowTimer = window.setTimeout(() => setSlow(true), SLOW_MS);

    es.onmessage = (e) => {
      setSlow(false);
      window.clearTimeout(slowTimer);
      setEvents((prev) => [...prev, JSON.parse(e.data)]);
    };
    es.addEventListener("done", async () => {
      done = true;
      window.clearTimeout(slowTimer);
      es.close();
      try {
        const r = await fetch(`${API}/api/records/${record_id}`);
        if (r.ok) {
          setRecord(await r.json());
          notify("ok", "Enrichment complete");
          requestAnimationFrame(() =>
            resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
          );
        }
      } catch {
        setRunError("Finished, but the result could not be loaded. Check the catalog.");
      }
      setRunning(false);
      refresh();
    });
    es.onerror = () => {
      window.clearTimeout(slowTimer);
      es.close();
      setRunning(false);
      if (!done)
        setRunError(
          "Lost connection during the run. Check the catalog, it may have finished.",
        );
    };
  };

  const statCards: [string, string][] = stats
    ? [
        ["Records", String(stats.completed)],
        ["Auto approved", `${Math.round((stats.auto_approval_rate as number) * 100)}%`],
        ["Avg cost", `$${stats.avg_cost_usd}`],
        ["Avg time", `${stats.avg_duration_s}s`],
        ["Flagged", String(stats.attributes_flagged_for_review)],
      ]
    : [];

  return (
    <>
      <Header online={online} />

      <main className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 py-6 sm:py-8 space-y-6">
        {/* how to use, three steps, always visible so the page explains itself */}
        <section aria-labelledby="howto">
          <h1 id="howto" className="text-[22px] sm:text-[26px] font-semibold tracking-tight">
            Enrich a part number into a sourced product record
          </h1>
          <p className="mt-1.5 text-ink-2 max-w-[68ch]">
            Give it a manufacturer part number, a brand and one line of text. It
            finds the datasheets, extracts the specifications, and scores every
            value against the sources it found.
          </p>
          <ol className="mt-4 grid gap-2.5 sm:grid-cols-3">
            {[
              ["1", "Enter a part", "Type an MPN and brand, or upload a CSV to run a whole catalog."],
              ["2", "Watch it work", "Each agent reports as it runs, including why a source was skipped."],
              ["3", "Clear the queue", "Open any row. Confirm what is right, resolve what disagrees."],
            ].map(([n, t, d]) => (
              <li
                key={n}
                className="rounded-lg border border-line bg-card p-3.5 flex gap-3"
              >
                <span className="shrink-0 w-6 h-6 rounded-full bg-accent-weak text-accent grid place-items-center text-xs font-semibold tnum">
                  {n}
                </span>
                <span>
                  <span className="block font-medium text-[13px]">{t}</span>
                  <span className="block text-[13px] text-ink-2 mt-0.5">{d}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>

        {!online && (
          <Notice tone="warn">
            No internet connection. Actions will fail until it returns.
          </Notice>
        )}

        {/* input */}
        <section className="rounded-lg border border-line bg-card">
          <div className="p-3.5 sm:p-4 grid gap-2.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)_auto]">
            <label className="grid gap-1.5">
              <span className="text-[11px] uppercase track text-ink-3">Part number</span>
              <input
                value={mpn}
                onChange={(e) => setMpn(e.target.value)}
                placeholder="HOM230CP"
                className="h-10 rounded-md border border-line bg-card px-3 font-mono text-[13px] focus:border-accent transition-colors"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] uppercase track text-ink-3">Brand</span>
              <input
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="Square D"
                className="h-10 rounded-md border border-line bg-card px-3 text-[13px] focus:border-accent transition-colors"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] uppercase track text-ink-3">Description</span>
              <input
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="30A 2 pole breaker"
                onKeyDown={(e) => e.key === "Enter" && !running && mpn && brand && enrich()}
                className="h-10 rounded-md border border-line bg-card px-3 text-[13px] focus:border-accent transition-colors"
              />
            </label>
            <div className="grid gap-1.5">
              <span className="hidden sm:block text-[11px]">&nbsp;</span>
              <button
                onClick={enrich}
                disabled={running || !mpn || !brand || !online}
                className="h-10 px-5 rounded-md bg-accent text-white text-[13px] font-medium hover:bg-accent-hover active:translate-y-px disabled:opacity-40 disabled:hover:bg-accent transition-colors whitespace-nowrap"
              >
                {running ? "Enriching" : "Enrich"}
              </button>
            </div>
          </div>

          <div className="border-t border-line px-3.5 sm:px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-2 text-[13px] text-ink-3">
            <span>
              Or run a catalog. CSV columns{" "}
              <code className="font-mono text-ink-2">mpn,brand,description</code>
            </span>
            <label className="sm:ml-auto rounded-md border border-line bg-card px-3 py-1.5 text-[13px] text-ink-2 hover:bg-sunken cursor-pointer transition-colors min-h-8 inline-flex items-center">
              {uploading ? "Uploading" : "Upload CSV"}
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={onUpload}
                disabled={uploading || !online}
              />
            </label>
          </div>

          {(slow && running) || runError || batchNote ? (
            <div className="border-t border-line px-3.5 sm:px-4 py-3 space-y-2.5">
              {running && slow && (
                <p className="text-[13px] text-single flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-single skeleton" />
                  Still working. Free tier models take 60 to 150 s per SKU.
                </p>
              )}
              {runError && <Notice onRetry={enrich}>{runError}</Notice>}
              {batchNote && (
                <p className={`text-[13px] ${batchNote.bad ? "text-conflict" : "text-ink-2"}`}>
                  {batchNote.text}
                </p>
              )}
            </div>
          ) : null}
        </section>

        {/* agent theatre */}
        {events.length > 0 && (
          <section className="rounded-lg border border-line bg-card overflow-hidden">
            <h2 className="text-[11px] uppercase track text-ink-3 px-4 py-2.5 bg-sunken border-b border-line">
              Pipeline
            </h2>
            <div ref={logRef} className="p-3 sm:p-4 max-h-52 overflow-y-auto font-mono text-xs space-y-1.5">
              {events.map((e, i) => (
                <div key={i} className="flex gap-2.5">
                  <span className={`w-[86px] shrink-0 ${AGENT_TONE[e.agent] ?? "text-ink-3"}`}>
                    {e.agent}
                  </span>
                  <span className="text-ink-2 break-words">{e.step}</span>
                </div>
              ))}
              {running && <div className="text-ink-3 skeleton w-2 h-3.5 inline-block" />}
            </div>
          </section>
        )}

        {/* stats */}
        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="rounded-lg border border-line bg-card p-3">
                <div className="skeleton h-5 w-14 rounded" />
                <div className="skeleton h-3 w-20 rounded mt-2" />
              </div>
            ))}
          </div>
        ) : loadError ? (
          <Notice onRetry={refresh}>{loadError}</Notice>
        ) : stats ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
            {statCards.map(([label, value]) => (
              <div key={label} className="rounded-lg border border-line bg-card px-3.5 py-3">
                <div className="tnum text-lg font-semibold">{value}</div>
                <div className="text-[11px] uppercase track text-ink-3 mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        ) : null}

        {/* catalog */}
        {loading ? (
          <div className="rounded-lg border border-line bg-card p-4 space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="skeleton h-9 rounded" />
            ))}
          </div>
        ) : catalog.length > 0 ? (
          <section className="rounded-lg border border-line bg-card overflow-hidden">
            <h2 className="flex items-baseline gap-2 text-[11px] uppercase track text-ink-3 px-4 py-2.5 bg-sunken border-b border-line">
              Catalog
              <span className="tnum normal-case tracking-normal text-ink-2">
                {catalog.length} records
              </span>
            </h2>

            {/* mobile: stacked rows. tablet and up: table. */}
            <div className="sm:hidden divide-y divide-line max-h-[420px] overflow-y-auto">
              {catalog.map((r) => (
                <button
                  key={r.id}
                  onClick={() => openRecord(r.id)}
                  disabled={openingId !== null}
                  className="w-full text-left px-4 py-3 min-h-11 hover:bg-accent-weak/60 active:bg-accent-weak transition-colors disabled:opacity-60"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[13px] font-medium">{r.mpn}</span>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full border shrink-0 ${recordStateClass(r.status)}`}>
                      {openingId === r.id ? "opening" : r.status}
                    </span>
                  </div>
                  <div className="text-xs text-ink-3 mt-1 flex flex-wrap gap-x-2">
                    <span>{r.brand}</span>
                    <span>{r.category || "uncategorised"}</span>
                    <span className="tnum">{r.attribute_count} attrs</span>
                    {r.conflict_count > 0 && (
                      <span className="text-conflict tnum">{r.conflict_count} conflict</span>
                    )}
                  </div>
                </button>
              ))}
            </div>

            <div className="hidden sm:block max-h-[420px] overflow-y-auto">
              <table className="w-full text-[13px]">
                <thead className="sr-only">
                  <tr>
                    <th>Part</th><th>Brand</th><th>Category</th>
                    <th>Attributes</th><th>Conflicts</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {catalog.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => openRecord(r.id)}
                      className="border-b border-line last:border-0 hover:bg-accent-weak/60 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-2.5 font-mono font-medium w-[150px]">{r.mpn}</td>
                      <td className="py-2.5 text-ink-2 w-[120px]">{r.brand}</td>
                      <td className="py-2.5 text-ink-3 w-[160px]">{r.category || "—"}</td>
                      <td className="py-2.5 tnum text-ink-2 w-[90px]">{r.attribute_count} attrs</td>
                      <td className="py-2.5 w-[110px]">
                        {r.conflict_count > 0 ? (
                          <span className="text-conflict tnum">{r.conflict_count} conflict</span>
                        ) : (
                          <span className="text-ink-3">clean</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 text-right">
                        <span className={`text-[11px] px-2 py-0.5 rounded-full border ${recordStateClass(r.status)}`}>
                          {openingId === r.id ? "opening" : r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <section className="rounded-lg border border-line bg-card px-6 py-10 text-center">
            <p className="font-medium">No records yet</p>
            <p className="text-ink-2 text-[13px] mt-1 max-w-[46ch] mx-auto">
              Run the part above to see how a record is built, or upload a CSV to
              enrich a whole catalog at once.
            </p>
          </section>
        )}

        {recordError && (
          <Notice onRetry={() => openingId && openRecord(openingId)}>{recordError}</Notice>
        )}

        {/* record */}
        {record && (
          <section ref={resultRef} className="grid gap-4 lg:grid-cols-[1.55fr_1fr] scroll-mt-20">
            <div className="rounded-lg border border-line bg-card overflow-hidden">
              <div className="flex items-center justify-between gap-2 flex-wrap px-4 py-2.5 bg-sunken border-b border-line">
                <h2 className="text-[11px] uppercase track text-ink-3">
                  Attributes
                  <span className="normal-case tracking-normal text-ink-2 ml-2">
                    {record.category} · {Math.round(record.category_confidence * 100)}% match
                  </span>
                </h2>
                <span className={`text-[11px] px-2 py-0.5 rounded-full border ${recordStateClass(record.status)}`}>
                  {record.status}
                </span>
              </div>
              {record.attributes.length === 0 ? (
                <p className="px-4 py-8 text-center text-[13px] text-ink-2">
                  No attributes extracted. Every source was blocked or unreachable.
                </p>
              ) : (
                record.attributes.map((a) => (
                  <AttributeRow
                    key={a.name}
                    attr={a}
                    recordId={record.id}
                    onUpdated={setRecord}
                    notify={notify}
                  />
                ))
              )}
            </div>

            <div className="grid gap-4 content-start min-w-0">
              <div className="rounded-lg border border-line bg-card overflow-hidden">
                <h3 className="text-[11px] uppercase track text-ink-3 px-4 py-2.5 bg-sunken border-b border-line">
                  Generated copy
                </h3>
                <div className="p-4 space-y-2">
                  <p className="font-medium text-[13px]">{record.seo_title || "—"}</p>
                  <p className="text-[13px] text-ink-2">{record.short_description}</p>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {record.search_synonyms.map((s) => (
                      <span
                        key={s}
                        className="text-[11px] bg-sunken border border-line rounded-full px-2 py-0.5 text-ink-2"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-line bg-card overflow-hidden min-w-0">
                <h3 className="text-[11px] uppercase track text-ink-3 px-4 py-2.5 bg-sunken border-b border-line">
                  Sources
                  <span className="tnum normal-case tracking-normal text-ink-2 ml-2">
                    {record.sources.length}
                  </span>
                </h3>
                <div className="p-4 space-y-2 min-w-0">
                  {record.sources.map((s) => (
                    <a
                      key={s.url}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="block text-xs text-accent hover:underline truncate"
                    >
                      {s.title || s.url}
                    </a>
                  ))}
                  {record.certifications.length > 0 && (
                    <p className="text-xs text-ink-2 pt-1 break-words">
                      Certifications: {record.certifications.join(", ")}
                    </p>
                  )}
                  {record.equivalent_mpns.length > 0 && (
                    <p className="text-xs text-ink-2 break-words">
                      Equivalents: {record.equivalent_mpns.join(", ")}
                    </p>
                  )}
                  <p className="tnum text-xs text-ink-3 pt-1 border-t border-line mt-2">
                    ${record.cost_usd.toFixed(4)} · {record.duration_s}s
                  </p>
                  <a
                    href={`${API}/api/export/${record.id}.csv`}
                    className="inline-flex items-center min-h-8 text-xs text-accent hover:underline"
                  >
                    Export CSV
                  </a>
                </div>
              </div>
            </div>
          </section>
        )}
      </main>

      <Footer />

      {toasts.length > 0 && (
        <div
          className="fixed bottom-3 left-1/2 -translate-x-1/2 sm:left-auto sm:right-5 sm:translate-x-0 z-50 flex flex-col gap-2 w-[calc(100%-1.5rem)] max-w-xs"
          role="status"
          aria-live="polite"
        >
          {toasts.map((t) => (
            <div
              key={t.id}
              onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}
              className={`toast-in cursor-pointer rounded-lg border px-3.5 py-2.5 text-[13px] shadow-[0_6px_24px_-8px_rgb(0_0_0/0.25)] ${
                t.kind === "ok"
                  ? "bg-verified-bg border-verified/30 text-verified"
                  : "bg-conflict-bg border-conflict/30 text-conflict"
              }`}
            >
              {t.text}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
