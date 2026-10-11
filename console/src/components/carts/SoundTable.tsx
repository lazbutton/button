import { Badge, Button, Checkbox, Flex, Text, TextField, Tooltip } from "@radix-ui/themes";
import {
  FolderOpen,
  GripVertical,
  ListChecks,
  Music2,
  Play,
  RadioTower,
  Search,
  Square,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type MouseEvent, type RefObject } from "react";
import { formatHhMmSs, formatMmSs } from "../../lib/parisClock";
import { audioFilesFromList, filesFromDataTransfer, isFileDrag } from "../../api/audioDrop";
import { lastPlayedLabel, MODE_LABELS, splitSoundTitle } from "../../api/cartMeta";
import { deleteCartSounds, type CartImportProgress } from "../../api/cartSounds";
import { BankAttachDialog } from "./BankAttachDialog";
import { fuzzyTitleMatch } from "../../api/fuzzyTitle";
import {
  apiBlob,
  apiDeleteJson,
  apiPost,
  apiPut,
  ApiForbiddenError,
  ApiRequestError,
} from "../../api/client";
import type { Cart, Sound } from "../../api/types";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { EmptyState } from "../../ui/EmptyState";
import { Panel, SectionHeader } from "../../ui/Panel";

export function SoundTable({
  cart,
  importProgress,
  onCart,
  onError,
  onImport,
  onAttachBank,
}: {
  cart: Cart;
  importProgress: CartImportProgress | null;
  onCart: (cart: Cart) => void;
  onError: (text: string) => void;
  onImport: (collect: () => Promise<File[]>) => Promise<void>;
  onAttachBank: (folders: string[]) => Promise<void>;
}) {
  const importing = importProgress?.cartId === cart.id;
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const dropDepth = useRef(0);
  const lastClicked = useRef<number | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [playingId, setPlayingId] = useState<number | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const objectUrlRef = useRef<string | null>(null);
  const prefetchRef = useRef<{ id: number; url: string } | null>(null);
  const playingIdRef = useRef<number | null>(null);
  const queueRef = useRef<Sound[]>([]);
  const cartIdRef = useRef(cart.id);
  const playRef = useRef<(sound: Sound) => Promise<void>>(async () => undefined);
  const [dropOver, setDropOver] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [busyDelete, setBusyDelete] = useState(false);
  const [titleQuery, setTitleQuery] = useState("");

  cartIdRef.current = cart.id;
  playingIdRef.current = playingId;

  const revokeUrl = (url: string | null) => {
    if (url) URL.revokeObjectURL(url);
  };

  useEffect(() => {
    return () => {
      revokeUrl(objectUrlRef.current);
      revokeUrl(prefetchRef.current?.url ?? null);
    };
  }, []);

  useEffect(() => {
    audioRef.current?.pause();
    setPlayingId(null);
    playingIdRef.current = null;
    setSelected(new Set());
    lastClicked.current = null;
    setTitleQuery("");
    revokeUrl(prefetchRef.current?.url ?? null);
    prefetchRef.current = null;
    revokeUrl(objectUrlRef.current);
    objectUrlRef.current = null;
    setObjectUrl(null);
  }, [cart.id]);

  useEffect(() => {
    const ids = new Set(cart.sounds.map((sound) => sound.id));
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => ids.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [cart.sounds]);

  const fail = (caught: unknown, fallback: string) => {
    if (caught instanceof ApiForbiddenError) onError("Droit insuffisant.");
    else onError(caught instanceof ApiRequestError ? caught.message : fallback);
  };

  const takeFiles = (list: FileList | File[] | null) => {
    const audio = list ? audioFilesFromList(list) : [];
    if (!audio.length) {
      onError("Aucun fichier audio.");
      return;
    }
    void onImport(() => Promise.resolve(audio));
  };

  const play = async (sound: Sound) => {
    if (playingIdRef.current === sound.id) {
      audioRef.current?.pause();
      playingIdRef.current = null;
      setPlayingId(null);
      return;
    }
    try {
      let url = prefetchRef.current?.id === sound.id ? prefetchRef.current.url : null;
      if (prefetchRef.current?.id === sound.id) prefetchRef.current = null;
      if (!url) url = await apiBlob(`/carts/${cartIdRef.current}/sounds/${sound.id}`);
      revokeUrl(objectUrlRef.current);
      objectUrlRef.current = url;
      setObjectUrl(url);
      playingIdRef.current = sound.id;
      setPlayingId(sound.id);
      requestAnimationFrame(() => {
        void audioRef.current?.play();
      });
      const list = queueRef.current;
      const index = list.findIndex((item) => item.id === sound.id);
      const upcoming = index >= 0 ? list[index + 1] : undefined;
      if (!upcoming) return;
      if (prefetchRef.current?.id === upcoming.id) return;
      void apiBlob(`/carts/${cartIdRef.current}/sounds/${upcoming.id}`)
        .then((nextUrl) => {
          if (playingIdRef.current !== sound.id) {
            revokeUrl(nextUrl);
            return;
          }
          revokeUrl(prefetchRef.current?.url ?? null);
          prefetchRef.current = { id: upcoming.id, url: nextUrl };
        })
        .catch(() => undefined);
    } catch (caught) {
      fail(caught, "Lecture impossible.");
      playingIdRef.current = null;
      setPlayingId(null);
    }
  };
  playRef.current = play;

  const onPreviewEnded = () => {
    const list = queueRef.current;
    const index = list.findIndex((item) => item.id === playingIdRef.current);
    const upcoming = index >= 0 ? list[index + 1] : undefined;
    if (upcoming) {
      void playRef.current(upcoming);
      return;
    }
    playingIdRef.current = null;
    setPlayingId(null);
  };

  const reorder = async (fromId: number, toId: number) => {
    if (fromId === toId) return;
    const ids = cart.sounds.map((s) => s.id);
    const from = ids.indexOf(fromId);
    const to = ids.indexOf(toId);
    if (from < 0 || to < 0) return;
    ids.splice(from, 1);
    ids.splice(to, 0, fromId);
    try {
      const payload = await apiPut<{ cart: Cart }>(`/carts/${cart.id}/sounds/ranks.json`, {
        ranks: ids,
      });
      onCart(payload.cart);
    } catch (caught) {
      fail(caught, "Rang impossible.");
    }
  };

  const visibleSounds = useMemo(
    () => cart.sounds.filter((sound) => fuzzyTitleMatch(sound.title, titleQuery)),
    [cart.sounds, titleQuery],
  );
  queueRef.current = visibleSounds.length ? visibleSounds : cart.sounds;

  const totalDuration = useMemo(
    () => cart.sounds.reduce((sum, sound) => sum + (sound.duration || 0), 0),
    [cart.sounds],
  );

  const nextSound = cart.sounds.find((sound) => sound.id === cart.next_sound_id) ?? null;
  const nextCopy = nextSound ? splitSoundTitle(nextSound.title) : null;

  const toggleSelect = (id: number, shift: boolean) => {
    const ids = visibleSounds.map((sound) => sound.id);
    setSelected((prev) => {
      const next = new Set(prev);
      if (shift && lastClicked.current != null) {
        const a = ids.indexOf(lastClicked.current);
        const b = ids.indexOf(id);
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a];
          for (let i = lo; i <= hi; i++) next.add(ids[i]);
          return next;
        }
      }
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    lastClicked.current = id;
  };

  const allSelected = visibleSounds.length > 0 && visibleSounds.every((sound) => selected.has(sound.id));
  const someSelected = visibleSounds.some((sound) => selected.has(sound.id)) && !allSelected;

  const deleteSelected = async () => {
    const ids = [...selected];
    if (!ids.length) return;
    setBusyDelete(true);
    try {
      if (playingId != null && ids.includes(playingId)) {
        audioRef.current?.pause();
        setPlayingId(null);
      }
      const payload = await deleteCartSounds(cart.id, ids);
      setSelected(new Set());
      onCart(payload.cart);
    } catch (caught) {
      fail(caught, "Suppression impossible.");
    } finally {
      setBusyDelete(false);
    }
  };

  const playing = cart.sounds.find((s) => s.id === playingId) ?? null;
  const playingCopy = playing ? splitSoundTitle(playing.title) : null;
  const dropClass = dropOver ? " is-drop-target" : "";

  return (
    <Panel padded={false} className={`app-carts-col app-carts-sounds${dropClass}${importing ? " is-importing" : ""}`}>
      <div
        className="app-carts-drop-surface"
        aria-busy={importing}
        onDragEnter={(event) => {
          if (!isFileDrag(event) || importing) return;
          dropDepth.current += 1;
          setDropOver(true);
        }}
        onDragOver={(event) => {
          if (!isFileDrag(event) || importing) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          setDropOver(true);
        }}
        onDragLeave={(event) => {
          if (!isFileDrag(event)) return;
          dropDepth.current -= 1;
          if (dropDepth.current <= 0) {
            dropDepth.current = 0;
            setDropOver(false);
          }
        }}
        onDrop={(event) => {
          if (!isFileDrag(event) || importing) return;
          event.preventDefault();
          event.stopPropagation();
          dropDepth.current = 0;
          setDropOver(false);
          const data = event.dataTransfer;
          void onImport(() => filesFromDataTransfer(data));
        }}
      >
        {dropOver || importing ? (
          <div className="app-carts-drop-overlay" role="status" aria-live="polite">
            <span className="app-carts-drop-icon">
              <Upload />
            </span>
            {importing && importProgress ? (
              <ImportStatus progress={importProgress} cartTitle={cart.title} />
            ) : (
              <>
                <strong>Ajouter dans « {cart.title} »</strong>
                <span>Relâchez les fichiers ou le dossier audio</span>
              </>
            )}
          </div>
        ) : null}
        <div className="app-carts-sounds-toolbar">
          <SectionHeader
            title={cart.title}
            count={cart.sounds.length}
            actions={
              <Flex gap="1" wrap="wrap" align="center">
                <Button size="1" variant="soft" disabled={importing} onClick={() => inputRef.current?.click()}>
                  <Upload className="ui-button-icon" />
                  Ajouter des fichiers
                </Button>
                <Tooltip content="Copie les fichiers d’un dossier de l’ordinateur dans le bac.">
                  <Button
                    size="1"
                    variant="ghost"
                    color="gray"
                    disabled={importing}
                    aria-label="Ajouter un dossier de l’ordinateur"
                    onClick={() => folderRef.current?.click()}
                  >
                    <FolderOpen className="ui-button-icon" />
                    Dossier
                  </Button>
                </Tooltip>
                <BankAttachDialog disabled={importing} busy={importing} onAttach={onAttachBank} />
              </Flex>
            }
          />
          <div className="app-carts-sound-stats">
            <span className="app-carts-mode">{MODE_LABELS[cart.mode]}</span>
            {titleQuery.trim() ? (
              <span>
                {visibleSounds.length} résultat{visibleSounds.length === 1 ? "" : "s"}
              </span>
            ) : (
              <>
                {totalDuration > 0 ? <span>{formatHhMmSs(totalDuration)}</span> : null}
                {cart.average_duration ? <span>moy. {formatMmSs(cart.average_duration)}</span> : null}
                {cart.schedule_summary ? <span>{cart.schedule_summary}</span> : null}
              </>
            )}
          </div>
          {nextCopy ? (
            <p className="app-carts-next-line">
              <span>Suivant</span>
              <strong>{nextCopy.title}</strong>
              {nextCopy.artist ? <em>{nextCopy.artist}</em> : null}
            </p>
          ) : null}
          <div className="app-carts-tools-row">
            <TextField.Root
              size="1"
              className="app-sound-search"
              placeholder="Filtrer les titres…"
              value={titleQuery}
              onChange={(event) => setTitleQuery(event.target.value)}
              aria-label="Filtrer les titres"
            >
              <TextField.Slot>
                <Search size={14} aria-hidden="true" />
              </TextField.Slot>
            </TextField.Root>
            <span className={`app-carts-import-state${importing ? " is-active" : ""}`} aria-live="polite">
              <span aria-hidden="true" />
              {importing && importProgress
                ? importProgress.phase === "reading"
                  ? "Lecture des fichiers…"
                  : `Ajout ${importProgress.done} / ${importProgress.total}`
                : "Déposez les fichiers ici"}
            </span>
          </div>
          {selected.size > 0 ? (
            <div className="app-carts-selection-bar" role="status">
              <div>
                <ListChecks size={16} aria-hidden="true" />
                <strong>
                  {selected.size} piste{selected.size === 1 ? "" : "s"} sélectionnée
                  {selected.size === 1 ? "" : "s"}
                </strong>
                <span>Maj+clic pour sélectionner une plage</span>
              </div>
              <Flex gap="1" align="center">
                <Button size="1" variant="ghost" color="gray" onClick={() => setSelected(new Set())}>
                  <X className="ui-button-icon" />
                  Effacer
                </Button>
                <ConfirmDialog
                  trigger={
                    <Button size="1" color="red" variant="soft" disabled={busyDelete}>
                      <Trash2 className="ui-button-icon" />
                      Supprimer
                    </Button>
                  }
                  title={`Supprimer ${selected.size} son${selected.size === 1 ? "" : "s"} ?`}
                  description="Les fichiers quitteront ce bac définitivement. Cette action ne peut pas être annulée."
                  confirmLabel={`Supprimer ${selected.size} son${selected.size === 1 ? "" : "s"}`}
                  busy={busyDelete}
                  onConfirm={deleteSelected}
                />
              </Flex>
            </div>
          ) : null}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="audio/*,.mp3,.wav,.flac,.ogg,.opus,.m4a,.aac,.aiff"
          multiple
          hidden
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            takeFiles(files);
          }}
        />
        <input
          ref={folderRef}
          type="file"
          multiple
          hidden
          // @ts-expect-error vendor directory picker
          webkitdirectory=""
          directory=""
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            takeFiles(files);
          }}
        />
        <div className="app-sound-table-wrap ui-table-shell">
          {cart.sounds.length === 0 ? (
            <EmptyState
              icon={Music2}
              title="Ce bac est vide"
              description="Déposez ici des fichiers ou un dossier audio, ou ouvrez le sélecteur de fichiers."
              actionLabel="Ajouter des fichiers"
              onAction={() => inputRef.current?.click()}
            />
          ) : (
            <>
              <table className="app-sound-table">
                <thead>
                  <tr>
                    <th className="app-sound-check">
                      <Checkbox
                        checked={allSelected ? true : someSelected ? "indeterminate" : false}
                        disabled={!visibleSounds.length}
                        aria-label="Tout sélectionner"
                        onCheckedChange={(checked) => {
                          if (checked === true) {
                            setSelected(new Set(visibleSounds.map((sound) => sound.id)));
                          } else {
                            setSelected(new Set());
                          }
                        }}
                      />
                    </th>
                    {cart.mode !== "random" ? <th className="app-sound-handle">#</th> : null}
                    <th className="app-sound-preview">
                      <span className="ui-visually-hidden">Aperçu</span>
                    </th>
                    <th className="app-sound-title">Titre</th>
                    <th className="app-sound-duration">Durée</th>
                    <th className="app-sound-active">On</th>
                    <th className="app-sound-actions">
                      <span className="ui-visually-hidden">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visibleSounds.map((sound, index) => (
                    <SoundRow
                      key={sound.id}
                      cart={cart}
                      sound={sound}
                      index={index}
                      canDrag={cart.mode !== "random"}
                      dragging={dragging}
                      playing={playingId === sound.id}
                      selected={selected.has(sound.id)}
                      onToggleSelect={toggleSelect}
                      onDragStart={setDragging}
                      onDrop={reorder}
                      onPlay={() => void play(sound)}
                      onCart={onCart}
                      onError={onError}
                    />
                  ))}
                </tbody>
              </table>
              {visibleSounds.length === 0 ? (
                <EmptyState
                  icon={Search}
                  title="Aucun titre trouvé"
                  description="Modifiez le filtre pour afficher les autres sons du bac."
                  actionLabel="Effacer le filtre"
                  onAction={() => setTitleQuery("")}
                />
              ) : (
                <Text size="1" color="gray" className="app-sound-hint">
                  Cliquez un titre pour le renommer
                  {cart.mode !== "random" ? " · glissez le numéro pour réordonner" : ""}
                  {" · la préécoute enchaîne les pistes"}.
                </Text>
              )}
            </>
          )}
        </div>
        <PreviewBar
          audioRef={audioRef}
          objectUrl={objectUrl}
          playing={playing}
          copy={playingCopy}
          onEnded={onPreviewEnded}
          onToggle={() => {
            if (playing) void play(playing);
            else if (visibleSounds[0]) void play(visibleSounds[0]);
          }}
        />
      </div>
    </Panel>
  );
}

