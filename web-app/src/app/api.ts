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
