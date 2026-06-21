// Kathakaar API client — connects the Figma UI to the FastAPI backend.
//
// Base URL resolution:
//   1. VITE_API_BASE env var (set this in production, e.g. your Render URL)
//   2. http://localhost:8000 during `vite dev`
//   3. same-origin ("") when the backend also serves the built frontend
const RAW_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  (import.meta.env.DEV ? "http://localhost:8000" : "");
export const API_BASE = RAW_BASE.replace(/\/$/, "");

export interface ApiStory {
  accepted: boolean;
  place?: string;
  story?: string;
  grounding_score?: number; // normalized to 0..100 for the meter
  relevance_score?: number; // normalized to 0..100
  citations?: { n: number; title: string; url: string }[];
  unsupported?: string[];
  retrieved?: { title: string; score: number }[];
  mode?: string;
  reason?: string;
  identified_place?: string;
  removed_claims?: number;
}

const pct = (x: unknown) =>
  typeof x === "number" ? Math.round(x * 100) : undefined;

function normalize(d: any): ApiStory {
  return {
    accepted: !!d.accepted,
    place: d.place,
    story: d.story,
    grounding_score: pct(d.grounding_score),
    relevance_score: pct(d.relevance_score),
    citations: d.citations ?? [],
    unsupported: d.unsupported ?? [],
    retrieved: d.retrieved ?? [],
    mode: d.mode,
    reason: d.reason,
    identified_place: d.identified_place,
    removed_claims: d.dropped_unsupported ?? d.removed_claims,
  };
}

export async function getConfig(): Promise<{ places: string[] } | null> {
  try {
    const r = await fetch(`${API_BASE}/api/config`);
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

export async function postStory(
  query: string,
  place: string | null,
  mode: string,
): Promise<ApiStory> {
  const r = await fetch(`${API_BASE}/api/story`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, place: place || null, mode }),
  });
  return normalize(await r.json());
}

export async function postStoryImage(
  file: File,
  query: string,
  mode: string,
): Promise<ApiStory> {
  const fd = new FormData();
  fd.append("image", file);
  fd.append("query", query || "history and architecture");
  fd.append("mode", mode);
  const r = await fetch(`${API_BASE}/api/story-image`, {
    method: "POST",
    body: fd,
  });
  return normalize(await r.json());
}

// ── Cinematic (narrated, animated mini-documentary) ─────────────────────────
export interface CinematicScene {
  index: number;
  title: string;
  narration: string;
  caption: string;
  duration_ms: number;
  visual_note: string;
}
export interface CinematicManifest {
  accepted: boolean;
  title?: string;
  place?: string;
  theme?: string;
  era?: string;
  year?: number;
  format?: string;
  format_label?: string;
  format_origin?: string;
  grounded?: boolean;
  image_url?: string | null;
  voice?: { rate: number; pitch: number };
  citations?: { n: number; title: string; url: string }[];
  scenes?: CinematicScene[];
  reason?: string;
}
export interface StoryFormat { id: string; label: string; origin: string }

export async function getFormats(): Promise<StoryFormat[]> {
  const cfg = await getConfig();
  return (cfg as any)?.formats ?? [];
}

export async function postCinematic(args: {
  query: string; place: string | null; year: number; format: string; duration_secs?: number;
}): Promise<CinematicManifest> {
  const r = await fetch(`${API_BASE}/api/cinematic`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: args.query, place: args.place || null, year: args.year,
      format: args.format, duration_secs: args.duration_secs ?? 60,
    }),
  });
  return await r.json();
}

// ── Premium voice (ElevenLabs) + real-video render hook ─────────────────────
export interface Capabilities {
  tts: { available: boolean; provider?: string };
  render: { available: boolean; provider?: string | null };
}
export async function getCapabilities(): Promise<Capabilities> {
  const c = (await getConfig()) as any;
  return {
    tts: c?.tts ?? { available: false },
    render: c?.render ?? { available: false },
  };
}
// Returns an object-URL for premium MP3 narration, or null (→ use browser voice).
export async function ttsBlobUrl(text: string, voiceId?: string): Promise<string | null> {
  try {
    const r = await fetch(`${API_BASE}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice_id: voiceId ?? null }),
    });
    const ct = r.headers.get("content-type") || "";
    if (!ct.includes("audio")) return null; // no key configured -> JSON response
    return URL.createObjectURL(await r.blob());
  } catch {
    return null;
  }
}
export async function startRender(manifest: CinematicManifest): Promise<any> {
  const r = await fetch(`${API_BASE}/api/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manifest }),
  });
  return r.json();
}
export async function getRender(id: string): Promise<any> {
  const r = await fetch(`${API_BASE}/api/render/${id}`);
  return r.json();
}
