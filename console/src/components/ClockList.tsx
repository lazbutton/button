import { Badge, Button, Dialog, Flex, Spinner, TextField } from "@radix-ui/themes";
import { Clock3, Plus, Radio, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Cart, Clock } from "../api/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { EntityListItem } from "../ui/EntityListItem";
import { FormField, SelectField } from "../ui/FormField";
import { Panel, SectionHeader } from "../ui/Panel";
import { ClockSpark } from "./HourStrip";

const NONE = "__none__";

export function ClockList({
  clocks,
  selectedId,
  carts,
  usage,
  usageReady,
  onAirName = "",
  onSelect,
  onCreate,
  onDelete,
  busy = false,
}: {
  clocks: Clock[];
  selectedId: number | null;
  carts: Cart[];
  usage: string[];
  usageReady: boolean;
  /** Nom de l’heure type en onde, quel que soit le choix dans la liste. */
  onAirName?: string;
  onSelect: (id: number) => void;
  onCreate: (name: string, fallback: string) => Promise<void> | void;
  onDelete?: (id: number) => Promise<void> | void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [fallback, setFallback] = useState(NONE);
  const [creating, setCreating] = useState(false);
  const cartNames = carts.map((cart) => cart.title);
  const selected = clocks.find((clock) => clock.id === selectedId) ?? null;
  const unavailable = busy || creating;

  return (
    <Panel className="horloges-library">
      <SectionHeader
        title="Heures types"
        description="Recettes réutilisables"
        count={clocks.length}
        actions={
          <Dialog.Root
            open={open}
            onOpenChange={(next) => {
              if (!creating) setOpen(next);
            }}
          >
            <Dialog.Trigger>
              <Button size="1" disabled={busy}>
                <Plus className="ui-button-icon" />
                Nouveau
              </Button>
            </Dialog.Trigger>
            <Dialog.Content maxWidth="26rem">
              <Dialog.Title>Nouvelle heure type</Dialog.Title>
              <Dialog.Description size="2" mb="4">
                Ce qui passe et les coupures à la minute se règlent ici.
              </Dialog.Description>
              <div className="horloges-dialog-fields">
                <FormField label="Nom" hint="Un nom court, visible dans la semaine.">
                  <TextField.Root
                    className="ui-field-control"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Journée pubs"
                    autoFocus
                  />
                </FormField>
                <SelectField
                  label="Si un bac est vide, jouer…"
                  value={fallback}
                  onValueChange={setFallback}
                  options={[
                    { value: NONE, label: "Aucun" },
                    ...cartNames.map((title) => ({ value: title, label: title })),
                  ]}
                  hint="Joué quand une étape n’a rien à passer."
                />
              </div>
              <Flex gap="2" mt="4" justify="end">
                <Dialog.Close>
                  <Button variant="soft" color="gray" disabled={creating}>
                    Annuler
                  </Button>
                </Dialog.Close>
                <Button
                  disabled={unavailable || !name.trim()}
                  onClick={() => {
                    void (async () => {
                      setCreating(true);
                      try {
                        await onCreate(name.trim(), fallback === NONE ? "" : fallback);
                        setName("");
                        setFallback(NONE);
                        setOpen(false);
                      } finally {
                        setCreating(false);
                      }
                    })();
                  }}
                >
                  {creating ? <Spinner size="1" /> : null}
                  {creating ? "Création…" : "Créer"}
                </Button>
              </Flex>
            </Dialog.Content>
          </Dialog.Root>
        }
      />

      <div className="ui-entity-list horloges-clock-list" role="list">
        {clocks.map((clock) => {
          const active = clock.id === selectedId;
          const live = Boolean(onAirName) && clock.name === onAirName;
          return (
            <div key={clock.id} role="listitem">
              <EntityListItem
                icon={Clock3}
                selected={active}
                className="horloges-clock-card"
                onClick={() => onSelect(clock.id)}
                title={
                  <span className="horloges-clock-card-title">
                    <span>{clock.name}</span>
                    {live ? (
                      <Badge size="1" color="green" variant="soft">
                        Antenne
                      </Badge>
                    ) : null}
                  </span>
                }
                meta={
                  <span className="horloges-clock-card-meta">
                    <ClockSpark clock={clock} />
                    <span>
                      {clock.motif.length} étape{clock.motif.length > 1 ? "s" : ""}
                      {clock.anchors.length
                        ? ` · :${clock.anchors.map((row) => row.minute).join(" / :")}`
                        : " · sans coupure"}
                    </span>
                  </span>
                }
                trailing={
                  live ? (
                    <span className="horloges-live-mark" title="À l’antenne">
                      <Radio size={14} aria-hidden="true" />
                    </span>
                  ) : null
                }
              />
            </div>
          );
        })}
      </div>

      <div className="horloges-library-footer">
        {onAirName ? (
          <p className="horloges-usage">
            <span className="ui-status-dot is-live" aria-hidden="true" />
            <span>
              {selected?.name === onAirName
                ? "Cette heure type est à l’antenne."
                : `À l’antenne : ${onAirName}.`}
            </span>
          </p>
        ) : null}
        {!usageReady ? (
          <p className="horloges-usage">Chargement des changements d’horloge…</p>
        ) : usage.length ? (
          <p className="horloges-usage">
            Dans la semaine : {usage.slice(0, 8).join(", ")}
            {usage.length > 8 ? "…" : ""} · <Link to="/programmation?onglet=semaine">Semaine</Link>
          </p>
        ) : (
          <p className="horloges-usage">
            Aucun changement d’horloge · <Link to="/programmation?onglet=semaine">Semaine</Link>
          </p>
        )}
      </div>

      {onDelete && selected ? (
        <ConfirmDialog
          title={`Supprimer « ${selected.name} » ?`}
          description="Cette heure type disparaît. Les changements d’horloge qui l’utilisent devront être revus."
          confirmLabel="Supprimer l’heure type"
          busy={busy}
          onConfirm={() => onDelete(selected.id)}
          trigger={
            <Button size="1" color="red" variant="soft" disabled={busy}>
              <Trash2 className="ui-button-icon" />
              Supprimer
            </Button>
          }
        />
      ) : null}
    </Panel>
  );
}
