import { Button, Checkbox, Dialog, IconButton, Spinner, TextField } from "@radix-ui/themes";
import { Plus, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { titlesLabel } from "../../api/bankContent";
import type { BankFacet, BankTitle, BankTitlesPage } from "../../api/bankTitles";
import { apiGet, apiPostJson } from "../../api/client";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";
import { TAGS_JSON, tagSuggestions, tagsOnTitles, withTag } from "../../api/stationTags";
import { MAX_LOT, type EditOutcome } from "../../api/titleEdits";
import { TryReport, messageOf, needsConfirmation } from "./TitleEditing";

/** Pose et retire des étiquettes sur un lot, ou l'essaie : ce qui changerait, les sélections touchées. */
export function tagTitles(ids: number[], add: string[], remove: string[], dryRun: boolean): Promise<EditOutcome> {
  return apiPostJson<EditOutcome>(TAGS_JSON, { ids, add, remove, dry_run: dryRun }, TITLES_SEND_DEADLINE_MS);
}

/**
 * « Étiquettes » (FON-74) : poser des étiquettes de la station sur les titres
 * choisis, et retirer celles qu'ils portent. La liste se crée à la volée : une
 * étiquette tapée qui n'existe pas encore naît avec le geste. Chaque titre garde
 * ses autres étiquettes, et le fichier n'est jamais touché. Un essai d'abord : il
 * ne demande confirmation que s'il a quelque chose à dire, comme le tableur.
 */
export function TagTitlesDialog({
  titles,
  onClose,
  onDone,
}: {
  titles: BankTitle[];
  onClose: () => void;
  onDone: (outcome: EditOutcome, add: string[], remove: string[]) => void;
}) {
  const base = useId();
  const [station, setStation] = useState<BankFacet[] | null>(null);
  const [stationProblem, setStationProblem] = useState("");
  const [typed, setTyped] = useState("");
  const [typedProblem, setTypedProblem] = useState("");
  const [adds, setAdds] = useState<string[]>([]);
  const [removes, setRemoves] = useState<string[]>([]);
  const [dropped, setDropped] = useState<number[]>([]);
  const [tried, setTried] = useState<EditOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  useEffect(() => {
    void apiGet<BankTitlesPage>("/media/titles.json?limit=1&facets=etiquette").then(
      (page) => setStation(page.facets.etiquette ?? []),
      (caught) => {
        setStation([]);
        setStationProblem(messageOf(caught, "Les étiquettes de la station ne se sont pas lues : tape la tienne."));
      },
    );
  }, []);

  const kept = useMemo(() => titles.filter((title) => !dropped.includes(title.id)), [titles, dropped]);
  const worn = useMemo(() => tagsOnTitles(titles), [titles]);
  const suggestions = useMemo(() => tagSuggestions(station ?? [], typed, adds), [station, typed, adds]);
  const what = titles.length === 1 ? "1 titre" : `${titles.length} titres`;
  const tooMany = kept.length > MAX_LOT;
  const none = adds.length === 0 && removes.length === 0;

  const change = (update: () => void) => {
    update();
    setTried(null);
    setFailure("");
  };

  const add = (raw: string) => {
    const next = withTag(adds, raw);
    setTypedProblem(next.problem);
    if (next.problem) return;
    change(() => {
      setAdds(next.tags);
      setRemoves((before) => before.filter((tag) => !next.tags.includes(tag)));
      setTyped("");
    });
  };

  const write = async (ids = kept.map((title) => title.id)) => {
    setBusy(true);
    setFailure("");
    try {
      onDone(await tagTitles(ids, adds, removes, false), adds, removes);
    } catch (caught) {
      setTried(null);
      setFailure(messageOf(caught, "Les étiquettes n'ont pas été écrites. Réessaie."));
      setBusy(false);
    }
  };

  // L'essai d'abord ; s'il n'a rien à dire, l'écriture suit sans autre clic.
  const check = async (ids = kept.map((title) => title.id)) => {
    setBusy(true);
    setFailure("");
    let outcome: EditOutcome;
    try {
      outcome = await tagTitles(ids, adds, removes, true);
    } catch (caught) {
      setFailure(messageOf(caught, "L'essai n'a pas abouti. Réessaie."));
      setBusy(false);
      return;
    }
    if (needsConfirmation(outcome)) {
      setTried(outcome);
      setBusy(false);
      return;
    }
    await write(ids);
  };

  const dropRefused = () => {
    if (!tried) return;
    const ids = tried.refused.map((issue) => issue.id);
    setDropped((before) => [...before, ...ids]);
    void check(kept.map((title) => title.id).filter((id) => !ids.includes(id)));
  };

  const changing = tried ? tried.written + tried.waiting.length : 0;
  let primary: { label: string; disabled: boolean; run: () => void };
  if (!tried) primary = { label: "Appliquer", disabled: none || tooMany, run: () => void check() };
  else if (tried.refused.length)
    primary = {
      label: `Continuer sans ${tried.refused.length === 1 ? "ce titre" : "ces titres"}`,
      disabled: tried.refused.length >= kept.length,
      run: dropRefused,
    };
  else
    primary = {
      label: changing === 1 ? "Appliquer à 1 titre" : `Appliquer à ${changing} titres`,
      disabled: changing === 0,
      run: () => void write(),
    };

  const field = `${base}-tag`;
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="34rem" className="banque-tags-dialog">
        <Dialog.Title>Étiquettes de {what}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="3">
          Une étiquette ne s'écrit que dans BUTTON, jamais dans le fichier. Chaque titre garde ses autres étiquettes.
        </Dialog.Description>
        {tooMany ? (
          <p className="bacs-dialog-error" role="alert">
            Un lot prend {MAX_LOT} titres au plus : sélectionnes-en {kept.length - MAX_LOT} de moins.
          </p>
        ) : null}
        {dropped.length ? (
          <p className="bacs-dialog-note">
            {dropped.length === 1 ? "Un titre a été retiré du lot." : `${dropped.length} titres ont été retirés du lot.`}{" "}
            {titlesLabel(kept.length)} {kept.length === 1 ? "reste" : "restent"}.
          </p>
        ) : null}

        <section className="banque-tags-part" aria-labelledby={`${base}-add`}>
          <h3 id={`${base}-add`} className="banque-tags-heading">
            Poser
          </h3>
          <form
            className="banque-tags-add"
            onSubmit={(event) => {
              event.preventDefault();
              add(typed);
            }}
          >
            <TextField.Root
              id={field}
              size="2"
              className="ui-field-control"
              value={typed}
              disabled={busy}
              autoFocus
              autoComplete="off"
              maxLength={80}
              aria-label="Nouvelle étiquette"
              aria-invalid={typedProblem ? true : undefined}
              aria-describedby={typedProblem ? `${field}-error` : undefined}
              placeholder="nuit, instrumental…"
              onChange={(event) => {
                setTyped(event.target.value);
                setTypedProblem("");
              }}
            />
            <Button type="submit" size="2" variant="soft" color="gray" disabled={busy || !typed.trim()}>
              <Plus className="ui-button-icon" />
              Ajouter
            </Button>
          </form>
          {typedProblem ? (
            <span id={`${field}-error`} className="ui-field-error">
              {typedProblem}
            </span>
          ) : null}
          {adds.length ? (
            <ul className="banque-tags-chosen" aria-label="Étiquettes à poser">
              {adds.map((tag) => (
                <li key={tag} className="banque-tag is-chosen">
                  <span>{tag}</span>
                  <IconButton
                    size="1"
                    variant="ghost"
                    color="gray"
                    disabled={busy}
                    aria-label={`Ne pas poser ${tag}`}
                    onClick={() => change(() => setAdds((before) => before.filter((item) => item !== tag)))}
                  >
                    <X size={13} />
                  </IconButton>
                </li>
              ))}
            </ul>
          ) : null}
          {station == null ? (
            <p className="banque-tags-hint">
              <Spinner size="1" /> Lecture des étiquettes de la station…
            </p>
          ) : stationProblem ? (
            <p className="banque-tags-hint">{stationProblem}</p>
          ) : suggestions.length ? (
            <div className="banque-tags-suggest">
              <p className="banque-tags-hint">Celles de la station, avec leur nombre de titres :</p>
              <ul aria-label="Étiquettes de la station">
                {suggestions.map((facet) => (
                  <li key={facet.value}>
                    <button type="button" className="banque-tag" disabled={busy} onClick={() => add(facet.value)}>
                      {facet.value} <small>{facet.count}</small>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="banque-tags-hint">
              {(station ?? []).some((facet) => facet.value)
                ? "Aucune étiquette de la station ne tient ce qui est tapé : « Ajouter » la crée."
                : "La station n'a pas encore d'étiquette : la première naît avec ce geste."}
            </p>
          )}
        </section>

        {worn.length ? (
          <section className="banque-tags-part" aria-labelledby={`${base}-remove`}>
            <h3 id={`${base}-remove`} className="banque-tags-heading">
              Retirer
            </h3>
            <ul className="banque-tags-worn">
              {worn.map((facet) => (
                <li key={facet.value}>
                  <label className="banque-edit-check">
                    <Checkbox
                      size="2"
                      checked={removes.includes(facet.value)}
                      disabled={busy || adds.includes(facet.value)}
                      onCheckedChange={(state) =>
                        change(() =>
                          setRemoves((before) =>
                            state === true ? [...before, facet.value] : before.filter((tag) => tag !== facet.value),
                          ),
                        )
                      }
                    />
                    <span>
                      {facet.value}
                      {titles.length > 1 ? (
                        <small>
                          {" "}
                          · {facet.count} sur {titles.length}
                        </small>
                      ) : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tried ? <TryReport outcome={tried} /> : null}
        {failure ? (
          <p className="bacs-dialog-error" role="alert">
            {failure}
          </p>
        ) : null}
        <div className="bacs-dialog-actions">
          {busy ? <Spinner size="2" /> : null}
          <Dialog.Close>
            <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button size="2" highContrast disabled={busy || primary.disabled} onClick={primary.run}>
            {primary.label}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
