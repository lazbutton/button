import { useEffect, useRef } from "react";
import { cssVar, withAlpha } from "../lib/cssColor";

type Props = {
  analyserL: AnalyserNode | null;
  analyserR: AnalyserNode | null;
  live: boolean;
  size?: "compact" | "desk";
};

const MIN_DB = -48;
const YELLOW_DB = -12;
const RED_DB = -6;
const CLIP_DB = -0.3;
const HOLD_MS = 1200;
const CLIP_HOLD_MS = 1600;
const VU_ATTACK_MS = 90;
const VU_RELEASE_MS = 280;
const TICKS = [0, -6, -12, -24] as const;

function dbFromAmp(amp: number): number {
  if (amp < 1e-6) return MIN_DB;
  return 20 * Math.log10(amp);
}

function readChannel(analyser: AnalyserNode, buf: Float32Array<ArrayBuffer>) {
  analyser.getFloatTimeDomainData(buf);
  let peak = 0;
  let sum = 0;
  for (let i = 0; i < buf.length; i++) {
    const v = buf[i] ?? 0;
    const a = Math.abs(v);
    if (a > peak) peak = a;
    sum += v * v;
  }
  return {
    peak: dbFromAmp(peak),
    rms: dbFromAmp(Math.sqrt(sum / Math.max(1, buf.length))),
  };
}

function unit(db: number): number {
  return Math.min(1, Math.max(0, (db - MIN_DB) / -MIN_DB));
}

function follow(prev: number, next: number, dt: number, attack: number, release: number) {
  const tau = next > prev ? attack : release;
  const a = 1 - Math.exp(-dt / Math.max(1, tau));
  return prev + (next - prev) * a;
}

function meterGradient(
  g: CanvasRenderingContext2D,
  el: Element,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
) {
  const grd = g.createLinearGradient(x0, y0, x1, y1);
  grd.addColorStop(0, cssVar(el, "--app-ok", "#2ea56a"));
  grd.addColorStop(unit(YELLOW_DB), cssVar(el, "--app-vu-ok", "#3ecf8e"));
  grd.addColorStop(unit(RED_DB), cssVar(el, "--app-vu-warn", "#f0e24a"));
  grd.addColorStop(0.94, cssVar(el, "--app-vu-hot", "#ff7a45"));
  grd.addColorStop(1, cssVar(el, "--app-vu-clip", "#ff4d4d"));
  return grd;
}

