import { Button, IconButton, Tooltip } from "@radix-ui/themes";
import { ArrowLeft, PanelRight, RadioTower } from "lucide-react";
import type { ReactNode } from "react";
import { MODE_LABELS } from "../../api/cartMeta";
import { bacKind } from "../../api/soundsView";
import type { Cart } from "../../api/types";
import { MODE_ICONS } from "./bacIcons";

/** Where the clocks use a bac: a short label, a tooltip, one line per use. */
export type BacUsage = {
  programmed: boolean;
  inClock: boolean;
  label: string;
  detail: string;
  lines: string[];
};

export function BacHeader({
  cart,
  usage,
  facts,
  inspectorOpen,
  onToggleInspector,
  onBack,
  onFire,
  firing,
}: {
  cart: Cart;
  usage: BacUsage;
  facts: ReactNode;
  inspectorOpen: boolean;
  onToggleInspector: () => void;
  onBack: () => void;
  onFire: () => void;
  firing: boolean;
}) {
  const kind = bacKind(cart);
  const Icon = MODE_ICONS[cart.mode];

  return (
    <header className="bacs-head">
      <IconButton
        size="2"
        variant="ghost"
        color="gray"
        className="bacs-back"
        aria-label="Retour à la liste des bacs"
        onClick={onBack}
      >
        <ArrowLeft size={18} />
      </IconButton>
      <span className={`bacs-tile bacs-tile--lg is-${kind}`} aria-hidden="true">
        <Icon size={18} strokeWidth={1.75} />
      </span>
      <div className="bacs-head-copy">
        <h1 className="bacs-head-title">{cart.title}</h1>
        <p className="bacs-facts">
          <span>{MODE_LABELS[cart.mode]}</span>
          {facts}
          <span className={`bacs-usage${usage.programmed ? " is-on" : ""}`} title={usage.detail || undefined}>
            <i aria-hidden="true" />
            {usage.label}
          </span>
        </p>
      </div>
      <div className="bacs-head-actions">
        <Tooltip content="Envoyer ce bac à l'antenne maintenant">
          <Button size="2" variant="soft" color="gray" disabled={firing} onClick={onFire}>
            <RadioTower className="ui-button-icon" />
            <span className="bacs-hide-narrow">Diffuser maintenant</span>
            <span className="bacs-show-narrow">Diffuser</span>
          </Button>
        </Tooltip>
        <Tooltip content={inspectorOpen ? "Masquer les réglages" : "Nom, lecture, dossier, suppression"}>
          <Button
            size="2"
            variant={inspectorOpen ? "soft" : "outline"}
            color="gray"
            className="bacs-settings-toggle"
            aria-pressed={inspectorOpen}
            aria-label="Réglages du bac"
            onClick={onToggleInspector}
          >
            <PanelRight className="ui-button-icon" />
            Réglages
          </Button>
        </Tooltip>
      </div>
    </header>
  );
}
