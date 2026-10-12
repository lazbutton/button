import { useEffect, useRef } from "react";
import { cssVar, withAlpha } from "../lib/cssColor";

type Props = {
  analyserL: AnalyserNode | null;
  analyserR: AnalyserNode | null;
  live: boolean;
};

const MIN_DB = -48;
const YELLOW_DB = -12;
const RED_DB = -6;
const CLIP_DB = -0.3;
const HOLD_MS = 1200;
const VU_ATTACK_MS = 90;
const VU_RELEASE_MS = 280;
/** Une diode : 2 px de large, 1 px d'écart. */
const LED = 2;
const STEP = 3;
const LANE = 5;
const GAP = 2;

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

/** Vumètre du casque, deux rangées de diodes (L en haut, R en bas). Rouge seulement au-delà de −6 dBFS. */
export function VuMeter({ analyserL, analyserR, live }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

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
    let lastT = 0;

    function resize() {
      const dpr = window.devicePixelRatio || 1;
      cssW = surface.clientWidth;
      cssH = surface.clientHeight;
      surface.width = Math.max(1, Math.floor(cssW * dpr));
      surface.height = Math.max(1, Math.floor(cssH * dpr));
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function paint(left: number, right: number, peakL: number, peakR: number) {
      const ink = cssVar(surface, "--app-text", "#0a0a0a");
      const ok = cssVar(surface, "--app-vu-ok", "#3ecf8e");
      const warn = cssVar(surface, "--app-vu-warn", "#f0e24a");
      const hot = cssVar(surface, "--app-vu-hot", "#ff7a45");
      const clip = cssVar(surface, "--app-vu-clip", "#ff4d4d");
      const off = withAlpha(ink, 0.12);
      const count = Math.max(4, Math.floor((cssW + STEP - LED) / STEP));
      const top = Math.max(0, Math.round((cssH - LANE * 2 - GAP) / 2));
      g.clearRect(0, 0, cssW, cssH);

      const colorAt = (index: number) => {
        const db = MIN_DB + ((index + 1) / count) * -MIN_DB;
        if (db > CLIP_DB) return clip;
        if (db > RED_DB) return hot;
        if (db > YELLOW_DB) return warn;
        return ok;
      };
      const lane = (y: number, vu: number, peak: number) => {
        const lit = unit(vu) * count;
        const peakAt = peak > MIN_DB + 1 ? Math.min(count - 1, Math.floor(unit(peak) * count)) : -1;
        for (let index = 0; index < count; index++) {
          g.fillStyle = index < lit || index === peakAt ? colorAt(index) : off;
          g.fillRect(index * STEP, y, LED, LANE);
        }
      };
      lane(top, left, peakL);
      lane(top + LANE + GAP, right, peakR);
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
        holdL = MIN_DB;
        holdR = MIN_DB;
        paint(vuL, vuR, holdL, holdR);
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
      const right = rightRaw.peak < MIN_DB + 1 && left.peak > MIN_DB + 6 ? left : rightRaw;
      vuL = reduce.matches ? left.rms : follow(vuL, left.rms, dt, VU_ATTACK_MS, VU_RELEASE_MS);
      vuR = reduce.matches ? right.rms : follow(vuR, right.rms, dt, VU_ATTACK_MS, VU_RELEASE_MS);
      if (left.peak >= holdL || now - holdLAt > HOLD_MS) {
        holdL = left.peak;
        holdLAt = now;
      }
      if (right.peak >= holdR || now - holdRAt > HOLD_MS) {
        holdR = right.peak;
        holdRAt = now;
      }
      paint(vuL, vuR, holdL, holdR);
      raf = requestAnimationFrame(tick);
    }

    resize();
    paint(MIN_DB, MIN_DB, MIN_DB, MIN_DB);
    const ro = new ResizeObserver(resize);
    ro.observe(surface);
    raf = requestAnimationFrame(tick);
    return () => {
      ro.disconnect();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [analyserL, analyserR, live]);

  return (
    <span className="app-vu" title="Niveau du casque, gauche et droite. Rouge au-delà de −6 dBFS.">
      <canvas ref={canvasRef} className="app-vu-canvas" width={56} height={14} aria-hidden="true" />
    </span>
  );
}
