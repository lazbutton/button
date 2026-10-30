import { useCallback, useEffect, useRef, useState } from "react";
import { previewFailure, previewUrl } from "../api/antenneDesk";
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

  // play() et l'élément audio peuvent signaler le même échec : le premier arrête
  // la pré-écoute et dit pourquoi. Un titre déjà arrêté ou remplacé ne dit plus rien.
  const fail = useCallback((src: string | null) => {
    if (!src || audioRef.current?.getAttribute("src") !== src) return;
    stopRef.current();
    void fetch(src, { method: "HEAD", cache: "no-store", signal: AbortSignal.timeout(5000) })
      .then((response) => response.status, () => null)
      .then((status) => onErrorRef.current(previewFailure(status)));
  }, []);

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
        // Une requête qui échoue en cours de lecture (session expirée, réseau coupé)
        // ne se voit qu'ici : play() a déjà réussi. Un événement en retard, arrivé
        // après un arrêt ou un changement de titre, ne porte plus d'erreur.
        audio.addEventListener("error", () => {
          const current = audioRef.current;
          if (current?.error) fail(current.getAttribute("src"));
        });
        audioRef.current = audio;
      }
      if (restoreRef.current === null) {
        restoreRef.current = isMuted();
        applyMute(true);
      }
      const src = previewUrl(id);
      audio.src = src;
      setPlayingId(id);
      void audio.play().catch((caught: unknown) => {
        // Un autre titre a pris la place : rien à signaler.
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        fail(src);
      });
    },
    [applyMute, fail, isMuted, playingId, stop],
  );

  useEffect(() => () => stopRef.current(), []);

  return { playingId, toggle, stop };
}