function PreviewBar({
  audioRef,
  objectUrl,
  playing,
  copy,
  onEnded,
  onToggle,
}: {
  audioRef: RefObject<HTMLAudioElement | null>;
  objectUrl: string | null;
  playing: Sound | null;
  copy: { title: string; artist: string } | null;
  onEnded: () => void;
  onToggle: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const sync = () => {
      setElapsed(el.currentTime || 0);
      const next = el.duration;
      setDuration(Number.isFinite(next) && next > 0 ? next : playing?.duration || 0);
    };
    sync();
    el.addEventListener("timeupdate", sync);
    el.addEventListener("durationchange", sync);
    el.addEventListener("loadedmetadata", sync);
    el.addEventListener("seeked", sync);
    return () => {
      el.removeEventListener("timeupdate", sync);
      el.removeEventListener("durationchange", sync);
      el.removeEventListener("loadedmetadata", sync);
      el.removeEventListener("seeked", sync);
    };
  }, [audioRef, objectUrl, playing?.id, playing?.duration]);

  const total = duration > 0 ? duration : playing?.duration || 0;
  const ratio = total > 0 ? Math.min(1, elapsed / total) : 0;

  const seek = (event: MouseEvent<HTMLButtonElement>) => {
    const el = audioRef.current;
    if (!el || total <= 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    el.currentTime = x * total;
    setElapsed(el.currentTime);
  };

  return (
    <div className={`app-carts-player${playing ? " is-playing" : ""}`}>
      <button
        type="button"
        className={`app-sound-play${playing ? " is-on" : ""}`}
        onClick={onToggle}
        aria-label={playing ? "Arrêter l’aperçu" : "Écouter"}
      >
        {playing ? <Square /> : <Play />}
      </button>
      <div className="app-carts-player-copy">
        <strong>{copy?.title || "Aucune piste"}</strong>
        {copy?.artist ? <em>{copy.artist}</em> : <em>{playing ? "Aperçu" : "Prêt"}</em>}
      </div>
      <div className="app-carts-player-clock">
        <span>
          {playing ? `${formatMmSs(elapsed)} / ${formatMmSs(total)}` : "—"}
        </span>
        <button
          type="button"
          className="app-carts-seek"
          disabled={!playing || total <= 0}
          aria-label="Position dans le titre"
          onClick={seek}
        >
          <i style={{ width: `${Math.round(ratio * 1000) / 10}%` }} />
        </button>
      </div>
      <audio
        ref={audioRef}
        className="app-carts-player-audio"
        src={objectUrl ?? undefined}
        onEnded={onEnded}
      />
    </div>
  );
}

