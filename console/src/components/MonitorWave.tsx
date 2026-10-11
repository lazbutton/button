import { SpeakerLoudIcon, SpeakerOffIcon } from "@radix-ui/react-icons";
import { displayNow, formatRemain } from "../lib/nowPlaying";
import { useMonitorState } from "../lib/MonitorContext";
import { useApiJson } from "../api/useApiJson";
import type { LiveSnapshot } from "../api/types";
import { Oscilloscope } from "./Oscilloscope";
import { VuMeter } from "./VuMeter";

export function MonitorWave() {
  const {
    analyser,
    analyserL,
    analyserR,
    live,
    muted,
    lagMs,
    toggleMute,
    now,
    remaining,
    listenKind,
    fileMissing,
    fileLoading,
  } = useMonitorState();
  const rt = useApiJson<LiveSnapshot>("/live.json", 2000);
  const fromDesk =
    rt.data && rt.data.status !== "offline"
      ? displayNow({
          title: rt.data.title,
          artist: rt.data.artist,
          album: rt.data.album,
        })
      : null;
  const label = muted ? "Cliquer pour entendre" : "Couper le son";
  const waiting =
    listenKind === "files" && now.startedAt != null && now.startedAt > Date.now();
  const hint = muted
    ? label
    : fileMissing
      ? "Fichier introuvable"
      : listenKind === "harbor"
        ? "Live plateau · Icecast"
        : listenKind === "files"
          ? fileLoading
            ? "Décodage"
            : waiting && remaining != null
              ? `dans ${formatRemain(remaining).slice(1)}`
              : lagMs != null
                ? `Horloge ${Math.abs(lagMs)} ms`
                : remaining != null
                  ? `Horloge ${formatRemain(remaining)}`
                  : "Conducteur · horloge"
          : lagMs != null
            ? `Casque ${Math.max(0, lagMs)} ms`
            : label;
  const title = (
    (listenKind === "files" ? now.title || fromDesk?.title : fromDesk?.title || now.title) || ""
  ).trim() || "—";
  const artist = (
    (listenKind === "files" ? now.artist || fromDesk?.artist : fromDesk?.artist || now.artist) || ""
  ).trim();

  return (
    <div
      className={`app-monitor${live ? " is-live" : ""}${muted ? " is-muted" : ""}`}
    >
      <button
        type="button"
        className="app-monitor-hit"
        onClick={toggleMute}
        aria-pressed={!muted}
        aria-label={label}
        title={hint}
      >
        <Oscilloscope analyser={analyser} playing={live} className="app-monitor-wave" />
        <span className="app-monitor-hint">
          {muted ? <SpeakerOffIcon /> : <SpeakerLoudIcon />}
          <span>{hint}</span>
        </span>
      </button>
      <VuMeter analyserL={analyserL} analyserR={analyserR} live={live} size="compact" />
      <div className="app-monitor-now" aria-live="polite">
        <p className="app-monitor-title" title={title}>
          {title}
        </p>
        <div className="app-monitor-meta">
          <p className="app-monitor-artist" title={artist || undefined}>
            {artist || " "}
          </p>
          {remaining !== null ? (
            <p className="app-monitor-remain" aria-label={`Temps restant ${formatRemain(remaining)}`}>
              {formatRemain(remaining)}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
