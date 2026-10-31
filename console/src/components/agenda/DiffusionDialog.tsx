import { Button, Dialog, SegmentedControl, Select, TextArea, TextField } from "@radix-ui/themes";
import { CopyPlus, Disc3, Mic, Square, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  attachBankFile,
  createDiffusions,
  deleteDiffusion,
  detachFile,
  getDiffusion,
  previewDiffusions,
  renewGuestLink,
  stopDiffusion,
  updateDiffusion,
  type AgendaGuest,
  type AgendaKind,
  type Diffusion,
  type DiffusionFields,
  type PreviewOccurrence,
  type RepeatRule,
  type WeeklyOccurrence,
} from "../../api/agenda";
import {
  dayLongLabel,
  durationLabel,
  hhmm,
  nthOfMonth,
  parisWall,
  rangeLabel,
  repeatLabel,
  statusOf,
  timeLabel,
  wallString,
  weekdayOf,
} from "../../api/agendaView";
import { errorText } from "../../api/programmationErrors";
import { parseHhmm } from "../../api/programmationView";
import { FormField } from "../../ui/FormField";
import { BankPicker } from "./BankPicker";
import { FileSection, InviteBox } from "./DiffusionParts";

export type DiffusionTarget =
  | {
      mode: "create";
      day: string;
      start: number;
      end: number;
      title?: string;
      kind?: AgendaKind;
      guestName?: string;
      host?: string;
      copyFrom?: Diffusion;
      replacing?: WeeklyOccurrence;
    }
  | { mode: "edit"; row: Diffusion };

const NOBODY = "__nobody__";
const NO_REPEAT = "none";

type Busy = null | "save" | "delete" | "stop" | "file";