function ImportStatus({
  progress,
  cartTitle,
}: {
  progress: CartImportProgress;
  cartTitle: string;
}) {
  const reading = progress.phase === "reading" || progress.total === 0;
  const ratio = reading ? 0 : Math.min(1, progress.done / Math.max(1, progress.total));
  const percent = Math.round(ratio * 100);
  return (
    <>
      <strong>{reading ? "Lecture des fichiers…" : `Ajout dans « ${cartTitle} »`}</strong>
      {reading ? (
        <span>Préparation du dossier, un instant</span>
      ) : (
        <>
          <span className="app-carts-import-count">
            {progress.done} / {progress.total}
            <em> · {percent} %</em>
          </span>
          {progress.current ? <span className="app-carts-import-file">{progress.current}</span> : null}
        </>
      )}
      <span className={`app-carts-import-bar${reading ? " is-busy" : ""}`} aria-hidden="true">
        <span style={reading ? undefined : { width: `${percent}%` }} />
      </span>
    </>
  );
}

function SoundRow({
  cart,
  sound,
  index,
  canDrag,
  dragging,
  playing,
  selected,
  onToggleSelect,
  onDragStart,
  onDrop,
  onPlay,
  onCart,
  onError,
}: {
  cart: Cart;
  sound: Sound;
  index: number;
  canDrag: boolean;
  dragging: number | null;
  playing: boolean;
  selected: boolean;
  onToggleSelect: (id: number, shift: boolean) => void;
  onDragStart: (id: number | null) => void;
  onDrop: (fromId: number, toId: number) => Promise<void>;
  onPlay: () => void;
  onCart: (cart: Cart) => void;
  onError: (text: string) => void;
}) {
  const [title, setTitle] = useState(sound.title);
  const [editing, setEditing] = useState(false);
  useEffect(() => setTitle(sound.title), [sound.title]);
  const isNext = cart.next_sound_id === sound.id;
  const parsed = splitSoundTitle(sound.title);
  const analysing = sound.gain == null;
  const inactive = !sound.active || !sound.available;

  const saveTitle = async () => {
    const next = title.trim();
    setEditing(false);
    if (!next || next === sound.title) {
      setTitle(sound.title);
      return;
    }
    try {
      const payload = await apiPut<{ cart: Cart }>(`/carts/${cart.id}/sounds/${sound.id}.json`, {
        title: next,
      });
      onCart(payload.cart);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Titre impossible.");
      setTitle(sound.title);
    }
  };

  const deleteSound = async () => {
    try {
      const payload = await apiDeleteJson<{ cart: Cart }>(
        `/carts/${cart.id}/sounds/${sound.id}.json`,
      );
      onCart(payload.cart);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Suppression impossible.");
    }
  };

  const rowClass = [
    "app-sound-row",
    isNext ? "is-next" : "",
    playing ? "is-playing" : "",
    dragging === sound.id ? "is-dragging" : "",
    selected ? "is-selected" : "",
    inactive && !analysing ? "is-inactive" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <tr
      className={rowClass}
      aria-selected={selected}
      onDragOver={(e) => {
        if (isFileDrag(e) || !canDrag) return;
        e.preventDefault();
      }}
      onDrop={(e) => {
        if (isFileDrag(e)) return;
        e.preventDefault();
        if (dragging != null) void onDrop(dragging, sound.id);
        onDragStart(null);
      }}
    >
      <td className="app-sound-check">
        <Checkbox
          checked={selected}
          aria-label={`Sélectionner ${sound.title}`}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onToggleSelect(sound.id, event.shiftKey);
          }}
        />
      </td>
      {canDrag ? (
        <td className="app-sound-handle">
          <button
            type="button"
            className="app-drag"
            draggable
            aria-label={`Réordonner, rang ${index + 1}`}
            onDragStart={() => onDragStart(sound.id)}
            onDragEnd={() => onDragStart(null)}
          >
            <GripVertical className="ui-button-icon" />
            <span className="app-sound-rank">{String(index + 1).padStart(2, "0")}</span>
          </button>
        </td>
      ) : null}
      <td className="app-sound-preview">
        <Tooltip content={playing ? "Arrêter l’aperçu" : "Écouter"}>
          <button
            type="button"
            className={`app-sound-play${playing ? " is-on" : ""}`}
            onClick={onPlay}
            aria-label={playing ? "Arrêter l’aperçu" : `Écouter ${parsed.title}`}
          >
            {playing ? <Square /> : <Play />}
          </button>
        </Tooltip>
      </td>
      <td className="app-sound-title">
        {editing ? (
          <TextField.Root
            size="1"
            autoFocus
            className="app-sound-title-field"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onBlur={() => void saveTitle()}
            onKeyDown={(event) => {
              if (event.key === "Enter") (event.target as HTMLInputElement).blur();
              if (event.key === "Escape") {
                setTitle(sound.title);
                setEditing(false);
              }
            }}
          />
        ) : (
          <button
            type="button"
            className="app-sound-name"
            title="Cliquer pour renommer"
            onClick={() => setEditing(true)}
          >
            <span className="app-sound-name-title">{parsed.title}</span>
            <span className="app-sound-name-meta">
              {playing ? <em>Aperçu</em> : isNext ? <em>Suivant</em> : null}
              {parsed.artist ? <span>{parsed.artist}</span> : null}
              {sound.last_played ? (
                <span className="app-sound-played">{lastPlayedLabel(sound.last_played)}</span>
              ) : null}
              {analysing ? (
                <Badge size="1" color="gray">
                  Analyse
                </Badge>
              ) : null}
              {!sound.available && !analysing ? (
                <Badge size="1" color="gray">
                  Inactif
                </Badge>
              ) : null}
            </span>
          </button>
        )}
      </td>
      <td className="app-num app-sound-duration">{formatMmSs(sound.duration)}</td>
      <td className="app-sound-active">
        <Checkbox
          checked={sound.active}
          aria-label={`${sound.active ? "Désactiver" : "Activer"} ${sound.title}`}
          onCheckedChange={(checked) => {
            void (async () => {
              try {
                const payload = await apiPut<{ cart: Cart }>(
                  `/carts/${cart.id}/sounds/${sound.id}.json`,
                  { active: checked === true },
                );
                onCart(payload.cart);
              } catch (caught) {
                onError(caught instanceof ApiRequestError ? caught.message : "MAJ impossible.");
              }
            })();
          }}
        />
      </td>
      <td className="app-sound-actions">
        <Flex gap="1" justify="end">
          <Tooltip content="Diffuser maintenant">
            <Button
              size="1"
              variant="ghost"
              aria-label={`Diffuser ${sound.title}`}
              onClick={() => {
                void (async () => {
                  try {
                    await apiPost(`/carts/${cart.id}/sounds/${sound.id}/now.json`);
                  } catch (caught) {
                    if (caught instanceof ApiForbiddenError) onError("Droit Antenne requis.");
                    else onError(caught instanceof ApiRequestError ? caught.message : "Diffusion impossible.");
                  }
                })();
              }}
            >
              <RadioTower className="ui-button-icon" />
            </Button>
          </Tooltip>
          <ConfirmDialog
            trigger={
              <Button size="1" variant="ghost" color="red" aria-label={`Supprimer ${sound.title}`}>
                <Trash2 className="ui-button-icon" />
              </Button>
            }
            title={`Supprimer « ${sound.title} » ?`}
            description="Ce son sera retiré définitivement du bac. Cette action ne peut pas être annulée."
            confirmLabel="Supprimer le son"
            onConfirm={deleteSound}
          />
        </Flex>
      </td>
    </tr>
  );
}
