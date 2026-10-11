import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { isHarborSource } from "../api/rundownLive";
import type { LiveSnapshot } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { useBrand } from "./BrandContext";
import {
  monitorSources,
  readMonitorSourceId,
  sourceById,
  streamReachable,
  fallbackMp3Stream,
  writeMonitorSourceId,
  type MonitorSource,
  type MonitorSourceId,
} from "./monitorSource";
import { useMonitor, type MonitorState } from "./useMonitor";
import { useRundownMonitor, type RundownGraph } from "./useRundownMonitor";

export type ListenKind = "icecast" | "files" | "harbor";

export type MonitorContextValue = MonitorState & {
  sourceId: MonitorSourceId;
  sources: MonitorSource[];
  setSourceId: (id: MonitorSourceId) => void;
  canChooseSource: boolean;
  listenKind: ListenKind;
  fileMissing: boolean;
  fileLoading: boolean;
};

const MonitorContext = createContext<MonitorContextValue | null>(null);

export function MonitorProvider({
  children,
  lockPublic = false,
}: {
  children: ReactNode;
  lockPublic?: boolean;
}) {
  const brand = useBrand();
  const sources = useMemo(() => {
    const all = monitorSources(brand);
    if (!lockPublic) return all;
    return all.filter((source) => source.id === "public");
  }, [brand, lockPublic]);
  const [sourceId, setSourceIdState] = useState<MonitorSourceId>(
    () => (lockPublic ? "public" : readMonitorSourceId() ?? "public"),
  );
  const source = sourceById(sources, sourceId);
  const [listenStream, setListenStream] = useState(source.stream);
  const live = useApiJson<LiveSnapshot>("/live.json", 2000);
  const filesWanted = sourceId === "files";
  const harbor = filesWanted && isHarborSource(live.data?.source);
  const filesOn = filesWanted && !harbor;
  const filesAudioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    setListenStream(source.stream);
    if (!source.stream.includes("studio.wav")) return;
    let cancelled = false;
    void streamReachable(source.stream, 800).then((ok) => {
      if (cancelled || ok) return;
      setListenStream(fallbackMp3Stream(source.stream));
    });
    return () => {
      cancelled = true;
    };
  }, [source.id, source.stream]);

  const icecast = useMonitor(
    listenStream,
    source.nowUrl,
    source.statusUrl,
    !filesOn,
    `${source.id}:${listenStream}`,
  );
  const graph = useMemo<RundownGraph>(
    () => ({
      applyMute: icecast.applyMute,
      ensureGraph: icecast.ensureGraph,
      connectElement: icecast.connectElement,
      connectNode: icecast.connectNode,
      getContext: icecast.getContext,
      resumeContext: icecast.resumeContext,
      isMuted: icecast.isMuted,
    }),
    [
      icecast.applyMute,
      icecast.connectElement,
      icecast.connectNode,
      icecast.ensureGraph,
      icecast.getContext,
      icecast.isMuted,
      icecast.resumeContext,
    ],
  );
  const rundown = useRundownMonitor({
    enabled: filesOn,
    audioRef: filesAudioRef,
    graph,
    live: live.data,
  });

  const setSourceId = useCallback(
    (id: MonitorSourceId) => {
      if (lockPublic) return;
      writeMonitorSourceId(id);
      setSourceIdState(id);
      void icecast.resumeContext();
      if (id !== "files") void icecast.start();
    },
    [icecast.resumeContext, icecast.start, lockPublic],
  );

  useEffect(() => {
    setSourceIdState(lockPublic ? "public" : readMonitorSourceId() ?? "public");
  }, [lockPublic]);

  const listenKind: ListenKind = harbor ? "harbor" : filesOn ? "files" : "icecast";
  const toggleMute = filesOn ? rundown.toggleMute : icecast.toggleMute;

  const value = useMemo(
    () => ({
      ...icecast,
      live: filesOn ? rundown.live : icecast.live,
      now: filesOn ? rundown.now : icecast.now,
      remaining: filesOn ? rundown.remaining : icecast.remaining,
      lagMs: filesOn ? rundown.lagMs : icecast.lagMs,
      toggleMute,
      sourceId: source.id,
      sources,
      setSourceId,
      canChooseSource: !lockPublic,
      listenKind,
      fileMissing: filesOn && rundown.missing,
      fileLoading: filesOn && rundown.loading,
    }),
    [
      filesOn,
      icecast,
      listenKind,
      rundown.lagMs,
      rundown.live,
      rundown.loading,
      rundown.missing,
      rundown.now,
      rundown.remaining,
      rundown.toggleMute,
      setSourceId,
      lockPublic,
      source.id,
      sources,
      toggleMute,
    ],
  );

  return (
    <MonitorContext.Provider value={value}>
      <audio
        ref={icecast.audioRef}
        className="app-monitor-audio"
        preload="none"
        playsInline
        crossOrigin="anonymous"
      />
      <audio
        ref={filesAudioRef}
        className="app-monitor-audio"
        preload="none"
        playsInline
      />
      {children}
    </MonitorContext.Provider>
  );
}

export function useMonitorState(): MonitorContextValue {
  const value = useContext(MonitorContext);
  if (!value) throw new Error("monitor");
  return value;
}
