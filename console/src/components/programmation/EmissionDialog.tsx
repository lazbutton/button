import { Button, Dialog, Select, TextField } from "@radix-ui/themes";
import { Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiPostJson, apiPut } from "../../api/client";
import { hostChoices } from "../../api/hosts";
import { errorText } from "../../api/programmationErrors";
import { DAY_LONG, hhmm, parseHhmm } from "../../api/programmationView";
import type { Emission } from "../../api/types";
import { useHosts } from "../../lib/useHosts";
import { FormField } from "../../ui/FormField";

export type EmissionTarget = { day: number; row?: Emission; start?: number };

const NOBODY = "none";

/** A weekly live show: it plays over the heure type, once the studio is connected. */
export function EmissionDialog({
  target,
  onClose,
  onDone,
}: {
  target: EmissionTarget | null;
  onClose: () => void;
  onDone: (message: string) => Promise<void>;
}) {
  const row = target?.row;
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [host, setHost] = useState(NOBODY);
  const [day, setDay] = useState(0);
  const [start, setStart] = useState("20:00");
  const [end, setEnd] = useState("22:00");
  const [busy, setBusy] = useState<"save" | "delete" | null>(null);
  const [failure, setFailure] = useState("");
  const [confirming, setConfirming] = useState(false);
  const hostList = useHosts(target != null);

  useEffect(() => {
    if (!target) return;
    setFailure("");
    setBusy(null);
    setConfirming(false);
    setTitle(target.row?.title ?? "");
    setArtist(target.row?.artist ?? "");
    setHost(target.row?.host_username?.trim() || NOBODY);
    setDay(target.row?.day_of_week ?? target.day);
    const from = target.row?.start_minute ?? target.start ?? 20 * 60;
    setStart(hhmm(from));
    setEnd(hhmm(target.row?.end_minute ?? Math.min(from + 120, 1440)));
  }, [target]);

  const hosts = useMemo(() => hostChoices(hostList.names, host === NOBODY ? "" : host), [host, hostList.names]);

  const startMinute = parseHhmm(start);
  const endMinute = parseHhmm(end);
  const timeProblem =
    startMinute == null || endMinute == null
      ? "Heure de début ou de fin à compléter."
      : endMinute <= startMinute
        ? "La fin doit venir après le début, le même jour."
        : "";
  const ready = Boolean(title.trim()) && Boolean(artist.trim()) && !timeProblem;

  const save = async () => {
    if (!ready || startMinute == null || endMinute == null) return;
    setBusy("save");
    setFailure("");
    const body = {
      scope: "weekly" as const,
      title: title.trim(),
      artist: artist.trim(),
      day_of_week: day,
      start_minute: startMinute,
      end_minute: endMinute,
      host_username: host === NOBODY ? "" : host,
      version: row?.version,
    };
    try {
      if (row) await apiPut(`/antenne/emissions/${row.id}.json`, body);
      else await apiPostJson("/antenne/emissions.json", body);
      await onDone(
        row ? `« ${body.title} » enregistrée` : `« ${body.title} » ajoutée, ${DAY_LONG[day].toLowerCase()} ${start}`,
      );
      onClose();
    } catch (caught) {
      setFailure(errorText(caught, "Enregistrement impossible."));
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!row) return;
    setBusy("delete");
    setFailure("");
    try {
      await apiDelete(`/antenne/emissions/${row.id}.json`);
      await onDone(`« ${row.title} » retirée de la semaine`);
      onClose();
    } catch (caught) {
      setFailure(errorText(caught, "Suppression impossible."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog.Root
      open={target != null}
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="32rem">
        <Dialog.Title>{row ? "Émission en direct" : "Nouvelle émission en direct"}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          L'heure type continue tant que personne n'est branché. Dès que le studio se connecte, le nom de l'émission et
          la phrase s'affichent.
        </Dialog.Description>
        <form
          className="prog-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <FormField label="Nom de l'émission">
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={title}
              placeholder="Hop Pop Hop"
              autoFocus
              onChange={(event) => setTitle(event.target.value)}
            />
          </FormField>
          <FormField label="Phrase artiste" hint="S'affiche comme artiste pendant l'émission.">
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={artist}
              placeholder="avec Marie et Jean"
              onChange={(event) => setArtist(event.target.value)}
            />
          </FormField>
          <div className="prog-dialog-row prog-dialog-row--3">
            <div className="ui-field">
              <span className="ui-field-label">Jour</span>
              <Select.Root size="2" value={String(day)} onValueChange={(value) => setDay(Number(value))}>
                <Select.Trigger className="ui-field-control" aria-label="Jour" />
                <Select.Content variant="soft" position="popper">
                  {DAY_LONG.map((name, index) => (
                    <Select.Item key={name} value={String(index)}>
                      {name}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </div>
            <FormField label="Début">
              <TextField.Root
                size="2"
                type="time"
                className="ui-field-control"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </FormField>
            <FormField label="Fin">
              <TextField.Root
                size="2"
                type="time"
                className="ui-field-control"
                value={end === "24:00" ? "23:59" : end}
                onChange={(event) => setEnd(event.target.value === "23:59" ? "24:00" : event.target.value)}
              />
            </FormField>
          </div>
          {timeProblem && (start || end) ? <p className="prog-dialog-note">{timeProblem}</p> : null}
          <div className="ui-field">
            <span className="ui-field-label">Compte du plateau</span>
            <Select.Root size="2" value={host} onValueChange={setHost}>
              <Select.Trigger className="ui-field-control" aria-label="Compte du plateau" />
              <Select.Content variant="soft" position="popper">
                <Select.Item value={NOBODY}>Pas encore nominatif</Select.Item>
                {hosts.length ? <Select.Separator /> : null}
                {hosts.map((name) => (
                  <Select.Item key={name} value={name}>
                    {name}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <span className="ui-field-hint">
              Tant qu'aucune émission ne nomme un compte, tout compte qui peut passer en direct se branche. Dès qu'une
              émission en nomme un, chacun passe sur son créneau. Un admin passe toujours.
            </span>
            {hostList.note ? <span className="ui-field-error">{hostList.note}</span> : null}
          </div>
          {failure ? (
            <p className="prog-dialog-error" role="alert">
              {failure}
            </p>
          ) : null}
          <div className="prog-dialog-actions">
            {row ? (
              <span className="prog-dialog-side">
                <Button
                  type="button"
                  size="2"
                  variant={confirming ? "solid" : "ghost"}
                  color="red"
                  highContrast={confirming}
                  disabled={busy != null}
                  onClick={() => (confirming ? void remove() : setConfirming(true))}
                >
                  <Trash2 className="ui-button-icon" />
                  {busy === "delete" ? "Retrait…" : confirming ? "Confirmer le retrait" : "Retirer"}
                </Button>
                {confirming ? <small>L'heure type de la plage continue.</small> : null}
              </span>
            ) : null}
            <Dialog.Close>
              <Button type="button" size="2" variant="soft" color="gray" disabled={busy != null}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" size="2" highContrast disabled={busy != null || !ready}>
              {busy === "save" ? "Enregistrement…" : row ? "Enregistrer" : "Ajouter"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
