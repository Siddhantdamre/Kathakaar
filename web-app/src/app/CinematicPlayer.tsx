import { useEffect, useRef, useState, useCallback } from "react";
import { Play, Pause, RotateCcw, Volume2, VolumeX, Clapperboard, Loader2 } from "lucide-react";
import type { CinematicManifest } from "./api";
import { getCapabilities, ttsBlobUrl, startRender, getRender } from "./api";

// Format → accent colour for the cinematic overlay (visible style difference per tradition)
const FORMAT_COLOUR: Record<string, string> = {
  oral:   "rgba(232,176,75,0.08)",
  griot:  "rgba(180,100,40,0.10)",
  ballad: "rgba(80,120,200,0.10)",
  koan:   "rgba(120,180,140,0.08)",
  myth:   "rgba(100,60,180,0.10)",
};

const speechOK =
  typeof window !== "undefined" && "speechSynthesis" in window;

export function CinematicPlayer({ manifest }: { manifest: CinematicManifest }) {
  const scenes = manifest.scenes ?? [];
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [imgOk, setImgOk] = useState(true);
  const [kb, setKb] = useState(false); // ken-burns toggle per scene
  const [ttsOn, setTtsOn] = useState(false);
  const [renderOn, setRenderOn] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [renderMsg, setRenderMsg] = useState<string | null>(null);

  const playingRef = useRef(false);
  const mutedRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const ttsRef = useRef(false);
  const voicesRef = useRef<SpeechSynthesisVoice[]>([]);

  // Use only the server-resolved Wikipedia image (fetched server-side on Render —
  // no hotlink blocking). Direct Unsplash hotlinks fail in production without a key.
  const imgUrl = manifest.image_url || null;
  const formatColour = FORMAT_COLOUR[manifest.format ?? "oral"] ?? FORMAT_COLOUR.oral;

  // ── procedural canvas layer: golden particles + light sweep + grain ──────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let t = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      canvas.width = r.width * dpr;
      canvas.height = r.height * dpr;
    };
    resize();
    window.addEventListener("resize", resize);
    const P = Array.from({ length: 70 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() * 1.8 + 0.4,
      s: Math.random() * 0.00022 + 0.00006,
      tw: Math.random() * Math.PI * 2,
    }));
    const draw = () => {
      const w = canvas.width;
      const h = canvas.height;
      t += 1;
      ctx.clearRect(0, 0, w, h);
      // vignette
      const g = ctx.createRadialGradient(w / 2, h / 2, h * 0.2, w / 2, h / 2, h * 0.75);
      g.addColorStop(0, "rgba(0,0,0,0)");
      g.addColorStop(1, "rgba(0,0,0,0.55)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
      // moving light sweep
      const lx = ((Math.sin(t * 0.0016) + 1) / 2) * w;
      const lg = ctx.createLinearGradient(lx - w * 0.25, 0, lx + w * 0.25, h);
      lg.addColorStop(0, "rgba(232,176,75,0)");
      lg.addColorStop(0.5, "rgba(232,176,75,0.06)");
      lg.addColorStop(1, "rgba(232,176,75,0)");
      ctx.fillStyle = lg;
      ctx.fillRect(0, 0, w, h);
      // particles (golden motes drifting up)
      for (const p of P) {
        p.y -= p.s;
        p.tw += 0.03;
        if (p.y < -0.02) {
          p.y = 1.02;
          p.x = Math.random();
        }
        const alpha = 0.35 + Math.sin(p.tw) * 0.3;
        ctx.beginPath();
        ctx.arc(p.x * w, p.y * h, p.r * dpr, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(245,210,140,${Math.max(0, alpha)})`;
        ctx.fill();
      }
      // film grain (cheap)
      for (let i = 0; i < 40; i++) {
        ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.025})`;
        ctx.fillRect(Math.random() * w, Math.random() * h, dpr, dpr);
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  // ── narration sequencing ─────────────────────────────────────────────────
  const revokeUrl = () => {
    if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null; }
  };
  const stopAll = useCallback(() => {
    playingRef.current = false;
    if (speechOK) window.speechSynthesis.cancel();
    const a = audioRef.current;
    if (a) { a.pause(); a.onended = null; a.onerror = null; }
    revokeUrl();
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const playFrom = useCallback(
    (i: number) => {
      if (i >= scenes.length) {
        stopAll();
        setPlaying(false);
        return;
      }
      setIdx(i);
      setKb((k) => !k);
      const advance = () => {
        if (!playingRef.current) return;
        if (i + 1 < scenes.length) playFrom(i + 1);
        else {
          setPlaying(false);
          playingRef.current = false;
        }
      };
      const speakWeb = () => {
        if (!speechOK) { timerRef.current = window.setTimeout(advance, scenes[i].duration_ms || 6000); return; }
        const u = new SpeechSynthesisUtterance(scenes[i].narration);
        u.rate = manifest.voice?.rate ?? 0.9;
        u.pitch = manifest.voice?.pitch ?? 1;
        u.lang = "en-IN";
        const en = voicesRef.current.filter((v) => v.lang && v.lang.toLowerCase().startsWith("en"));
        if (en.length) {
          const order = ["oral", "griot", "ballad", "koan", "myth"];
          const fi = Math.max(0, order.indexOf(manifest.format || "oral"));
          u.voice = en[fi % en.length];
        }
        u.onend = advance;
        u.onerror = advance;
        window.speechSynthesis.speak(u);
      };
      if (mutedRef.current) {
        timerRef.current = window.setTimeout(advance, scenes[i].duration_ms || 6000);
      } else if (ttsRef.current) {
        ttsBlobUrl(scenes[i].narration).then((url) => {
          if (!playingRef.current) { if (url) URL.revokeObjectURL(url); return; }
          if (!url) { speakWeb(); return; }
          revokeUrl();
          urlRef.current = url;
          const a = audioRef.current;
          if (!a) { speakWeb(); return; }
          a.src = url;
          a.onended = advance;
          a.onerror = () => speakWeb();
          a.play().catch(() => speakWeb());
        });
      } else {
        speakWeb();
      }
    },
    [scenes, manifest.voice, stopAll],
  );

  const onPlayPause = () => {
    if (playing) {
      stopAll();
      setPlaying(false);
    } else {
      playingRef.current = true;
      setPlaying(true);
      playFrom(idx >= scenes.length ? 0 : idx);
    }
  };

  const onRestart = () => {
    stopAll();
    setIdx(0);
    setPlaying(true);
    playingRef.current = true;
    playFrom(0);
  };

  const onRender = async () => {
    setRendering(true);
    setRenderMsg("Submitting render job…");
    try {
      const job = await startRender(manifest);
      setRenderMsg(job.message || job.status);
      if (job.status === "queued" && job.id) {
        for (let k = 0; k < 3; k++) {
          await new Promise((r) => setTimeout(r, 1500));
          const st = await getRender(job.id);
          setRenderMsg(st.message || st.status);
          if (st.video_url) { setRenderMsg("Video ready."); break; }
        }
      }
    } catch {
      setRenderMsg("Render request failed (is the backend reachable?).");
    }
    setRendering(false);
  };

  useEffect(() => () => stopAll(), [stopAll]); // cleanup on unmount
  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    getCapabilities().then((c) => { setTtsOn(c.tts.available); setRenderOn(c.render.available); }).catch(() => {});
  }, []);
  useEffect(() => { ttsRef.current = ttsOn; }, [ttsOn]);
  useEffect(() => {
    if (!speechOK) return;
    const load = () => { voicesRef.current = window.speechSynthesis.getVoices(); };
    load();
    window.speechSynthesis.onvoiceschanged = load;
    return () => { window.speechSynthesis.onvoiceschanged = null; };
  }, []);

  if (!manifest.accepted) {
    return (
      <div className="p-8 text-center" style={{ color: "var(--muted-foreground)" }}>
        <p style={{ fontFamily: "'Fraunces', serif", fontSize: "1.1rem" }}>
          Kathakaar declined to film this.
        </p>
        <p className="mt-2 text-sm">{manifest.reason}</p>
      </div>
    );
  }

  const scene = scenes[Math.min(idx, scenes.length - 1)];
  const pct = scenes.length ? ((idx + (playing ? 0.5 : 1)) / scenes.length) * 100 : 0;

  return (
    <div className="flex flex-col flex-1">
      {/* honest banner */}
      <div
        className="flex items-center gap-2.5 px-5 sm:px-6 py-2.5 border-b shrink-0"
        style={{
          backgroundColor: "color-mix(in srgb, var(--accent) 7%, transparent)",
          borderColor: "color-mix(in srgb, var(--accent) 18%, transparent)",
        }}
      >
        <Volume2 className="w-3.5 h-3.5 shrink-0" style={{ color: "var(--accent)" }} />
        <p className="text-xs leading-snug" style={{ color: "color-mix(in srgb, var(--accent) 82%, transparent)" }}>
          <span className="font-semibold">{manifest.grounded === false ? "Imaginative retelling" : "Grounded retelling"}</span> — narrated from cited
          sources in the <span className="font-semibold">{manifest.format_label}</span> form
          {!speechOK && " · (enable a Chrome/Edge browser for voice)"}
        </p>
      </div>

      <div className="overflow-y-auto flex-1">
        <div className="p-5 sm:p-6 pb-0">
          {/* ── the stage ── */}
          <div className="relative rounded-xl overflow-hidden bg-black" style={{ aspectRatio: "16/9" }}>
            {/* Real moving-video background (Pexels) when available */}
            {manifest.video_url && (
              <video
                src={manifest.video_url}
                autoPlay
                loop
                muted
                playsInline
                className="absolute inset-0 w-full h-full object-cover"
                style={{ opacity: 0.82 }}
              />
            )}
            {/* Ken Burns image layer (fallback when no video) */}
            {!manifest.video_url && imgUrl && imgOk && (
              <img
                src={imgUrl}
                alt={manifest.place}
                onError={() => setImgOk(false)}
                className="absolute inset-0 w-full h-full object-cover"
                style={{
                  opacity: 0.7,
                  transform: kb ? "scale(1.18) translate(-2%, -2%)" : "scale(1.05) translate(2%, 1%)",
                  transition: `transform ${(scene?.duration_ms ?? 8000) + 600}ms linear, opacity 800ms ease`,
                  filter: "saturate(1.05) contrast(1.05)",
                }}
              />
            )}
            {!manifest.video_url && (!imgOk || !imgUrl) ? (
              <div
                className="absolute inset-0"
                style={{
                  background:
                    "radial-gradient(120% 120% at 50% 30%, #2a2118 0%, #14110d 60%, #0a0908 100%)",
                }}
              />
            ) : null}

            {/* procedural particle / light / grain layer */}
            <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />

            {/* per-format colour wash — makes tradition switch visually distinct */}
            <div className="absolute inset-0 pointer-events-none" style={{ backgroundColor: formatColour, transition: "background-color 1s ease" }} />

            {/* gradient for text legibility */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/15 to-black/45" />

            {/* title + badges */}
            <div className="absolute top-3 left-4 sm:top-4 sm:left-5 right-4">
              <h3 className="text-white text-base sm:text-lg leading-tight" style={{ fontFamily: "'Fraunces', serif", fontWeight: 300 }}>
                {manifest.title}
              </h3>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {[manifest.era, manifest.format_origin, manifest.theme].filter(Boolean).map((b, i) => (
                  <span key={i} className="text-[9.5px] px-1.5 py-0.5 rounded" style={{ fontFamily: "'JetBrains Mono', monospace", backgroundColor: "rgba(0,0,0,0.5)", color: "rgba(255,255,255,0.6)" }}>
                    {b}
                  </span>
                ))}
              </div>
            </div>

            {/* animated caption (synced to narration) */}
            <div className="absolute left-0 right-0 bottom-16 px-6 sm:px-10 text-center">
              <p
                key={idx}
                className="inline-block text-white"
                style={{
                  fontFamily: "'Fraunces', serif",
                  fontWeight: 300,
                  fontSize: "clamp(0.95rem, 2.4vw, 1.4rem)",
                  lineHeight: 1.4,
                  textShadow: "0 2px 18px rgba(0,0,0,0.85)",
                  animation: "kthFade 900ms ease",
                }}
              >
                {scene?.narration}
              </p>
            </div>

            {/* center play */}
            {!playing && (
              <button onClick={onPlayPause} className="absolute inset-0 flex items-center justify-center focus:outline-none" aria-label="Play narrated story">
                <div className="w-16 h-16 rounded-full flex items-center justify-center shadow-2xl" style={{ backgroundColor: "var(--primary)" }}>
                  <Play className="w-7 h-7 ml-0.5" style={{ color: "var(--primary-foreground)" }} />
                </div>
              </button>
            )}

            {/* bottom controls */}
            <div className="absolute bottom-0 left-0 right-0 px-4 pt-8 pb-3 sm:px-5" style={{ background: "linear-gradient(to top, rgba(0,0,0,0.9) 0%, transparent 100%)" }}>
              <div className="h-0.5 rounded-full mb-2.5 relative" style={{ backgroundColor: "rgba(255,255,255,0.15)" }}>
                <div className="absolute left-0 top-0 h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: "var(--primary)", transition: "width 500ms linear" }} />
              </div>
              <div className="flex items-center gap-3">
                <button onClick={onPlayPause} aria-label={playing ? "Pause" : "Play"}>
                  {playing ? <Pause className="w-4 h-4 text-white" /> : <Play className="w-4 h-4 text-white" />}
                </button>
                <button onClick={onRestart} aria-label="Restart">
                  <RotateCcw className="w-4 h-4" style={{ color: "rgba(255,255,255,0.7)" }} />
                </button>
                <button onClick={() => setMuted((m) => !m)} aria-label={muted ? "Unmute" : "Mute"}>
                  {muted ? <VolumeX className="w-4 h-4" style={{ color: "rgba(255,255,255,0.7)" }} /> : <Volume2 className="w-4 h-4" style={{ color: "rgba(255,255,255,0.7)" }} />}
                </button>
                <span className="ml-auto" style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.625rem", color: "rgba(255,255,255,0.5)" }}>
                  Scene {Math.min(idx + 1, scenes.length)} / {scenes.length}
                </span>
              </div>
            </div>
          </div>

          {/* scene list */}
          <div className="mt-5 space-y-2">
            {scenes.map((s, i) => (
              <button
                key={i}
                onClick={() => { stopAll(); setPlaying(false); setIdx(i); }}
                className="w-full text-left p-3 rounded-lg border transition-colors"
                style={{
                  borderColor: i === idx ? "var(--primary)" : "var(--border)",
                  backgroundColor: i === idx ? "color-mix(in srgb, var(--primary) 8%, transparent)" : "transparent",
                }}
              >
                <div className="flex items-center gap-2">
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.6rem", color: "var(--muted-foreground)" }}>{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-sm font-medium" style={{ color: "var(--foreground)" }}>{s.title}</span>
                </div>
                <p className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>{s.caption}</p>
              </button>
            ))}
          </div>

          {/* provenance */}
          {manifest.citations && manifest.citations.length > 0 && (
            <div className="mt-4 mb-6 p-3 rounded-lg border" style={{ borderColor: "var(--border)" }}>
              <p className="text-xs font-semibold mb-1.5" style={{ color: "var(--foreground)" }}>Sources</p>
              {manifest.citations.map((c) => (
                <a key={c.n} href={c.url} target="_blank" rel="noopener noreferrer" className="block text-xs hover:underline" style={{ color: "var(--accent)" }}>
                  [{c.n}] {c.title}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* premium voice status + real-video render hook */}
      <div className="px-5 sm:px-6 pb-5 flex items-center gap-2 flex-wrap">
        <button
          onClick={onRender}
          disabled={rendering}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs"
          style={{ borderColor: "var(--border)", color: "var(--foreground)", opacity: rendering ? 0.6 : 1 }}
        >
          {rendering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Clapperboard className="w-3.5 h-3.5" />}
          Render real video{renderOn ? "" : " (beta)"}
        </button>
        {ttsOn && (
          <span className="text-[10px] px-2 py-1 rounded" style={{ fontFamily: "'JetBrains Mono', monospace", backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}>
            premium voice on
          </span>
        )}
        {renderMsg && (
          <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>{renderMsg}</span>
        )}
      </div>
      <audio ref={audioRef} className="hidden" />

      <style>{`@keyframes kthFade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );
}
