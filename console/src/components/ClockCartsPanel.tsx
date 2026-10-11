import { Badge, Button } from "@radix-ui/themes";
import { Link } from "react-router-dom";
import { Clock3, Library } from "lucide-react";
import { autodjCartRows, clockHasCart } from "../api/clockMeta";
import type { Cart, Clock } from "../api/types";
import { Panel, SectionHeader } from "../ui/Panel";

export function ClockCartsPanel({
  clock,
  carts,
  busy = false,
  onAdd,
}: {
  clock: Clock;
  carts: Cart[];
  busy?: boolean;
  onAdd: () => void;
}) {
  const attached = autodjCartRows([clock], carts);
  const unused = carts.filter((cart) => !clockHasCart(clock, cart));

  return (
    <Panel className="clock-carts-panel">
      <SectionHeader
        title="Carts de cette heure type"
        description="Ce que l’Auto-DJ joue vraiment : Jingles et Prog, plus ce que tu accroches."
        count={attached.length}
        actions={
          <Button size="1" variant="soft" disabled={busy || !carts.length} onClick={onAdd}>
            <Clock3 className="ui-button-icon" />
            Accrocher un cart
          </Button>
        }
      />
      {attached.length ? (
        <ul className="clock-carts-list">
          {attached.map((row) => (
            <li key={row.cart.id}>
              <Link to={`/sons?id=${row.cart.id}`} className="clock-carts-link">
                <strong>{row.cart.title}</strong>
                <span>
                  {row.role}
                  {row.isDefaultProgramme ? " (défaut)" : ""}
                </span>
              </Link>
              <Badge size="1" variant="soft" color="gray">
                {row.cart.sounds.length} titre{row.cart.sounds.length === 1 ? "" : "s"}
              </Badge>
            </li>
          ))}
        </ul>
      ) : (
        <p className="clock-carts-empty">Aucun cart accroché. Ajoute Jingles puis Prog.</p>
      )}
      {unused.length ? (
        <p className="clock-carts-aside">
          Pas encore dans l’heure : {unused.map((cart) => cart.title).join(", ")}.
        </p>
      ) : null}
      <p className="clock-carts-new">
        <Library size={14} aria-hidden="true" />
        <Link to="/sons">Nouveau cart</Link> — crée-le, importe les fichiers, puis accroche-le ici.
      </p>
    </Panel>
  );
}
