import {
  Badge,
  Button,
  Checkbox,
  DropdownMenu,
  IconButton,
  Spinner,
  Switch,
  TextField,
  Tooltip,
} from "@radix-ui/themes";
import {
  ChevronDown,
  FolderOpen,
  GripVertical,
  Link2,
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  Plus,
  RadioTower,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type MouseEvent, type RefObject } from "react";
import { audioFilesFromList, filesFromDataTransfer, isFileDrag } from "../../api/audioDrop";
import { lastPlayedLabel, splitSoundTitle } from "../../api/cartMeta";
import { deleteCartSounds, type CartImportProgress } from "../../api/cartSounds";
import { apiBlob, apiDeleteJson, apiPost, apiPut, ApiForbiddenError, ApiRequestError } from "../../api/client";
import { fuzzyTitleMatch } from "../../api/fuzzyTitle";
import { formatClock, percentOf } from "../../api/soundsView";
import type { Cart, Sound } from "../../api/types";
import type { ToastTone } from "../../ui/AppToast";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { BankAttachDialog } from "./BankAttachDialog";

export function SoundTable({
  cart,
  importProgress,
  onCart,
  notify,
  onImport,
  onAttachBank,
}: {
  cart: Cart;
  importProgress: CartImportProgress | null;
  onCart: (cart: Cart) => void;
  notify: (text: string, tone?: ToastTone) => void;
  onImport: (collect: () => Promise<File[]>) => Promise<void>;
  onAttachBank: (folders: string[]) => Promise<void>;
}) {
  const importing = importProgress?.cartId === cart.id;
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const dropDepth = useRef(0);
  const lastClicked = useRef<number | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
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
  const [attachOpen, setAttachOpen] = useState(false);

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
    if (caught instanceof ApiForbiddenError) notify("Il faut le rôle Programmateur pour modifier ce bac.", "error");
    else notify(caught instanceof ApiRequestError ? caught.message : fallback, "error");
  };

  const takeFiles = (list: FileList | File[] | null) => {
    const audio = list ? audioFilesFromList(list) : [];
    if (!audio.length) {
      notify("Aucun fichier audio dans ce choix.", "error");
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
  const filtering = Boolean(titleQuery.trim());
  const canDrag = cart.mode !== "random" && !filtering;

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
  const reading = importProgress?.phase === "reading" || !importProgress?.total;
  const importPercent = importProgress ? percentOf(importProgress.done, importProgress.total) : 0;

  return (
    <div
      className={`bacs-sounds${dropOver ? " is-drop" : ""}`}
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
      {selected.size > 0 ? (
        <div className="bacs-toolbar bacs-toolbar--selection" role="toolbar" aria-label="Sélection">
          <strong className="bacs-selection-count">
            {selected.size} son{selected.size === 1 ? "" : "s"} sélectionné{selected.size === 1 ? "" : "s"}
          </strong>
          <span className="bacs-muted bacs-hide-narrow">Maj + clic pour une plage</span>
          <span className="bacs-spacer" />
          <Button size="1" variant="ghost" color="gray" onClick={() => setSelected(new Set())}>
            <X className="ui-button-icon" />
            Désélectionner
          </Button>
          <ConfirmDialog
            trigger={
              <Button size="1" color="red" variant="soft" disabled={busyDelete}>
                <Trash2 className="ui-button-icon" />
                Retirer
              </Button>
            }
            title={`Retirer ${selected.size} son${selected.size === 1 ? "" : "s"} du bac ?`}
            description="Les sons quittent ce bac. Un fichier lié depuis un dossier de la banque y reste ; un fichier ajouté dans ce bac part dans la corbeille de la banque."
            confirmLabel={`Retirer ${selected.size} son${selected.size === 1 ? "" : "s"}`}
            busy={busyDelete}
            onConfirm={deleteSelected}
          />
        </div>
      ) : (
        <div className="bacs-toolbar" role="toolbar" aria-label="Sons du bac">
          {cart.sounds.length ? (
            <TextField.Root
              size="1"
              className="bacs-filter-field"
              placeholder="Filtrer les sons"
              value={titleQuery}
              aria-label="Filtrer les sons"
              onChange={(event) => setTitleQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setTitleQuery("");
              }}
            >
              <TextField.Slot>
                <Search size={14} aria-hidden="true" />
              </TextField.Slot>
            </TextField.Root>
          ) : (
            <span className="bacs-muted">Aucun son pour l'instant</span>
          )}
          {filtering ? (
            <span className="bacs-muted">
              {visibleSounds.length} sur {cart.sounds.length}
            </span>
          ) : null}
          <span className="bacs-spacer" />
          <DropdownMenu.Root>
            <DropdownMenu.Trigger disabled={importing}>
              <Button size="1" highContrast>
                <Plus className="ui-button-icon" />
                Ajouter
                <ChevronDown size={13} aria-hidden="true" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end" className="bacs-menu">
              <DropdownMenu.Item onSelect={() => inputRef.current?.click()}>
                <Upload size={15} aria-hidden="true" />
                <span className="bacs-menu-copy">
                  Fichiers de l'ordinateur
                  <small>Copiés dans le bac</small>
                </span>
              </DropdownMenu.Item>
              <DropdownMenu.Item onSelect={() => folderRef.current?.click()}>
                <FolderOpen size={15} aria-hidden="true" />
                <span className="bacs-menu-copy">
                  Dossier de l'ordinateur
                  <small>Tous ses fichiers audio, copiés</small>
                </span>
              </DropdownMenu.Item>
              <DropdownMenu.Separator />
              <DropdownMenu.Item onSelect={() => setAttachOpen(true)}>
                <Link2 size={15} aria-hidden="true" />
                <span className="bacs-menu-copy">
                  Dossier de la banque
                  <small>Lié, sans copie</small>
                </span>
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>
      )}

      {importing && importProgress ? (
        <div className="bacs-import" role="status" aria-live="polite">
          <Spinner size="1" />
          <span className="bacs-import-copy">
            <strong>
              {reading
                ? "Lecture des fichiers…"
                : `Ajout de ${importProgress.total} fichier${importProgress.total === 1 ? "" : "s"}`}
            </strong>
            {!reading ? (
              <span>
                {importProgress.done} / {importProgress.total}
                {importProgress.current ? ` · ${importProgress.current}` : ""}
              </span>
            ) : null}
          </span>
          <span className={`bacs-bar${reading ? " is-busy" : ""}`} aria-hidden="true">
            <i style={reading ? undefined : { width: `${importPercent}%` }} />
          </span>
        </div>
      ) : null}

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

      <div className="bacs-table-wrap">
        {cart.sounds.length === 0 ? (
          <div className="bacs-dropzone">
            <span className="bacs-dropzone-icon" aria-hidden="true">
              <Upload size={20} />
            </span>
            <strong>Ce bac est vide</strong>
            <p>Glisse des fichiers audio ou un dossier ici, ou choisis d'où viennent les sons.</p>
            <div className="bacs-dropzone-actions">
              <Button size="2" highContrast disabled={importing} onClick={() => inputRef.current?.click()}>
                <Upload className="ui-button-icon" />
                Ajouter des fichiers
              </Button>
              <Button size="2" variant="soft" color="gray" disabled={importing} onClick={() => setAttachOpen(true)}>
                <Link2 className="ui-button-icon" />
                Lier un dossier de la banque
              </Button>
            </div>
          </div>
        ) : (
          <table className="bacs-table">
            <thead>
              <tr>
                <th className="c-check">
                  <Checkbox
                    size="1"
                    checked={allSelected ? true : someSelected ? "indeterminate" : false}
                    disabled={!visibleSounds.length}
                    aria-label="Tout sélectionner"
                    onCheckedChange={(checked) => {
                      setSelected(checked === true ? new Set(visibleSounds.map((sound) => sound.id)) : new Set());
                    }}
                  />
                </th>
                {cart.mode !== "random" ? <th className="c-rank">#</th> : null}
                <th className="c-play">
                  <span className="ui-visually-hidden">Écouter</span>
                </th>
                <th className="c-title">Titre</th>
                <th className="c-last">Diffusé</th>
                <th className="c-len">Durée</th>
                <th className="c-on">Actif</th>
                <th className="c-more">
                  <span className="ui-visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleSounds.map((sound) => (
                <SoundRow
                  key={sound.id}
                  cart={cart}
                  sound={sound}
                  rank={cart.sounds.indexOf(sound) + 1}
                  showRank={cart.mode !== "random"}
                  canDrag={canDrag}
                  dragging={dragging}
                  dropTarget={dropTarget === sound.id}
                  playing={playingId === sound.id}
                  selected={selected.has(sound.id)}
                  onToggleSelect={toggleSelect}
                  onDragStart={setDragging}
                  onDragTarget={setDropTarget}
                  onDrop={reorder}
                  onPlay={() => void play(sound)}
                  onCart={onCart}
                  notify={notify}
                />
              ))}
            </tbody>
          </table>
        )}
        {cart.sounds.length > 0 && visibleSounds.length === 0 ? (
          <div className="bacs-table-empty">
            <p>Aucun son ne correspond à « {titleQuery.trim()} ».</p>
            <Button size="1" variant="soft" color="gray" onClick={() => setTitleQuery("")}>
              Effacer le filtre
            </Button>
          </div>
        ) : null}
      </div>

      {cart.sounds.length ? (
        <PreviewBar
          audioRef={audioRef}
          objectUrl={objectUrl}
          playing={playing}
          copy={playingCopy}
          hint={
            cart.mode === "random"
              ? "Double-clic sur un titre pour le renommer"
              : "Double-clic pour renommer, glisser le numéro pour classer"
          }
          onEnded={onPreviewEnded}
          onToggle={() => {
            if (playing) void play(playing);
            else if (visibleSounds[0]) void play(visibleSounds[0]);
          }}
        />
      ) : null}

      {dropOver ? (
        <div className="bacs-drop-overlay" aria-hidden="true">
          <span className="bacs-dropzone-icon">
            <Upload size={20} />
          </span>
          <strong>Déposer dans « {cart.title} »</strong>
          <span>Les fichiers audio sont copiés dans le bac.</span>
        </div>
      ) : null}

      <BankAttachDialog
        open={attachOpen}
        onOpenChange={setAttachOpen}
        busy={importing}
        cartTitle={cart.title}
        onAttach={onAttachBank}
      />
    </div>
  );
}