/** One dated broadcast: when, what, who; then its file and its guest's link. */
export function DiffusionDialog({
  target,
  guests,
  hosts,
  hostsNote,
  titles,
  station,
  editable,
  canStop,
  onClose,
  onChanged,
  onDuplicate,
  onEdit,
}: {
  target: DiffusionTarget | null;
  guests: AgendaGuest[];
  hosts: string[];
  /** Why the host list is missing, when it is. */
  hostsNote: string;
  titles: string[];
  station: string;
  editable: boolean;
  canStop: boolean;
  onClose: () => void;
  onChanged: (message: string | null) => Promise<void>;
  onDuplicate: (row: Diffusion) => void;
  /** After a single date is created, the dialog goes on with it: its link is next. */
  onEdit: (row: Diffusion) => void;
}) {
  const [row, setRow] = useState<Diffusion | null>(null);
  const [kind, setKind] = useState<AgendaKind>("set");
  const [title, setTitle] = useState("");
  const [day, setDay] = useState("");
  const [start, setStart] = useState("22:00");
  const [end, setEnd] = useState("00:00");
  const [guestName, setGuestName] = useState("");
  const [host, setHost] = useState(NOBODY);
  const [setTitleText, setSetTitleText] = useState("");
  const [tracklist, setTracklist] = useState("");
  const [rule, setRule] = useState<string>(NO_REPEAT);
  const [count, setCount] = useState("4");
  const [preview, setPreview] = useState<PreviewOccurrence[] | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [previewNth, setPreviewNth] = useState(1);
  const [busy, setBusy] = useState<Busy>(null);
  const [failure, setFailure] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<"" | "one" | "following">("");
  const [confirmStop, setConfirmStop] = useState(false);
  const [bankOpen, setBankOpen] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!target) return;
    setFailure("");
    setBusy(null);
    setConfirmDelete("");
    setConfirmStop(false);
    setPreview(null);
    setRule(NO_REPEAT);
    setCount("4");
    if (target.mode === "edit") {
      const current = target.row;
      const from = parisWall(current.starts_at);
      setRow(current);
      setKind(current.kind);
      setTitle(current.title);
      setDay(from.day);
      setStart(hhmm(from.minute));
      setEnd(timeLabel(current.ends_at));
      setGuestName(current.guest?.name ?? "");
      setHost(current.host_username || NOBODY);
      setSetTitleText(current.set_title);
      setTracklist(current.tracklist);
      return;
    }
    setRow(null);
    setKind(target.kind ?? target.copyFrom?.kind ?? "set");
    setTitle(target.title ?? target.copyFrom?.title ?? "");
    setDay(target.day);
    setStart(hhmm(target.start));
    setEnd(hhmm(target.end % 1440));
    setGuestName(target.guestName ?? target.copyFrom?.guest?.name ?? "");
    setHost(target.host ?? (target.copyFrom?.host_username || NOBODY));
    setSetTitleText("");
    setTracklist("");
  }, [target]);

  const startMinute = parseHhmm(start);
  const endRaw = parseHhmm(end);
  const endMinute =
    startMinute != null && endRaw != null ? (endRaw <= startMinute ? endRaw + 1440 : endRaw) : null;
  const lasting = startMinute != null && endMinute != null ? endMinute - startMinute : 0;
  const creating = target?.mode === "create";
  const upcoming = !row || row.air_status === "upcoming";
  const canEditWhen = editable && upcoming;
  const ready = Boolean(title.trim()) && startMinute != null && endMinute != null && Boolean(day);

  const matchedGuest = useMemo(() => {
    const name = guestName.trim().toLowerCase();
    if (!name) return null;
    return guests.find((guest) => guest.name.trim().toLowerCase() === name) ?? null;
  }, [guestName, guests]);

  const baseFields = (): DiffusionFields | null => {
    if (startMinute == null || endMinute == null) return null;
    const fields: DiffusionFields = {
      kind,
      title: title.trim(),
      start: wallString(day, startMinute),
      end: wallString(day, endMinute),
    };
    if (kind === "set") {
      if (matchedGuest) fields.guest_id = matchedGuest.id;
      else if (guestName.trim()) fields.guest_name = guestName.trim();
      else fields.guest_id = null;
    } else {
      fields.host_username = host === NOBODY ? "" : host;
    }
    return fields;
  };

  // The dates of a series, with their clashes, before anything is created.
  useEffect(() => {
    if (!creating || rule === NO_REPEAT || !ready || startMinute == null || endMinute == null) {
      setPreview(null);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      const fields = baseFields();
      if (!fields) return;
      previewDiffusions({
        ...fields,
        title: fields.title || "Aperçu",
        repeat: { rule: rule as RepeatRule, count: Math.max(1, Math.min(52, Number(count) || 1)) },
      })
        .then((result) => {
          if (!alive) return;
          setPreview(result.occurrences);
          setPreviewNth(result.nth);
          setPicked(new Set(result.occurrences.filter((item) => !item.problem).map((item) => item.start)));
          setFailure("");
        })
        .catch((caught: unknown) => {
          if (!alive) return;
          setPreview(null);
          setFailure(errorText(caught, "Aperçu impossible."));
        });
    }, 280);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [creating, rule, count, day, start, end, kind, ready]);

  const save = async () => {
    const fields = baseFields();
    if (!fields || !ready) return;
    setBusy("save");
    setFailure("");
    try {
      if (creating) {
        const repeat = rule !== NO_REPEAT;
        const rows = await createDiffusions(
          repeat
            ? {
                ...fields,
                repeat: { rule: rule as RepeatRule, count: Math.max(1, Math.min(52, Number(count) || 1)) },
                only: [...picked],
              }
            : fields,
        );
        const source = target?.mode === "create" ? target.copyFrom?.file : null;
        let created = rows;
        if (source) {
          created = [];
          for (const item of rows) created.push(await attachBankFile(item.id, source.path, source.duration));
        }
        if (created.length === 1) {
          await onChanged(`« ${created[0].title} » ajoutée, ${rangeLabel(created[0].starts_at, created[0].ends_at)}`);
          onEdit(created[0]);
        } else {
          await onChanged(`${created.length} dates ajoutées`);
          onClose();
        }
        return;
      }
      if (!row) return;
      const update: DiffusionFields = upcoming
        ? { ...fields, version: row.version, set_title: setTitleText, tracklist }
        : { version: row.version, title: title.trim(), set_title: setTitleText, tracklist };
      const saved = await updateDiffusion(row.id, update);
      setRow(saved);
      await onChanged(`« ${saved.title} » enregistrée`);
      onClose();
    } catch (caught) {
      setFailure(errorText(caught, "Enregistrement impossible."));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (following: boolean) => {
    if (!row) return;
    setBusy("delete");
    setFailure("");
    try {
      const count = await deleteDiffusion(row.id, following);
      await onChanged(count > 1 ? `${count} dates retirées de l'agenda` : `« ${row.title} » retirée de l'agenda`);
      onClose();
    } catch (caught) {
      setFailure(errorText(caught, "Suppression impossible."));
    } finally {
      setBusy(null);
    }
  };

  const stop = async () => {
    if (!row) return;
    setBusy("stop");
    try {
      setRow(await stopDiffusion(row.id));
      await onChanged("Arrêt demandé : la grille reprend dans quelques secondes");
    } catch (caught) {
      setFailure(errorText(caught, "Arrêt impossible."));
    } finally {
      setBusy(null);
      setConfirmStop(false);
    }
  };

  const fileAction = async (work: () => Promise<Diffusion>, text: string) => {
    setBusy("file");
    setFailure("");
    try {
      setRow(await work());
      await onChanged(text);
    } catch (caught) {
      setFailure(errorText(caught, "Action impossible."));
    } finally {
      setBusy(null);
    }
  };

  const status = row ? statusOf(row) : null;
  const weekday = day ? weekdayOf(day) : 0;
  const nth = preview ? previewNth : day ? nthOfMonth(day) : 1;
  const heading = row ? row.title : target?.mode === "create" && target.replacing ? "Remplacer ce jour-là" : "Nouvelle émission datée";

  return (
    <>
      <Dialog.Root
        open={target != null}
        onOpenChange={(open) => {
          if (!open && !busy) onClose();
        }}
      >
        <Dialog.Content
          ref={contentRef}
          maxWidth="38rem"
          className="ag-dialog"
          tabIndex={-1}
          onOpenAutoFocus={(event) => {
            // A new date starts with its title; an open one with nothing selected.
            event.preventDefault();
            if (target?.mode === "create") titleRef.current?.focus();
            else contentRef.current?.focus();
          }}
        >
          <Dialog.Title>{heading}</Dialog.Title>
          <Dialog.Description size="2" color="gray" mb="3">
            {row
              ? rangeLabel(row.starts_at, row.ends_at)
              : target?.mode === "create" && target.replacing
                ? `« ${target.replacing.title} » ne passe pas ce jour-là : cette émission prend sa place.`
                : "Elle passe devant la semaine type ; la grille reprend à la fin."}
          </Dialog.Description>

          {row && status ? (
            <p className={`ag-status tone-${status.tone}`} role="status">
              <span className={`ag-chip tone-${status.tone}`}>{status.label}</span>
              {status.detail ? <span>{status.detail}</span> : null}
              {row.aired_start ? (
                <span className="is-faint">
                  {row.air_status === "on_air" ? "depuis" : "de"} {timeLabel(row.aired_start)}
                  {row.aired_end && row.air_status !== "on_air" ? ` à ${timeLabel(row.aired_end)}` : ""}
                </span>
              ) : null}
            </p>
          ) : null}

          <form
            className="prog-dialog-form"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <div className="ag-kind">
              <span className="ui-field-label">Type</span>
              <SegmentedControl.Root
                size="2"
                value={kind}
                onValueChange={(value) => setKind(value as AgendaKind)}
                disabled={!canEditWhen || (row != null && row.file != null)}
              >
                <SegmentedControl.Item value="set">
                  <span className="ag-kind-option">
                    <Disc3 size={14} aria-hidden="true" />
                    Set enregistré
                  </span>
                </SegmentedControl.Item>
                <SegmentedControl.Item value="live">
                  <span className="ag-kind-option">
                    <Mic size={14} aria-hidden="true" />
                    Direct
                  </span>
                </SegmentedControl.Item>
              </SegmentedControl.Root>
            </div>
            <FormField label="Titre" hint="Le nom affiché à l'antenne. Il donne aussi le dossier du set.">
              <TextField.Root
                ref={titleRef}
                size="2"
                className="ui-field-control"
                value={title}
                placeholder="Ex. Carte blanche"
                list="ag-titles"
                disabled={!editable}
                onChange={(event) => setTitle(event.target.value)}
              />
              <datalist id="ag-titles">
                {titles.map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </FormField>
            <div className="prog-dialog-row prog-dialog-row--3">
              <FormField label="Date">
                <TextField.Root
                  size="2"
                  type="date"
                  className="ui-field-control"
                  value={day}
                  disabled={!canEditWhen}
                  onChange={(event) => setDay(event.target.value)}
                />
              </FormField>
              <FormField label="Début">
                <TextField.Root
                  size="2"
                  type="time"
                  step={300}
                  className="ui-field-control"
                  value={start}
                  disabled={!canEditWhen}
                  onChange={(event) => setStart(event.target.value)}
                />
              </FormField>
              <FormField label="Fin" hint={endRaw != null && startMinute != null && endRaw <= startMinute ? "le lendemain" : undefined}>
                <TextField.Root
                  size="2"
                  type="time"
                  step={300}
                  className="ui-field-control"
                  value={end}
                  disabled={!canEditWhen}
                  onChange={(event) => setEnd(event.target.value)}
                />
              </FormField>
            </div>
            {day && startMinute != null && endMinute != null ? (
              <p className="ag-hint">
                {dayLongLabel(day)}, {start} → {end} · {durationLabel(lasting)} · heure de Paris
              </p>
            ) : null}

            {kind === "set" ? (
              <FormField
                label="Invité"
                hint={
                  matchedGuest
                    ? "Même lien que ses autres dates."
                    : guestName.trim()
                      ? "Nouvel invité : un lien sera créé."
                      : "Sans invité, choisis le fichier dans la banque."
                }
              >
                <TextField.Root
                  size="2"
                  className="ui-field-control"
                  value={guestName}
                  placeholder="Nom de l'invité (facultatif)"
                  list="ag-guests"
                  disabled={!canEditWhen}
                  onChange={(event) => setGuestName(event.target.value)}
                />
                <datalist id="ag-guests">
                  {guests.map((guest) => (
                    <option key={guest.id} value={guest.name} />
                  ))}
                </datalist>
              </FormField>
            ) : (
              <div className="ui-field">
                <span className="ui-field-label">Animateur</span>
                <Select.Root size="2" value={host} onValueChange={setHost} disabled={!canEditWhen}>
                  <Select.Trigger className="ui-field-control" aria-label="Animateur" />
                  <Select.Content variant="soft" position="popper">
                    <Select.Item value={NOBODY}>À choisir</Select.Item>
                    {hosts.length ? <Select.Separator /> : null}
                    {hosts.map((name) => (
                      <Select.Item key={name} value={name}>
                        {name}
                      </Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
                <span className="ui-field-hint">
                  Son compte peut se brancher de 15 min avant le début jusqu'à la fin. Nommer un animateur ferme le direct
                  aux autres comptes hors de leurs créneaux.
                </span>
                {hostsNote ? <span className="ui-field-error">{hostsNote}</span> : null}
              </div>
            )}

            {creating ? (
              <div className="ag-repeat">
                <div className="prog-dialog-row">
                  <div className="ui-field">
                    <span className="ui-field-label">Répéter</span>
                    <Select.Root size="2" value={rule} onValueChange={setRule}>
                      <Select.Trigger className="ui-field-control" aria-label="Répéter" />
                      <Select.Content variant="soft" position="popper">
                        <Select.Item value={NO_REPEAT}>Une seule fois</Select.Item>
                        <Select.Item value="weekly">{repeatLabel("weekly", nth, weekday)}</Select.Item>
                        <Select.Item value="biweekly">{repeatLabel("biweekly", nth, weekday)}</Select.Item>
                        <Select.Item value="monthly">{repeatLabel("monthly", nth, weekday)}</Select.Item>
                      </Select.Content>
                    </Select.Root>
                  </div>
                  {rule !== NO_REPEAT ? (
                    <FormField label="Nombre de dates">
                      <TextField.Root
                        size="2"
                        type="number"
                        min={1}
                        max={52}
                        className="ui-field-control"
                        value={count}
                        onChange={(event) => setCount(event.target.value)}
                      />
                    </FormField>
                  ) : null}
                </div>
                {preview ? (
                  <ul className="ag-preview-list" aria-label="Dates de la série">
                    {preview.map((item) => {
                      const checked = picked.has(item.start);
                      return (
                        <li key={item.start} className={item.problem ? "is-problem" : undefined}>
                          <label>
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={Boolean(item.problem)}
                              onChange={() => {
                                const next = new Set(picked);
                                if (checked) next.delete(item.start);
                                else next.add(item.start);
                                setPicked(next);
                              }}
                            />
                            <span>{item.label}</span>
                          </label>
                          {item.problem ? <small>{item.problem}</small> : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {row && kind === "set" ? (
              <>
                <FileSection
                  row={row}
                  editable={editable}
                  onPick={() => setBankOpen(true)}
                  onRemove={() => fileAction(() => detachFile(row.id), "Fichier retiré")}
                />
                <InviteBox
                  row={row}
                  station={station}
                  onRenew={async () => {
                    if (!row.guest) return;
                    await renewGuestLink(row.guest.id);
                    setRow(await getDiffusion(row.id));
                    await onChanged("Nouveau lien créé : l'ancien ne marche plus");
                  }}
                />
                <section className="ag-section" aria-label="Infos du set">
                  <header className="ag-section-head">
                    <h3>Infos du set</h3>
                    <small className={row.rights ? "" : "is-faint"}>
                      {row.rights ? "Droits de diffusion confirmés" : row.guest ? "Droits pas encore confirmés" : ""}
                    </small>
                  </header>
                  <FormField label="Titre du set">
                    <TextField.Root
                      size="2"
                      className="ui-field-control"
                      value={setTitleText}
                      disabled={!editable}
                      onChange={(event) => setSetTitleText(event.target.value)}
                    />
                  </FormField>
                  <FormField label="Tracklist" hint="Gardée pour les déclarations SACEM/SCPP.">
                    <TextArea
                      size="2"
                      rows={4}
                      value={tracklist}
                      disabled={!editable}
                      onChange={(event) => setTracklist(event.target.value)}
                    />
                  </FormField>
                </section>
              </>
            ) : null}

            {row && row.air_status === "on_air" && row.kind === "set" && canStop && !row.stop_requested ? (
              <div className="ag-stop">
                <Button
                  type="button"
                  size="2"
                  color="red"
                  variant={confirmStop ? "solid" : "soft"}
                  disabled={busy != null}
                  onClick={() => (confirmStop ? void stop() : setConfirmStop(true))}
                >
                  <Square className="ui-button-icon" />
                  {confirmStop ? "Confirmer : arrêter et reprendre la grille" : "Arrêter et reprendre la grille"}
                </Button>
              </div>
            ) : null}

            {failure ? (
              <p className="prog-dialog-error" role="alert">
                {failure}
              </p>
            ) : null}

            <div className="prog-dialog-actions">
              {row && editable ? (
                <span className="prog-dialog-side">
                  {confirmDelete ? (
                    <>
                      <Button
                        type="button"
                        size="2"
                        color="red"
                        disabled={busy != null}
                        onClick={() => void remove(confirmDelete === "following")}
                      >
                        <Trash2 className="ui-button-icon" />
                        {busy === "delete" ? "Retrait…" : "Confirmer"}
                      </Button>
                      {row.series_id ? (
                        <Select.Root
                          size="2"
                          value={confirmDelete}
                          onValueChange={(value) => setConfirmDelete(value as "one" | "following")}
                        >
                          <Select.Trigger aria-label="Quelles dates" />
                          <Select.Content variant="soft" position="popper">
                            <Select.Item value="one">Cette date</Select.Item>
                            <Select.Item value="following">Celle-ci et les suivantes</Select.Item>
                          </Select.Content>
                        </Select.Root>
                      ) : null}
                    </>
                  ) : (
                    <>
                      <Button
                        type="button"
                        size="2"
                        variant="ghost"
                        color="red"
                        disabled={busy != null || row.air_status === "on_air"}
                        onClick={() => setConfirmDelete("one")}
                      >
                        <Trash2 className="ui-button-icon" />
                        Retirer
                      </Button>
                      <Button
                        type="button"
                        size="2"
                        variant="ghost"
                        color="gray"
                        disabled={busy != null}
                        onClick={() => onDuplicate(row)}
                      >
                        <CopyPlus className="ui-button-icon" />
                        Dupliquer…
                      </Button>
                    </>
                  )}
                </span>
              ) : null}
              <Dialog.Close>
                <Button type="button" size="2" variant="soft" color="gray" disabled={busy != null}>
                  Annuler
                </Button>
              </Dialog.Close>
              {editable ? (
                <Button type="submit" size="2" highContrast disabled={busy != null || !ready || (creating && rule !== NO_REPEAT && !picked.size)}>
                  {busy === "save"
                    ? "Enregistrement…"
                    : creating
                      ? rule !== NO_REPEAT
                        ? `Ajouter ${picked.size} date${picked.size > 1 ? "s" : ""}`
                        : "Ajouter"
                      : "Enregistrer"}
                </Button>
              ) : null}
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Root>
      {row ? (
        <BankPicker
          open={bankOpen}
          slotMinutes={row.duration_min}
          onClose={() => setBankOpen(false)}
          onPick={async (hit) => {
            await fileAction(() => attachBankFile(row.id, hit.path, hit.duration), "Fichier choisi : analyse en cours");
            setBankOpen(false);
          }}
        />
      ) : null}
    </>
  );
}
