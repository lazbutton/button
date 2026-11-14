import { Button, Checkbox, Dialog, Spinner, TextField } from "@radix-ui/themes";
import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { DROPBOX_NOTE } from "../../api/bankCarts";
import { titlesLabel } from "../../api/bankContent";
import { DEFAULT_STATE, cell, fileName, titlesCount, titlesQuery, type BankTitle, type BankTitlesPage } from "../../api/bankTitles";
import { apiGet } from "../../api/client";
import { formatClock } from "../../api/soundsView";

/**
 * « Ajouter ▾ → Titres de la banque » in a cart (FON-69): the bank's titles,
 * searched as in its table, chosen with a checkbox, added without a copy. The
 * cart plays them where they are, in the rotation or a collection.
 */
export function BankTitlesPicker({
  cartTitle,
  inCart,
  onClose,
  onAdd,
}: {
  cartTitle: string;
  /** The paths below the bank the cart already plays. */
  inCart: Set<string>;
  onClose: () => void;
  /** Rejects with the engine's refusal, shown in the dialog. */
  onAdd: (paths: string[]) => Promise<void>;
}) {
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState<BankTitlesPage | null>(null);
  const [chosen, setChosen] = useState<Map<string, BankTitle>>(() => new Map());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const ticket = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(typed.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [typed]);

  useEffect(() => {
    const mine = ++ticket.current;
    const state = { ...DEFAULT_STATE, q: query };
    void apiGet<BankTitlesPage>(`/media/titles.json${titlesQuery(state, 0, 60)}`).then(
      (next) => {
        if (mine !== ticket.current) return;
        setPage(next);
        setProblem("");
      },
      (caught) => {
        if (mine === ticket.current) setProblem(caught instanceof Error ? caught.message : "La banque ne s'est pas lue.");
      },
    );
  }, [query]);

  const toggle = (title: BankTitle) =>
    setChosen((before) => {
      const next = new Map(before);
      if (next.has(title.path)) next.delete(title.path);
      else next.set(title.path, title);
      return next;
    });

  const add = async () => {
    if (!chosen.size || busy) return;
    setBusy(true);
    setProblem("");
    try {
      await onAdd([...chosen.keys()]);
      onClose();
    } catch (caught) {
      setProblem(caught instanceof Error && caught.message ? caught.message : "Les titres n'ont pas été ajoutés. Réessaie.");
    } finally {
      setBusy(false);
    }
  };

  const shown = page?.titles ?? [];
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="38rem" className="bacs-picker">
        <Dialog.Title>Titres de la banque pour « {cartTitle} »</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="3">
          Sans copie : le bac les joue là où ils sont, dans la rotation ou une collection. Les retirer du bac ne touche pas
          leur fichier.
        </Dialog.Description>
        <TextField.Root
          size="2"
          placeholder="Titre, artiste, album, fichier"
          value={typed}
          aria-label="Chercher dans la banque"
          autoFocus
          onChange={(event) => setTyped(event.target.value)}
        >
          <TextField.Slot>
            <Search size={15} aria-hidden="true" />
          </TextField.Slot>
        </TextField.Root>
        <div className="bacs-picker-list" role="group" aria-label="Titres de la banque" aria-busy={!page}>
          {!page ? (
            problem ? null : (
              <p className="bacs-dialog-note">
                <Spinner size="1" /> Lecture de la banque…
              </p>
            )
          ) : shown.length === 0 ? (
            <p className="bacs-dialog-note">{query ? `Aucun titre ne correspond à « ${query} ».` : "La banque n'a encore aucun titre."}</p>
          ) : (
            shown.map((title) => {
              const already = inCart.has(title.path);
              const name = title.title || fileName(title.path);
              return (
                <label key={title.id} className={`bacs-picker-row${already ? " is-done" : ""}`}>
                  <Checkbox
                    size="2"
                    checked={already || chosen.has(title.path)}
                    disabled={already || busy}
                    onCheckedChange={() => toggle(title)}
                  />
                  <span className="bacs-picker-copy">
                    <strong>{name}</strong>
                    <span>
                      {[cell(title.artist), title.album || null, already ? "déjà dans le bac" : null].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <span className="bacs-picker-len">{title.duration ? formatClock(title.duration) : ""}</span>
                </label>
              );
            })
          )}
        </div>
        {page && page.matched > shown.length ? (
          <p className="bacs-dialog-note">
            {shown.length} sur {titlesCount(page.matched).toLowerCase()} : précise la recherche pour trouver les autres.
          </p>
        ) : null}
        <p className="bacs-dialog-note">{DROPBOX_NOTE}</p>
        {problem ? (
          <p className="bacs-dialog-error" role="alert">
            {problem}
          </p>
        ) : null}
        <div className="bacs-dialog-actions">
          <Dialog.Close>
            <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button size="2" highContrast disabled={!chosen.size || busy} onClick={() => void add()}>
            {busy ? "Ajout…" : chosen.size ? `Ajouter ${titlesLabel(chosen.size).toLowerCase()}` : "Ajouter"}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
