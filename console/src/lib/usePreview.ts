import { useCallback, useEffect, useRef, useState } from "react";
import { previewUrl } from "../api/antenneDesk";
import { useMonitorState } from "./MonitorContext";

/**
 * Pré-écoute d'un titre de la bibliothèque, dans le casque seulement.
 * Le casque d'antenne se tait pendant la pré-écoute, puis reprend où il en était.
 */
export function usePreview(onError: (message: string) => void) {
  const { applyMute, isMuted } = useMonitorState();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const restoreRef = useRef<boolean | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const stop = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    setPlayingId(null);
    if (restoreRef.current !== null) {
      applyMute(restoreRef.current);
      restoreRef.current = null;
    }
  }, [applyMute]);

  const stopRef = useRef(stop);
  stopRef.current = stop;

  const toggle = useCallback(
    (id: string) => {
      if (playingId === id) {
        stop();
        return;
      }
      let audio = audioRef.current;
      if (!audio) {
        audio = new Audio();
        audio.preload = "auto";
        audio.addEventListener("ended", () => stopRef.current());
        audioRef.current = audio;
      }
      if (restoreRef.current === null) {
        restoreRef.current = isMuted();
        applyMute(true);
      }
      audio.src = previewUrl(id);
      setPlayingId(id);
      void audio.play().catch((caught: unknown) => {
        // Un autre titre a pris la place : rien à signaler.
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        stopRef.current();
        onErrorRef.current("Pré-écoute impossible : le fichier ne répond pas.");
      });
    },
    [applyMute, isMuted, playingId, stop],
  );

  useEffect(() => () => stopRef.current(), []);

  return { playingId, toggle, stop };
}
