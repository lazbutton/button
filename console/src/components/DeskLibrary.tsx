import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Search } from "lucide-react";
import { kindLabel } from "../api/clockMeta";
import { pushDeskRecent, readDeskRecents } from "../api/deskRecents";
import { formatMmSs } from "../lib/parisClock";
import type { PositionKind } from "../api/types";
import {
  deskKindFromHit,
  LIBRARY_DRAG_MIME,
  LIBRARY_TABS,
  labelsFromHit,
  librarySearch,
  type LibraryHit,
  type LibraryTabId,
} from "../api/library";

function asKind(hit: LibraryHit): PositionKind {
  return deskKindFromHit(hit);
}

const DESK_TABS = LIBRARY_TABS.filter(
  (tab) => tab.id === "all" || tab.id === "musique" || tab.id === "jingle" || tab.id === "archives",
);

export function DeskLibrary({
  fireDisabled = false,
  onInsertNext,
  onFireNow,
}: {
  fireDisabled?: boolean;
  onInsertNext: (hit: LibraryHit) => void;
  onFireNow: (hit: LibraryHit) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<LibraryTabId>("all");
  const [hits, setHits] = useState<LibraryHit[]>([]);
  const [recents, setRecents] = useState<LibraryHit[]>(() => readDeskRecents());
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [active, setActive] = useState(0);
  const debounce = useRef<number | null>(null);

  const remember = useCallback((hit: LibraryHit) => {
    setRecents(pushDeskRecent(hit));
  }, []);

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
      onFireNow(hit);
    },
    [fireDisabled, onFireNow, remember],
  );

  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      void librarySearch({ q: query, tab, limit: 40 })
        .then((result) => {
          setHits(result.hits);
          setTotal(
            typeof result.estimatedTotalHits === "number" ? result.estimatedTotalHits : result.hits.length,
          );
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
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current);
    };
  }, [query, tab, attempt]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable;
      const inSearch = document.activeElement === inputRef.current;
      if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        return;
      }
      if (event.key === "Escape" && inSearch) {
        event.preventDefault();
        setQuery("");
        inputRef.current?.blur();
        return;
      }
      if (
        event.key === "Enter" &&
        (!typing || inSearch) &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !event.shiftKey
      ) {
        event.preventDefault();
        const hit = hits[active];
        if (hit) insert(hit);
        return;
      }
      if (!inSearch) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((value) => Math.min(hits.length - 1, value + 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((value) => Math.max(0, value - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, hits, insert]);

  const showRecents = !query.trim() && recents.length > 0 && !error;
  const showEmpty = ready && !error && hits.length === 0;
  const shown = hits.length;
  const countLabel = !ready
    ? "Recherche…"
    : total != null && total > shown
      ? `${shown} affichés sur ${total}`
      : `${shown} résultat${shown > 1 ? "s" : ""}`;

  return (
    <section className="panel" aria-labelledby="lib-title">
      <header className="panel-head">
        <h2 id="lib-title">Bibliothèque</h2>
      </header>
      <div className="lib-body">
        <div className="search">
          <p className="lib-help">
            Touche le titre pour le mettre à la suite. Lecture le passe tout de suite. Tu peux aussi le glisser sur la file.
          </p>
          <div className="search-field">
            <Search aria-hidden="true" />
            <input
              ref={inputRef}
              type="search"
              placeholder="Titre, artiste…"
              aria-label="Recherche bibliothèque"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {query ? (
              <button
                type="button"
                className="search-clear"
                aria-label="Effacer la recherche"
                onClick={() => {
                  setQuery("");
                  inputRef.current?.focus();
                }}
              >
                Effacer
              </button>
            ) : null}
          </div>
          <div className="tabs" role="tablist" aria-label="Filtres">
            {DESK_TABS.map((item) => (
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
            <div className="lib-chips" aria-label="Titres récents">
              {recents.map((hit) => {
                const labels = labelsFromHit(hit);
                return (
                  <button key={`r-${hit.path}`} type="button" onClick={() => insert(hit)}>
                    {labels.title || hit.path}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
        {error ? (
          <div className="lib-state lib-error">
            <strong>Le catalogue ne répond pas.</strong>
            {error} S’il reste muet, un admin regarde Réglages → Automate.
            <br />
            <button type="button" onClick={() => setAttempt((value) => value + 1)}>
              Réessayer
            </button>
          </div>
        ) : null}
        {showEmpty ? (
          <div className="lib-state">
            <strong>Aucun titre.</strong>
            Essaie un autre mot, ou change d’onglet.
          </div>
        ) : null}
        {!error && hits.length ? (
          <div className="lib-results">
            <ol className="hits">
              {hits.map((hit, index) => (
                <HitRow
                  key={hit.id || hit.path}
                  hit={hit}
                  active={index === active}
                  fireDisabled={fireDisabled}
                  onSelect={() => setActive(index)}
                  onInsert={insert}
                  onFire={fire}
                />
              ))}
            </ol>
          </div>
        ) : null}
      </div>
      <footer className="panel-foot">{error || !ready ? "" : countLabel}</footer>
    </section>
  );
}

function HitRow({
  hit,
  active = false,
  fireDisabled = false,
  onSelect,
  onInsert,
  onFire,
}: {
  hit: LibraryHit;
  active?: boolean;
  fireDisabled?: boolean;
  onSelect?: () => void;
  onInsert: (hit: LibraryHit) => void;
  onFire: (hit: LibraryHit) => void;
}) {
  const kind = asKind(hit);
  const labels = labelsFromHit(hit);
  const [fired, setFired] = useState(false);
  const rowRef = useRef<HTMLLIElement>(null);
  const title = labels.title || "ce titre";
  useEffect(() => {
    if (active) rowRef.current?.scrollIntoView({ block: "nearest" });
  }, [active]);
  return (
    <li ref={rowRef} className={active ? "is-active" : undefined}>
      <button
        type="button"
        className="hit"
        draggable
        aria-label={`Mettre ${title} à la suite`}
        onDragStart={(event) => {
          event.stopPropagation();
          event.dataTransfer.effectAllowed = "copy";
          event.dataTransfer.setData(LIBRARY_DRAG_MIME, JSON.stringify(hit));
          event.dataTransfer.setData("text/plain", hit.path);
        }}
        onClick={() => {
          onSelect?.();
          onInsert(hit);
        }}
      >
        <span className={`kind is-${kind}`} title={kindLabel(kind)} aria-hidden="true" />
        <span className="q-copy">
          <span className="t">{labels.title || "—"}</span>
          {labels.artist ? <span className="a">{labels.artist}</span> : null}
        </span>
        <span className="hit-dur">{formatMmSs(hit.duration || 0)}</span>
      </button>
      <button
        type="button"
        className={`play${fired ? " is-fired" : ""}`}
        disabled={fireDisabled}
        aria-label={`Lecture de ${title}`}
        title={fireDisabled ? "Direct à l’antenne" : "Lecture immédiate"}
        onClick={() => {
          setFired(true);
          window.setTimeout(() => setFired(false), 320);
          onFire(hit);
        }}
      >
        <Play aria-hidden="true" />
        <span>Lecture</span>
      </button>
    </li>
  );
}
