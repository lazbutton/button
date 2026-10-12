import { Headphones, Plus, Radio, Search, Square, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { mmss } from "../../api/antenneDesk";
import { pushDeskRecent, readDeskRecents } from "../../api/deskRecents";
import {
  deskKindFromHit,
  LIBRARY_DRAG_MIME,
  LIBRARY_TABS,
  labelsFromHit,
  librarySearch,
  type LibraryHit,
  type LibraryTabId,
} from "../../api/library";
import { usePreview } from "../../lib/usePreview";

const TABS = LIBRARY_TABS.filter(
  (tab) => tab.id === "all" || tab.id === "musique" || tab.id === "jingle" || tab.id === "archives",
);

/** Chercher, pré-écouter, mettre à la suite ou diffuser tout de suite. */
export function LibraryPanel({
  fireDisabled,
  onInsertNext,
  onFireNow,
  onNotice,
}: {
  /** Le direct tient l'antenne : rien ne peut le couper d'ici. */
  fireDisabled: boolean;
  onInsertNext: (hit: LibraryHit) => void;
  onFireNow: (hit: LibraryHit) => void;
  onNotice: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<LibraryTabId>("all");
  const [hits, setHits] = useState<LibraryHit[]>([]);
  const [recents, setRecents] = useState<LibraryHit[]>(() => readDeskRecents());
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [active, setActive] = useState(0);
  const preview = usePreview(onNotice);

  const remember = useCallback((hit: LibraryHit) => setRecents(pushDeskRecent(hit)), []);

  const insert = useCallback(
    (hit: LibraryHit) => {
      remember(hit);
      onInsertNext(hit);
    },
    [onInsertNext, remember],
  );

  const fire = useCallback(
    (hit: LibraryHit) => {
      if (fireDisabled) return;
      remember(hit);
      preview.stop();
      onFireNow(hit);
    },
    [fireDisabled, onFireNow, preview, remember],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void librarySearch({ q: query, tab, limit: 40 })
        .then((result) => {
          setHits(result.hits);
          setTotal(typeof result.estimatedTotalHits === "number" ? result.estimatedTotalHits : result.hits.length);
          setError(null);
          setReady(true);
          setActive(0);
        })
        .catch((caught: unknown) => {
          setHits([]);
          setTotal(null);
          setReady(true);
          setError(caught instanceof Error ? caught.message : "Recherche impossible.");
        });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [query, tab, attempt]);

  // « / » amène à la recherche, où qu'on soit sur la page.
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target?.isContentEditable) return;
      event.preventDefault();
      inputRef.current?.focus();
      inputRef.current?.select();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const shown = hits.length;
  const count = !ready
    ? "Recherche…"
    : error
      ? ""
      : total != null && total > shown
        ? `${shown} sur ${total}`
        : `${shown} résultat${shown > 1 ? "s" : ""}`;
  const showRecents = !query.trim() && recents.length > 0 && !error;

  return (
    <section className="ant-panel ant-lib" aria-labelledby="ant-lib-title">
      <header className="ant-panel-head">
        <h2 id="ant-lib-title">Bibliothèque</h2>
        <span className="ant-panel-count" aria-live="polite">
          {count}
        </span>
      </header>

      <div className="ant-lib-tools">
        <label className="ant-search">
          <Search size={16} aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            placeholder="Titre, artiste…"
            aria-label="Chercher dans la bibliothèque"
            aria-keyshortcuts="/"
            aria-controls="ant-lib-results"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const next = Math.min(Math.max(0, active + (event.key === "ArrowDown" ? 1 : -1)), hits.length - 1);
                setActive(next);
                // Seule la navigation au clavier fait défiler jusqu'à la ligne active.
                resultsRef.current
                  ?.querySelector<HTMLElement>(`[data-index="${next}"]`)
                  ?.scrollIntoView({ block: "nearest" });
              } else if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                const hit = hits[active];
                if (hit) insert(hit);
              } else if (event.key === "Escape") {
                event.preventDefault();
                setQuery("");
                inputRef.current?.blur();
              }
            }}
          />
          {query ? (
            <button
              type="button"
              className="ant-search-clear"
              aria-label="Effacer la recherche"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          ) : (
            <kbd aria-hidden="true">/</kbd>
          )}
        </label>
        <div className="ant-tabs" role="tablist" aria-label="Filtrer">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        {showRecents ? (
          <div className="ant-recents" aria-label="Récemment utilisés">
            <span className="ant-recents-k">Récents</span>
            {recents.map((hit) => (
              <button
                key={`r-${hit.path}`}
                type="button"
                title="Mettre à la suite"
                onClick={() => insert(hit)}
              >
                {labelsFromHit(hit).title || hit.path}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="ant-lib-results" id="ant-lib-results" ref={resultsRef}>
        {error ? (
          <div className="ant-empty is-error">
            <strong>Le catalogue ne répond pas.</strong>
            <span>{error} Si ça dure, un admin regarde Réglages → Automate.</span>
            <button type="button" className="ant-btn ant-btn--small" onClick={() => setAttempt((value) => value + 1)}>
              Réessayer
            </button>
          </div>
        ) : ready && !shown ? (
          <div className="ant-empty">
            <strong>Aucun titre.</strong>
            <span>Essaie un autre mot, ou un autre filtre.</span>
          </div>
        ) : (
          <ol className="ant-hits">
            {hits.map((hit, index) => (
              <HitRow
                key={hit.id || hit.path}
                index={index}
                hit={hit}
                active={index === active}
                previewing={preview.playingId === hit.id}
                fireDisabled={fireDisabled}
                onInsert={() => {
                  setActive(index);
                  insert(hit);
                }}
                onPreview={() => preview.toggle(hit.id)}
                onFire={() => fire(hit)}
              />
            ))}
          </ol>
        )}
      </div>

      <footer className="ant-panel-foot">
        <span>
          <kbd>Entrée</kbd> à la suite · glisser sur la file pour placer
        </span>
      </footer>
    </section>
  );
}

function HitRow({
  index,
  hit,
  active,
  previewing,
  fireDisabled,
  onInsert,
  onPreview,
  onFire,
}: {
  index: number;
  hit: LibraryHit;
  active: boolean;
  previewing: boolean;
  fireDisabled: boolean;
  onInsert: () => void;
  onPreview: () => void;
  onFire: () => void;
}) {
  const kind = deskKindFromHit(hit);
  const labels = labelsFromHit(hit);
  const title = labels.title || "ce titre";

  return (
    <li data-index={index} className={`${active ? "is-active" : ""}${previewing ? " is-preview" : ""}`}>
      <button
        type="button"
        className="ant-hit"
        draggable
        aria-label={`Mettre ${title} à la suite`}
        onDragStart={(event) => {
          event.dataTransfer.effectAllowed = "copy";
          event.dataTransfer.setData(LIBRARY_DRAG_MIME, JSON.stringify(hit));
          event.dataTransfer.setData("text/plain", hit.path);
        }}
        onClick={onInsert}
      >
        <span className={`ant-kind is-${kind}`} aria-hidden="true" />
        <span className="ant-hit-copy">
          <span className="ant-hit-title">{labels.title || "—"}</span>
          {labels.artist ? <span className="ant-hit-artist">{labels.artist}</span> : null}
        </span>
        <span className="ant-hit-dur">{mmss(hit.duration || 0)}</span>
        <Plus className="ant-hit-add" size={15} aria-hidden="true" />
      </button>
      <button
        type="button"
        className="ant-icon-btn"
        aria-pressed={previewing}
        aria-label={previewing ? `Arrêter la pré-écoute de ${title}` : `Pré-écouter ${title} au casque`}
        title={previewing ? "Arrêter la pré-écoute" : "Pré-écoute au casque (les auditeurs n’entendent rien)"}
        onClick={onPreview}
      >
        {previewing ? <Square size={13} aria-hidden="true" /> : <Headphones size={15} aria-hidden="true" />}
      </button>
      <button
        type="button"
        className="ant-fire"
        disabled={fireDisabled}
        aria-label={`Diffuser ${title} maintenant`}
        title={fireDisabled ? "Le direct tient l’antenne" : "Diffuser maintenant : coupe le titre en cours"}
        onClick={onFire}
      >
        <Radio size={15} aria-hidden="true" />
        <span>Diffuser</span>
      </button>
    </li>
  );
}
