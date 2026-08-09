"use client";

import type { ChangeEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

function ConfidenceBar({ value }: { value: number }) {
  const color =
    value >= 0.8 ? "bg-emerald-500" : value >= 0.5 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 w-28">
      <div className="h-1.5 flex-1 rounded bg-zinc-800">
        <div
          className={`h-1.5 rounded ${color}`}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-zinc-400 w-8">
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

function AttributeRow({
  attr,
  recordId,
  onUpdated,
}: {
  attr: Attribute;
  recordId: string;
  onUpdated: (r: ProductRecord) => void;
}) {
  const [open, setOpen] = useState(attr.status === "conflict");
  const [busy, setBusy] = useState(false);

  const review = async (action: string, newValue = "", newUnit = "") => {
    setBusy(true);
    const res = await fetch(`${API}/api/records/${recordId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        attribute_name: attr.name,
        action,
        new_value: newValue,
        new_unit: newUnit,
      }),
    });
    if (res.ok) onUpdated(await res.json());
    setBusy(false);
  };

  return (
    <div className="border-b border-zinc-800 last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 py-2.5 px-3 hover:bg-zinc-900/60 text-left"
      >
        <span className="font-mono text-sm text-zinc-300 w-44 truncate">
          {attr.name}
        </span>
        <span className="text-sm text-zinc-100 flex-1">
          {attr.value} {attr.unit}
        </span>
        <span
          className={`text-[11px] px-2 py-0.5 rounded-full border ${STATUS_BADGE[attr.status] ?? STATUS_BADGE.generated}`}
        >
          {attr.human_reviewed ? "human-verified" : attr.status}
        </span>
        <ConfidenceBar value={attr.confidence} />
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2">
          {attr.evidence.map((ev, i) => (
            <div key={i} className="text-xs bg-zinc-900 rounded p-2 border border-zinc-800">
              <div className="flex justify-between gap-2">
                <a
                  href={ev.source_url}
                  target="_blank"
                  className="text-sky-400 hover:underline truncate"
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
                <div key={i} className="flex items-center justify-between gap-2">
                  <span className="text-zinc-200">
                    {ev.raw_value}{" "}
                    <span className="text-zinc-500">({ev.source_type})</span>
                  </span>
                  <button
                    disabled={busy}
                    onClick={() => review("edit", ev.raw_value, attr.unit)}
                    className="text-sky-400 hover:underline disabled:opacity-40"
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
                className="px-2.5 py-1 rounded bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600/30 disabled:opacity-40"
              >
                Approve
              </button>
              <button
                disabled={busy}
                onClick={() => review("reject")}
                className="px-2.5 py-1 rounded bg-red-600/20 text-red-400 border border-red-500/30 hover:bg-red-600/30 disabled:opacity-40"
              >
                Reject
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

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

export default function Home() {
  const [mpn, setMpn] = useState("HOM230CP");
  const [brand, setBrand] = useState("Square D");
  const [desc, setDesc] = useState("30A 2 pole breaker");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [record, setRecord] = useState<ProductRecord | null>(null);
  const [running, setRunning] = useState(false);
  const [stats, setStats] = useState<Record<string, number | boolean> | null>(null);
  const [catalog, setCatalog] = useState<RecordSummary[]>([]);
  const [uploading, setUploading] = useState(false);
  const [batchNote, setBatchNote] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  const refreshStats = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([
        fetch(`${API}/api/stats`),
        fetch(`${API}/api/records`),
      ]);
      if (s.ok) setStats(await s.json());
      if (r.ok) setCatalog(await r.json());
    } catch {}
  }, []);

  useEffect(() => {
    refreshStats();
    // The catalog view is a live picture of a running batch.
    const t = setInterval(refreshStats, 5000);
    return () => clearInterval(t);
  }, [refreshStats]);

  const onUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setBatchNote("");
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${API}/api/batch`, { method: "POST", body });
      const data = await res.json();
      setBatchNote(
        res.ok
          ? `Enriching ${data.count} SKUs — the catalog below fills in as each finishes.`
          : `Upload failed: ${data.detail ?? res.statusText}`,
      );
    } catch (err) {
      setBatchNote(`Upload failed: ${String(err)}`);
    } finally {
      setUploading(false);
      e.target.value = "";
      refreshStats();
    }
  };

  const openRecord = async (id: string) => {
    const r = await fetch(`${API}/api/records/${id}`);
    if (r.ok) {
      setRecord(await r.json());
      setEvents([]);
    }
  };

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [events]);

  const enrich = async () => {
    setRunning(true);
    setEvents([]);
    setRecord(null);
    const res = await fetch(`${API}/api/enrich`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mpn, brand, description: desc }),
    });
    const { record_id } = await res.json();

    const es = new EventSource(`${API}/api/events/${record_id}`);
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      setEvents((prev) => [...prev, ev]);
    };
    es.addEventListener("done", async () => {
      es.close();
      const r = await fetch(`${API}/api/records/${record_id}`);
      if (r.ok) setRecord(await r.json());
      setRunning(false);
      refreshStats();
    });
    es.onerror = () => {
      es.close();
      setRunning(false);
    };
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 p-6 font-sans">
      <div className="max-w-6xl mx-auto space-y-6">
        <header className="flex items-baseline justify-between">
          <h1 className="text-2xl font-bold tracking-tight">
            SKU<span className="text-sky-400">Forge</span>
          </h1>
          <p className="text-sm text-zinc-500">
            minimal input → commerce-ready product intelligence, with proof
          </p>
        </header>

        {stats && (
          <div className="grid grid-cols-5 gap-3 text-center">
            {[
              ["Records", stats.completed],
              ["Auto-approved", `${Math.round((stats.auto_approval_rate as number) * 100)}%`],
              ["Avg cost/SKU", `$${stats.avg_cost_usd}`],
              ["Avg time", `${stats.avg_duration_s}s`],
              ["Flagged attrs", stats.attributes_flagged_for_review],
            ].map(([label, value]) => (
              <div
                key={String(label)}
                className="bg-zinc-900 border border-zinc-800 rounded-lg py-3"
              >
                <div className="text-lg font-semibold tabular-nums">{String(value)}</div>
                <div className="text-xs text-zinc-500">{String(label)}</div>
              </div>
            ))}
          </div>
        )}

        <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="flex gap-3">
            <input
              value={mpn}
              onChange={(e) => setMpn(e.target.value)}
              placeholder="MPN"
              className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm w-44"
            />
            <input
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="Brand"
              className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm w-44"
            />
            <input
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="One-line description"
              className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm flex-1"
            />
            <button
              onClick={enrich}
              disabled={running || !mpn || !brand}
              className="px-5 py-2 rounded bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-sm font-medium"
            >
              {running ? "Enriching…" : "Enrich"}
            </button>
          </div>

          <div className="flex items-center gap-3 mt-3 pt-3 border-t border-zinc-800">
            <span className="text-xs text-zinc-500">
              Or enrich a whole catalog — CSV with columns{" "}
              <code className="text-zinc-400">mpn,brand,description</code>
            </span>
            <label className="ml-auto text-xs px-3 py-1.5 rounded border border-zinc-700 hover:bg-zinc-800 cursor-pointer">
              {uploading ? "Uploading…" : "Upload CSV"}
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={onUpload}
                disabled={uploading}
              />
            </label>
          </div>
          {batchNote && (
            <p className="text-xs text-zinc-400 mt-2">{batchNote}</p>
          )}
        </section>

        {events.length > 0 && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg">
            <h2 className="text-sm font-medium text-zinc-400 px-4 pt-3">
              Agent pipeline
            </h2>
            <div ref={logRef} className="p-4 pt-2 max-h-52 overflow-y-auto font-mono text-xs space-y-1">
              {events.map((e, i) => (
                <div key={i} className="flex gap-2">
                  <span className={`w-24 shrink-0 ${AGENT_COLORS[e.agent] ?? ""}`}>
                    [{e.agent}]
                  </span>
                  <span className="text-zinc-300">{e.step}</span>
                </div>
              ))}
              {running && <div className="text-zinc-500 animate-pulse">▌</div>}
            </div>
          </section>
        )}

        {catalog.length > 0 && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg">
            <h2 className="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">
              Catalog — {catalog.length} enriched SKUs
              <span className="text-zinc-600 font-normal">
                {" "}· click any row to inspect its evidence
              </span>
            </h2>
            <div className="max-h-72 overflow-y-auto">
              <table className="w-full text-sm">
                <tbody>
                  {catalog.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => openRecord(r.id)}
                      className="border-b border-zinc-800/70 last:border-0 hover:bg-zinc-800/40 cursor-pointer"
                    >
                      <td className="px-4 py-2 font-mono text-zinc-300 w-36">
                        {r.mpn}
                      </td>
                      <td className="py-2 text-zinc-400 w-28">{r.brand}</td>
                      <td className="py-2 text-zinc-500 w-40">{r.category || "—"}</td>
                      <td className="py-2 text-zinc-300 w-20 tabular-nums">
                        {r.attribute_count} attrs
                      </td>
                      <td className="py-2 w-24">
                        {r.conflict_count > 0 ? (
                          <span className="text-red-400">
                            {r.conflict_count} conflict
                          </span>
                        ) : (
                          <span className="text-zinc-600">clean</span>
                        )}
                      </td>
                      <td className="py-2 pr-4 text-right">
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded-full border ${
                            r.status === "auto-approved" || r.status === "approved"
                              ? STATUS_BADGE.verified
                              : r.status === "failed"
                                ? STATUS_BADGE.conflict
                                : STATUS_BADGE["single-source"]
                          }`}
                        >
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {record && (
          <section className="grid grid-cols-3 gap-4">
            <div className="col-span-2 bg-zinc-900 border border-zinc-800 rounded-lg">
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
                <h2 className="text-sm font-medium text-zinc-400">
                  Attributes — {record.category}{" "}
                  <span className="text-zinc-600">
                    ({Math.round(record.category_confidence * 100)}%)
                  </span>
                </h2>
                <span
                  className={`text-[11px] px-2 py-0.5 rounded-full border ${
                    record.status === "auto-approved" || record.status === "approved"
                      ? STATUS_BADGE.verified
                      : STATUS_BADGE["single-source"]
                  }`}
                >
                  {record.status}
                </span>
              </div>
              {record.attributes.map((a) => (
                <AttributeRow
                  key={a.name}
                  attr={a}
                  recordId={record.id}
                  onUpdated={setRecord}
                />
              ))}
            </div>

            <div className="space-y-4">
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2">
                <h3 className="text-xs text-zinc-500 uppercase tracking-wide">
                  Commerce copy
                </h3>
                <p className="text-sm font-medium">{record.seo_title}</p>
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

              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2">
                <h3 className="text-xs text-zinc-500 uppercase tracking-wide">
                  Sources ({record.sources.length})
                </h3>
                {record.sources.map((s) => (
                  <a
                    key={s.url}
                    href={s.url}
                    target="_blank"
                    className="block text-xs text-sky-400 hover:underline truncate"
                  >
                    [{s.source_type}] {s.title || s.url}
                  </a>
                ))}
                {record.certifications.length > 0 && (
                  <p className="text-xs text-zinc-400 pt-1">
                    Certs: {record.certifications.join(", ")}
                  </p>
                )}
                {record.equivalent_mpns.length > 0 && (
                  <p className="text-xs text-zinc-400">
                    Equivalents: {record.equivalent_mpns.join(", ")}
                  </p>
                )}
                <p className="text-xs text-zinc-500 pt-1">
                  ${record.cost_usd.toFixed(4)} · {record.duration_s}s
                </p>
                <a
                  href={`${API}/api/export/${record.id}.csv`}
                  className="inline-block text-xs text-sky-400 hover:underline pt-1"
                >
                  Export CSV →
                </a>
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