export function VuMeter({ analyserL, analyserR, live, size = "compact" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const desk = size === "desk";

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const surface = canvas;
    const g = ctx;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    let raf = 0;
    let cssW = 0;
    let cssH = 0;
    let bufL: Float32Array<ArrayBuffer> | null = null;
    let bufR: Float32Array<ArrayBuffer> | null = null;
    let vuL = MIN_DB;
    let vuR = MIN_DB;
    let holdL = MIN_DB;
    let holdR = MIN_DB;
    let holdLAt = 0;
    let holdRAt = 0;
    let clipUntil = 0;
    let lastT = 0;

    function resize() {
      const dpr = window.devicePixelRatio || 1;
      cssW = surface.clientWidth;
      cssH = surface.clientHeight;
      surface.width = Math.max(1, Math.floor(cssW * dpr));
      surface.height = Math.max(1, Math.floor(cssH * dpr));
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function palette() {
      const ink = cssVar(surface, "--app-text", "#0a0a0a");
      const clipCol = cssVar(surface, "--app-vu-clip", "#ff4d4d");
      const hot = cssVar(surface, "--app-vu-hot", "#ff7a45");
      return { ink, clipCol, hot };
    }

    function laneH(
      x: number,
      y: number,
      w: number,
      h: number,
      vu: number,
      peak: number,
      name: string,
    ) {
      const { ink, clipCol } = palette();
      g.fillStyle = withAlpha(ink, 0.05);
      g.fillRect(x, y, w, h);
      const grd = meterGradient(g, surface, x, y, x + w, y);
      g.globalAlpha = 0.38;
      g.fillStyle = grd;
      g.fillRect(x, y, w, h);
      g.globalAlpha = 1;
      const fillW = unit(vu) * w;
      if (fillW > 0) {
        g.save();
        g.beginPath();
        g.rect(x, y, fillW, h);
        g.clip();
        g.fillStyle = grd;
        g.fillRect(x, y, w, h);
        g.restore();
      }
      for (const tick of TICKS) {
        const tx = x + unit(tick) * w;
        g.fillStyle = tick === 0 ? withAlpha(clipCol, 0.7) : withAlpha(ink, 0.18);
        g.fillRect(tx, y, 1, h);
      }
      const px = Math.min(x + w - 1, x + unit(peak) * w);
      g.fillStyle = peak >= CLIP_DB ? clipCol : ink;
      g.fillRect(px - 1, y, 2, h);
      g.fillStyle = withAlpha(ink, 0.62);
      g.font = "700 9px ui-sans-serif, system-ui, sans-serif";
      g.textAlign = "left";
      g.textBaseline = "middle";
      g.fillText(name, 2, y + h / 2);
    }

    function laneV(
      x: number,
      top: number,
      w: number,
      height: number,
      vu: number,
      peak: number,
    ) {
      const { ink, clipCol } = palette();
      const bottom = top + height;
      g.fillStyle = withAlpha(ink, 0.06);
      g.fillRect(x, top, w, height);
      const fillH = unit(vu) * height;
      if (fillH > 0) {
        g.save();
        g.beginPath();
        g.rect(x, bottom - fillH, w, fillH);
        g.clip();
        g.fillStyle = meterGradient(g, surface, x, bottom, x, top);
        g.fillRect(x, top, w, height);
        g.restore();
      }
      for (const tick of TICKS) {
        const ty = bottom - unit(tick) * height;
        g.fillStyle = tick === 0 ? withAlpha(clipCol, 0.55) : withAlpha(ink, 0.12);
        g.fillRect(x, ty, w, 1);
      }
      const py = bottom - unit(peak) * height;
      g.fillStyle = peak >= CLIP_DB ? clipCol : ink;
      g.fillRect(x, py - 1, w, 2);
    }

    function paint(left: number, right: number, peakL: number, peakR: number, clip: boolean) {
      const { ink, clipCol, hot } = palette();
      g.clearRect(0, 0, cssW, cssH);
      g.textBaseline = "alphabetic";
      if (!desk) {
        const labelW = 12;
        const readW = 48;
        const scaleH = 12;
        const gap = 3;
        const x = labelW;
        const w = Math.max(8, cssW - labelW - readW);
        const h = Math.max(7, (cssH - scaleH - gap * 2 - 1) / 2);
        g.font = "600 9px ui-sans-serif, system-ui, sans-serif";
        g.textAlign = "center";
        g.textBaseline = "alphabetic";
        for (const tick of TICKS) {
          const tx = x + unit(tick) * w;
          g.fillStyle = tick >= RED_DB ? withAlpha(hot, 0.95) : withAlpha(ink, 0.72);
          g.fillText(tick === 0 ? "0" : `${tick}`, tx, scaleH - 2);
        }
        laneH(x, scaleH, w, h, left, peakL, "L");
        laneH(x, scaleH + h + gap, w, h, right, peakR, "R");
        g.textAlign = "right";
        g.textBaseline = "middle";
        const shown = Math.max(peakL, peakR);
        g.fillStyle = clip ? clipCol : withAlpha(ink, 0.88);
        g.font = "700 12px ui-sans-serif, system-ui, sans-serif";
        g.fillText(clip ? "CLIP" : `${Math.round(shown)}`, cssW - 3, cssH / 2 - 6);
        g.font = "600 8px ui-sans-serif, system-ui, sans-serif";
        g.fillStyle = clip ? clipCol : withAlpha(ink, 0.55);
        g.fillText("dBFS", cssW - 3, cssH / 2 + 8);
        return;
      }

      const gutter = 10;
      const label = 18;
      const top = 18;
      const bottom = cssH - 22;
      const height = Math.max(8, bottom - top);
      const barW = Math.max(10, (cssW - gutter - label) / 2 - 4);
      const xL = label;
      const xR = label + barW + gutter;
      laneV(xL, top, barW, height, left, peakL);
      laneV(xR, top, barW, height, right, peakR);
      g.fillStyle = withAlpha(ink, 0.45);
      g.font = "600 9px ui-sans-serif, system-ui, sans-serif";
      g.textAlign = "right";
      for (const tick of TICKS) {
        const y = bottom - unit(tick) * height;
        g.fillText(`${tick}`, label - 3, y + 3);
      }
      g.textAlign = "center";
      g.fillStyle = withAlpha(ink, 0.55);
      g.fillText("L", xL + barW / 2, cssH - 6);
      g.fillText("R", xR + barW / 2, cssH - 6);
      g.textAlign = "left";
      g.font = "700 10px ui-sans-serif, system-ui, sans-serif";
      const shown = Math.max(peakL, peakR);
      g.fillStyle = clip ? clipCol : withAlpha(ink, 0.78);
      g.fillText(clip ? "CLIP" : `${Math.round(shown)} dB`, 0, 12);
    }

    function tick(now: number) {
      raf = 0;
      const dt = lastT ? Math.min(80, now - lastT) : 16;
      lastT = now;
      const leftNode = analyserL;
      const rightNode = analyserR ?? analyserL;
      if (!live || !leftNode || !rightNode) {
        vuL = follow(vuL, MIN_DB, dt, VU_ATTACK_MS, VU_RELEASE_MS);
        vuR = follow(vuR, MIN_DB, dt, VU_ATTACK_MS, VU_RELEASE_MS);
        paint(vuL, vuR, holdL, holdR, false);
        raf = requestAnimationFrame(tick);
        return;
      }
      if (!bufL || bufL.length !== leftNode.fftSize) {
        bufL = new Float32Array(new ArrayBuffer(leftNode.fftSize * 4));
      }
      if (!bufR || bufR.length !== rightNode.fftSize) {
        bufR = new Float32Array(new ArrayBuffer(rightNode.fftSize * 4));
      }
      const left = readChannel(leftNode, bufL);
      const rightRaw = readChannel(rightNode, bufR);
      const right =
        rightRaw.peak < MIN_DB + 1 && left.peak > MIN_DB + 6 ? left : rightRaw;
      vuL = reduce.matches ? left.rms : follow(vuL, left.rms, dt, VU_ATTACK_MS, VU_RELEASE_MS);
      vuR = reduce.matches ? right.rms : follow(vuR, right.rms, dt, VU_ATTACK_MS, VU_RELEASE_MS);
      if (left.peak >= CLIP_DB || right.peak >= CLIP_DB) clipUntil = now + CLIP_HOLD_MS;
      if (left.peak >= holdL || now - holdLAt > HOLD_MS) {
        holdL = left.peak;
        holdLAt = now;
      }
      if (right.peak >= holdR || now - holdRAt > HOLD_MS) {
        holdR = right.peak;
        holdRAt = now;
      }
      if (!reduce.matches) {
        holdL = Math.max(left.peak, holdL - 0.08);
        holdR = Math.max(right.peak, holdR - 0.08);
      }
      paint(vuL, vuR, holdL, holdR, now < clipUntil);
      raf = requestAnimationFrame(tick);
    }

    resize();
    paint(MIN_DB, MIN_DB, MIN_DB, MIN_DB, false);
    const ro = new ResizeObserver(resize);
    ro.observe(surface);
    raf = requestAnimationFrame(tick);
    return () => {
      ro.disconnect();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [analyserL, analyserR, live, desk]);

  return (
    <div
      className={`app-vu app-vu--${size}`}
      title="Vumètre du flux Icecast. Barre = VU (RMS). Trait = crête. Rouge seulement au-delà de −6 dBFS."
    >
      <canvas
        ref={canvasRef}
        className="app-vu-canvas"
        width={desk ? 88 : 240}
        height={desk ? 168 : 52}
        aria-hidden="true"
      />
      {desk ? (
        <p className="app-vu-caption">Antenne · Icecast</p>
      ) : (
        <span className="ui-visually-hidden">Vumètre d’antenne, échelle en dBFS</span>
      )}
    </div>
  );
}
