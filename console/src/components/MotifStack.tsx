import { Button, IconButton, Select, Spinner, Tooltip } from "@radix-ui/themes";
import { ArrowDown, ArrowUp, Repeat2, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { kindLabel, motifStepMissingCart } from "../api/clockMeta";
import type { Cart, Clock, PositionKind } from "../api/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { EmptyState } from "../ui/EmptyState";
import { Panel, SectionHeader } from "../ui/Panel";

const NONE = "__none__";

export function MotifStack({
  clock,
  carts = [],
  busy = false,
  onChangeCart,
  onRemove,
  onReorder,
  onAddKind,
  onSeedDefault,
  onRepair,
}: {
  clock: Clock;
  carts?: Cart[];
  busy?: boolean;
  onChangeCart: (index: number, cart: Cart) => void | Promise<unknown>;
  onRemove: (index: number) => void | Promise<unknown>;
  onReorder: (from: number, to: number) => void | Promise<unknown>;
  onAddKind: (kind: Exclude<PositionKind, "musique">) => void | Promise<unknown>;
  onSeedDefault?: () => void | Promise<unknown>;
  onRepair?: (index: number) => void;
}) {
  return (
    <Panel className="autodj-loop">
      <SectionHeader
        title="Ce qui passe, dans l’ordre"
        description="Dans l’ordre, puis ça recommence."
        count={clock.motif.length}
      />

      {clock.motif.length ? (
        <ol className="autodj-loop-list" aria-label="Rotation" aria-busy={busy}>
          {clock.motif.map((step, index) => {
            const missing = motifStepMissingCart(step, carts);
            const current =
              carts.find((row) => row.id === step.cart_id) ??
              carts.find((row) => row.title === step.cart) ??
              null;
            const cartId = current ? String(current.id) : NONE;
            const count = current?.sounds.length ?? 0;
            return (
              <li
                key={`${step.kind}-${step.id ?? index}`}
                className={`autodj-loop-row${missing ? " is-missing" : ""}`}
              >
                <span className={`hour-dot hour-dot--${step.kind}`} aria-hidden="true" />
                <span className="autodj-loop-role">
                  <strong>{kindLabel(step.kind)}</strong>
                  {missing ? (
                    <span className="autodj-loop-missing">
                      Cart manquant
                      {onRepair ? (
                        <button
                          type="button"
                          className="autodj-loop-repair"
                          disabled={busy}
                          onClick={() => onRepair(index)}
                        >
                          Réparer
                        </button>
                      ) : null}
                    </span>
                  ) : null}
                </span>
                <Select.Root
                  value={cartId}
                  disabled={busy || !carts.length}
                  onValueChange={(value) => {
                    const picked = carts.find((row) => String(row.id) === value);
                    if (picked) void onChangeCart(index, picked);
                  }}
                >
                  <Select.Trigger
                    className="autodj-loop-cart"
                    aria-label={`Cart ${kindLabel(step.kind)}`}
                    placeholder="Choisir un cart…"
                  />
                  <Select.Content position="popper">
                    {cartId === NONE ? (
                      <Select.Item value={NONE} disabled>
                        Choisir un cart…
                      </Select.Item>
                    ) : null}
                    {carts.map((row) => (
                      <Select.Item key={row.id} value={String(row.id)}>
                        {row.title}
                      </Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
                {current ? (
                  <Link className="autodj-loop-count" to={`/sons?id=${current.id}`}>
                    {count === 1 ? "1 son" : `${count}\u00a0sons`}
                  </Link>
                ) : (
                  <span className="autodj-loop-count is-missing">—</span>
                )}
                <div className="autodj-loop-actions">
                  <Tooltip content="Monter">
                    <IconButton
                      size="1"
                      variant="ghost"
                      color="gray"
                      disabled={busy || index === 0}
                      aria-label={`Monter ${kindLabel(step.kind)}`}
                      onClick={() => void onReorder(index, index - 1)}
                    >
                      <ArrowUp className="ui-button-icon" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip content="Descendre">
                    <IconButton
                      size="1"
                      variant="ghost"
                      color="gray"
                      disabled={busy || index === clock.motif.length - 1}
                      aria-label={`Descendre ${kindLabel(step.kind)}`}
                      onClick={() => void onReorder(index, index + 1)}
                    >
                      <ArrowDown className="ui-button-icon" />
                    </IconButton>
                  </Tooltip>
                  <ConfirmDialog
                    title={`Retirer ${kindLabel(step.kind)} ?`}
                    description={`${current?.title || step.cart || "Ce cart"} sort de la rotation.`}
                    confirmLabel="Retirer"
                    busy={busy}
                    onConfirm={async () => {
                      await onRemove(index);
                    }}
                    trigger={
                      <IconButton
                        size="1"
                        variant="ghost"
                        color="red"
                        disabled={busy}
                        aria-label={`Retirer ${kindLabel(step.kind)}`}
                      >
                        <Trash2 className="ui-button-icon" />
                      </IconButton>
                    }
                  />
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <EmptyState
          icon={Repeat2}
          title="Rien ne tourne encore"
          description="Un jingle coupe le titre. Un programme enchaîne les morceaux."
          actionLabel={onSeedDefault ? "Mettre Jingles et Prog" : undefined}
          onAction={busy || !onSeedDefault ? undefined : () => void onSeedDefault()}
        />
      )}

      <div className="autodj-loop-add">
        <Button size="1" variant="soft" disabled={busy} onClick={() => void onAddKind("jingle")}>
          Ajouter un jingle
        </Button>
        <Button size="1" variant="soft" disabled={busy} onClick={() => void onAddKind("son")}>
          Ajouter un programme
        </Button>
        <Button size="1" variant="soft" disabled={busy} onClick={() => void onAddKind("pub")}>
          Ajouter des pubs
        </Button>
        {busy ? <Spinner size="1" /> : null}
      </div>
      <p className="motif-loop-note">
        Un jingle coupe le titre en cours. Un programme enchaîne les morceaux.
      </p>
    </Panel>
  );
}