function PreviewBar({
  audioRef,
  objectUrl,
  playing,
  copy,
  hint,
  onEnded,
  onToggle,
}: {
  audioRef: RefObject<HTMLAudioElement | null>;
  objectUrl: string | null;
  playing: Sound | null;
  copy: { title: string; artist: string } | null;
  hint: string;
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
    <div className={`bacs-player${playing ? " is-playing" : ""}`}>
      <button
        type="button"
        className={`bacs-play bacs-play--lg${playing ? " is-on" : ""}`}
        onClick={onToggle}
        aria-label={playing ? "Arrêter la pré-écoute" : "Pré-écouter le bac"}
      >
        {playing ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <div className="bacs-player-copy">
        <strong>{copy?.title || "Pré-écoute"}</strong>
        <span>{copy ? copy.artist || "Lecture locale, hors antenne" : "Écoute ici, sans toucher à l'antenne"}</span>
      </div>
      {playing ? (
        <div className="bacs-player-track">
          <span className="bacs-time">{formatClock(elapsed)}</span>
          <button
            type="button"
            className="bacs-seek"
            disabled={total <= 0}
            aria-label="Position dans le titre"
            onClick={seek}
          >
            <i style={{ width: `${Math.round(ratio * 1000) / 10}%` }} />
          </button>
          <span className="bacs-time">{formatClock(total)}</span>
        </div>
      ) : (
        <span className="bacs-player-hint">{hint}</span>
      )}
      <audio ref={audioRef} className="bacs-audio" src={objectUrl ?? undefined} onEnded={onEnded} />
    </div>
  );
}

function SoundRow({
  cart,
  sound,
  rank,
  showRank,
  canDrag,
  dragging,
  dropTarget,
  playing,
  selected,
  onToggleSelect,
  onDragStart,
  onDragTarget,
  onDrop,
  onPlay,
  onCart,
  notify,
}: {
  cart: Cart;
  sound: Sound;
  rank: number;
  showRank: boolean;
  canDrag: boolean;
  dragging: number | null;
  dropTarget: boolean;
  playing: boolean;
  selected: boolean;
  onToggleSelect: (id: number, shift: boolean) => void;
  onDragStart: (id: number | null) => void;
  onDragTarget: (id: number | null) => void;
  onDrop: (fromId: number, toId: number) => Promise<void>;
  onPlay: () => void;
  onCart: (cart: Cart) => void;
  notify: (text: string, tone?: ToastTone) => void;
}) {
  const [title, setTitle] = useState(sound.title);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => setTitle(sound.title), [sound.title]);
  const isNext = cart.mode !== "random" && cart.next_sound_id === sound.id;
  const parsed = splitSoundTitle(sound.title);
  const analysing = sound.gain == null;
  const unavailable = !sound.available && !analysing;

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
      notify(caught instanceof ApiRequestError ? caught.message : "Renommage impossible.", "error");
      setTitle(sound.title);
    }
  };

  const deleteSound = async () => {
    try {
      const payload = await apiDeleteJson<{ cart: Cart }>(`/carts/${cart.id}/sounds/${sound.id}.json`);
      onCart(payload.cart);
    } catch (caught) {
      notify(caught instanceof ApiRequestError ? caught.message : "Retrait impossible.", "error");
    }
  };

  const fire = async () => {
    try {
      await apiPost(`/carts/${cart.id}/sounds/${sound.id}/now.json`);
      notify(`« ${parsed.title} » envoyé à l'antenne`, "success");
    } catch (caught) {
      if (caught instanceof ApiForbiddenError) notify("Il faut le droit Antenne pour diffuser.", "error");
      else notify(caught instanceof ApiRequestError ? caught.message : "Diffusion impossible.", "error");
    }
  };

  const setActive = async (active: boolean) => {
    try {
      const payload = await apiPut<{ cart: Cart }>(`/carts/${cart.id}/sounds/${sound.id}.json`, { active });
      onCart(payload.cart);
    } catch (caught) {
      notify(caught instanceof ApiRequestError ? caught.message : "Mise à jour impossible.", "error");
    }
  };

  const rowClass = [
    "bacs-track-row",
    isNext ? "is-next" : "",
    playing ? "is-playing" : "",
    dragging === sound.id ? "is-dragging" : "",
    dropTarget && dragging != null && dragging !== sound.id ? "is-drop-target" : "",
    selected ? "is-selected" : "",
    !sound.active || unavailable ? "is-off" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <tr
      className={rowClass}
      aria-selected={selected}
      onDragOver={(event) => {
        if (isFileDrag(event) || !canDrag || dragging == null) return;
        event.preventDefault();
        onDragTarget(sound.id);
      }}
      onDrop={(event) => {
        if (isFileDrag(event)) return;
        event.preventDefault();
        if (dragging != null) void onDrop(dragging, sound.id);
        onDragStart(null);
        onDragTarget(null);
      }}
    >
      <td className="c-check">
        <Checkbox
          size="1"
          checked={selected}
          aria-label={`Sélectionner ${parsed.title}`}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onToggleSelect(sound.id, event.shiftKey);
          }}
        />
      </td>
      {showRank ? (
        <td className="c-rank">
          {canDrag ? (
            <span
              className="bacs-grip"
              draggable
              title="Glisser pour réordonner"
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                onDragStart(sound.id);
              }}
              onDragEnd={() => {
                onDragStart(null);
                onDragTarget(null);
              }}
            >
              <span className="bacs-rank">{rank}</span>
              <GripVertical size={14} aria-hidden="true" />
            </span>
          ) : (
            <span className="bacs-rank">{rank}</span>
          )}
        </td>
      ) : null}
      <td className="c-play">
        <button
          type="button"
          className={`bacs-play${playing ? " is-on" : ""}`}
          onClick={onPlay}
          aria-label={playing ? "Arrêter la pré-écoute" : `Pré-écouter ${parsed.title}`}
        >
          {playing ? (
            <span className="bacs-eq" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
          ) : (
            <Play size={13} />
          )}
        </button>
      </td>
      <td className="c-title" onDoubleClick={() => setEditing(true)}>
        {editing ? (
          <TextField.Root
            size="1"
            autoFocus
            className="bacs-rename"
            value={title}
            aria-label="Nouveau titre"
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
          <div className="bacs-cell-title">
            <span className="bacs-track">{parsed.title}</span>
            <span className="bacs-artist">
              {parsed.artist ? <span>{parsed.artist}</span> : null}
              <span className="bacs-inline-len">{formatClock(sound.duration)}</span>
              {isNext ? (
                <Badge size="1" variant="outline" color="gray" className="bacs-badge">
                  Suivant
                </Badge>
              ) : null}
              {analysing ? (
                <Badge size="1" variant="soft" color="gray" className="bacs-badge">
                  Analyse…
                </Badge>
              ) : null}
              {unavailable ? (
                <Badge size="1" variant="soft" color="orange" className="bacs-badge">
                  Indisponible
                </Badge>
              ) : null}
            </span>
          </div>
        )}
      </td>
      <td className="c-last">{sound.last_played ? lastPlayedLabel(sound.last_played) : "Jamais"}</td>
      <td className="c-len">{formatClock(sound.duration)}</td>
      <td className="c-on">
        <Tooltip content={sound.active ? "Actif : peut passer à l'antenne" : "Inactif : le bac le saute"}>
          <Switch
            size="1"
            checked={sound.active}
            aria-label={`${sound.active ? "Désactiver" : "Activer"} ${parsed.title}`}
            onCheckedChange={(checked) => void setActive(checked)}
          />
        </Tooltip>
      </td>
      <td className="c-more">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            <IconButton size="1" variant="ghost" color="gray" aria-label={`Actions pour ${parsed.title}`}>
              <MoreHorizontal size={15} />
            </IconButton>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end" className="bacs-menu">
            <DropdownMenu.Item onSelect={onPlay}>
              {playing ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
              {playing ? "Arrêter la pré-écoute" : "Pré-écouter"}
            </DropdownMenu.Item>
            <DropdownMenu.Item onSelect={() => void fire()}>
              <RadioTower size={15} aria-hidden="true" />
              Diffuser maintenant
            </DropdownMenu.Item>
            <DropdownMenu.Item onSelect={() => setEditing(true)}>
              <Pencil size={15} aria-hidden="true" />
              Renommer
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item color="red" onSelect={() => setConfirmDelete(true)}>
              <Trash2 size={15} aria-hidden="true" />
              Retirer du bac…
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title={`Retirer « ${parsed.title} » ?`}
          description="Le son quitte ce bac. Un fichier lié depuis un dossier de la banque y reste ; un fichier ajouté dans ce bac part dans la corbeille de la banque."
          confirmLabel="Retirer le son"
          onConfirm={async () => {
            await deleteSound();
            setConfirmDelete(false);
          }}
        />
      </td>
    </tr>
  );
}
