import { Button, TextField } from "@radix-ui/themes";
import { Save } from "lucide-react";
import { useEffect, useState } from "react";
import { relayUrlOk } from "../../api/cartMeta";
import type { Cart } from "../../api/types";
import { FormField } from "../../ui/FormField";
import { Panel, SectionHeader } from "../../ui/Panel";

export function RelayEditor({
  cart,
  busy,
  onSave,
}: {
  cart: Cart;
  busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [url, setUrl] = useState(cart.url || "");
  const [maxDuration, setMaxDuration] = useState(cart.max_duration ? String(cart.max_duration) : "");

  useEffect(() => {
    setUrl(cart.url || "");
    setMaxDuration(cart.max_duration ? String(cart.max_duration) : "");
  }, [cart.id, cart.url, cart.max_duration]);

  const seconds = Number(maxDuration);
  const ready = relayUrlOk(url) && Number.isFinite(seconds) && seconds > 0;
  const dirty = url !== (cart.url || "") || maxDuration !== (cart.max_duration ? String(cart.max_duration) : "");

  return (
    <Panel padded={false} className="app-carts-relay">
      <div className="app-carts-sounds-toolbar">
        <SectionHeader title={cart.title} description="Flux entrant. Le flux public ne change pas." />
      </div>
      <form
        className="app-carts-relay-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!ready || busy) return;
          void onSave({ url: url.trim(), max_duration: seconds });
        }}
      >
        <FormField label="URL du flux" hint="HTTP ou HTTPS, avec un chemin.">
          <TextField.Root
            className="ui-field-control"
            value={url}
            placeholder="https://radio.exemple/flux.mp3"
            onChange={(event) => setUrl(event.target.value)}
          />
        </FormField>
        <FormField label="Durée max (secondes)" hint="Obligatoire. Le relais s’arrête au bout de ce temps.">
          <TextField.Root
            className="ui-field-control"
            type="number"
            min={1}
            value={maxDuration}
            onChange={(event) => setMaxDuration(event.target.value)}
          />
        </FormField>
        <div className="app-carts-relay-actions">
          <Button type="submit" size="1" disabled={busy || !dirty || !ready}>
            <Save className="ui-button-icon" />
            {busy ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}
