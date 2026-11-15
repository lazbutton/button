import { useEffect, useRef, useState } from "react";
import { apiPostJson, ApiRequestError } from "../../api/client";
import {
  settled,
  uploadKey,
  uploadsBody,
  UPLOADS_FOLLOW_MS,
  UPLOADS_JSON,
  type UploadFileReport,
  type UploadReport,
} from "../../api/uploadReport";

/** Toutes les cinq secondes, comme l'activité du dépôt. */
const EVERY_MS = 5000;

type Sent = { dest: string; name: string };

/**
 * Ce que la banque sait des fichiers envoyés (FON-82), redemandé tant qu'un fichier n'a pas fini son
 * chemin : promu, indexé, puis cherché en ligne. `enabled` : le rangement ouvert, et le droit de lire les
 * fiches. Un moteur plus ancien, ou le rangement fermé entre-temps, et la file n'en dit plus rien.
 */
export function useUploadReport(sent: Sent[], enabled: boolean) {
  const [reports, setReports] = useState<Record<string, UploadFileReport>>({});
  const [fichesOn, setFichesOn] = useState(false);
  const [problem, setProblem] = useState("");
  const [gone, setGone] = useState(false);
  const firstSeen = useRef(new Map<string, number>());
  const latest = useRef({ reports, fichesOn });
  latest.current = { reports, fichesOn };
  const sentKey = sent.map((one) => uploadKey(one.dest, one.name)).join("\u0001");

  useEffect(() => {
    if (!enabled || gone || !sent.length) return;
    let live = true;
    const now = Date.now();
    for (const one of sent) {
      const key = uploadKey(one.dest, one.name);
      if (!firstSeen.current.has(key)) firstSeen.current.set(key, now);
    }
    const ask = async () => {
      const { reports: known, fichesOn: on } = latest.current;
      const pending = sent.filter((one) => {
        const key = uploadKey(one.dest, one.name);
        const report = known[key];
        if (report && settled(report, on)) return false;
        return Date.now() - (firstSeen.current.get(key) ?? 0) < UPLOADS_FOLLOW_MS;
      });
      if (!pending.length) return;
      try {
        const answer = await apiPostJson<UploadReport>(UPLOADS_JSON, uploadsBody(pending));
        if (!live) return;
        setFichesOn(answer.fiches);
        setReports((before) => {
          const next = { ...before };
          for (const file of answer.files) next[uploadKey(file.dest, file.name)] = file;
          return next;
        });
        setProblem("");
      } catch (caught) {
        if (!live) return;
        if (caught instanceof ApiRequestError && (caught.status === 404 || caught.status === 409)) {
          setGone(true);
          return;
        }
        setProblem("La banque ne dit pas encore ce qu'elle sait de ces fichiers : nouvel essai dans un instant.");
      }
    };
    void ask();
    const timer = window.setInterval(() => void ask(), EVERY_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
    // La liste des fichiers envoyés, par son contenu : un rendu de la file ne relance rien.
  }, [sentKey, enabled, gone]);

  return { reports, fichesOn, problem: enabled && !gone ? problem : "" };
}
