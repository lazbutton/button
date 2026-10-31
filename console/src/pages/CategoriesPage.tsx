import { Button, Code, Dialog, DropdownMenu, IconButton, Kbd, Spinner, TextField } from "@radix-ui/themes";
import { FlaskConical, ListMusic, MoreHorizontal, Pencil, Plus, Search, SearchX, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { apiDelete, apiGet, apiPostJson, apiPut } from "../api/client";
import { errorText } from "../api/programmationErrors";
import { nameTaken } from "../api/programmationView";
import { SessionGate } from "../api/SessionGate";
import type { CategoriesResponse, Category, ClocksResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { FormField } from "../ui/FormField";
import "../styles/pages/programmation.css";

type TestResult = { count: number; sample: { artist: string; title: string }[] };

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function CategoriesPage() {
  const { data, error, loading, reload } = useApiJson<CategoriesResponse>("/autodj/categories.json");
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json");
  const { message, show, dismiss } = useProtoToast();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [deleting, setDeleting] = useState<Category | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const categories = useMemo(
    () => [...(data?.categories ?? [])].sort((a, b) => a.name.localeCompare(b.name, "fr")),
    [data],
  );
  const usage = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const clock of clocksRes.data?.clocks ?? []) {
      for (const step of [...clock.motif, ...clock.anchors]) {
        if (step.kind !== "musique" || !step.category) continue;
        const names = map.get(step.category) ?? [];
        if (!names.includes(clock.name)) names.push(clock.name);
        map.set(step.category, names);
      }
    }
    return map;
  }, [clocksRes.data]);
  const clockIds = useMemo(
    () => new Map((clocksRes.data?.clocks ?? []).map((clock) => [clock.name, clock.id])),
    [clocksRes.data],
  );
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("fr");
    if (!needle) return categories;
    return categories.filter((row) =>
      [row.name, row.query, row.empty_query].some((value) => value.toLocaleLowerCase("fr").includes(needle)),
    );
  }, [categories, query]);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || isTyping(event.target)) return;
      if (!searchRef.current || searchRef.current.offsetParent === null) return;
      event.preventDefault();
      searchRef.current.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const remove = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await apiDelete(`/autodj/categories/${deleting.id}.json`);
      await reload();
      show(`« ${deleting.name} » supprimée`, "success");
      setDeleting(null);
    } catch (caught) {
      show(errorText(caught, "Suppression impossible."), "error");
      setDeleting(null);
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div className="prog-page">
      <SessionGate loading={loading} error={error} ready={data != null} onRetry={() => void reload()}>
        <div className="prog-sel">
          <header className="prog-sel-bar">
            <div className="prog-sel-copy">
              <h2>
                Sélections de titres <span className="prog-count">{categories.length}</span>
              </h2>
              <p>
                Une requête sur la banque choisit les titres d'une étape « Titres ». Le repli sert si elle ne trouve
                rien.
              </p>
            </div>
            <div className="prog-sel-tools">
              <TextField.Root
                ref={searchRef}
                size="2"
                className="prog-sel-search"
                placeholder="Rechercher"
                value={query}
                aria-label="Rechercher une sélection"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") setQuery("");
                }}
              >
                <TextField.Slot>
                  <Search size={15} aria-hidden="true" />
                </TextField.Slot>
                <TextField.Slot side="right">
                  <Kbd size="1">/</Kbd>
                </TextField.Slot>
              </TextField.Root>
              <Button size="2" highContrast onClick={() => setEditing("new")}>
                <Plus className="ui-button-icon" />
                Nouvelle sélection
              </Button>
            </div>
          </header>

          <div className="prog-sel-frame">
            {visible.length ? (
              <table className="prog-sel-table">
                <thead>
                  <tr>
                    <th className="c-name">Nom</th>
                    <th className="c-query">Requête</th>
                    <th className="c-count">Titres</th>
                    <th className="c-uses">Utilisée par</th>
                    <th className="c-more">
                      <span className="ui-visually-hidden">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => {
                    const uses = usage.get(row.name) ?? [];
                    return (
                      <tr key={row.id}>
                        <th className="c-name" scope="row">
                          <button type="button" className="prog-sel-name" onClick={() => setEditing(row)}>
                            <span className="prog-sel-icon" aria-hidden="true">
                              <ListMusic size={14} />
                            </span>
                            {row.name}
                          </button>
                        </th>
                        <td className="c-query">
                          <Code size="1" variant="ghost" className="prog-code">
                            {row.query}
                          </Code>
                          {row.empty_query ? (
                            <span className="prog-sel-fallback">
                              sinon{" "}
                              <Code size="1" variant="ghost" className="prog-code">
                                {row.empty_query}
                              </Code>
                            </span>
                          ) : null}
                        </td>
                        <td className="c-count">
                          <span className={`prog-sel-count${row.count ? "" : " is-empty"}`}>{row.count}</span>
                        </td>
                        <td className="c-uses">
                          {uses.length ? (
                            <span className="prog-sel-uses">
                              {uses.map((name) => (
                                <Link
                                  key={name}
                                  to={`/programmation?clock=${clockIds.get(name) ?? ""}`}
                                  className="prog-chip"
                                >
                                  {name}
                                </Link>
                              ))}
                            </span>
                          ) : (
                            <span className="prog-faint">Aucune heure type</span>
                          )}
                        </td>
                        <td className="c-more">
                          <DropdownMenu.Root modal={false}>
                            <DropdownMenu.Trigger>
                              <IconButton size="2" variant="ghost" color="gray" aria-label={`Actions pour ${row.name}`}>
                                <MoreHorizontal size={16} />
                              </IconButton>
                            </DropdownMenu.Trigger>
                            <DropdownMenu.Content variant="soft" align="end" className="prog-menu">
                              <DropdownMenu.Item onSelect={() => setEditing(row)}>
                                <Pencil size={15} aria-hidden="true" />
                                Modifier et tester
                              </DropdownMenu.Item>
                              <DropdownMenu.Separator />
                              <DropdownMenu.Item
                                color="red"
                                disabled={uses.length > 0}
                                onSelect={() => setDeleting(row)}
                              >
                                <Trash2 size={15} aria-hidden="true" />
                                <span className="prog-menu-copy">
                                  Supprimer…
                                  {uses.length ? (
                                    <small>Une heure type l'utilise : change d'abord ses étapes</small>
                                  ) : null}
                                </span>
                              </DropdownMenu.Item>
                            </DropdownMenu.Content>
                          </DropdownMenu.Root>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <div className="prog-sel-empty">
                {categories.length ? (
                  <SearchX size={20} aria-hidden="true" />
                ) : (
                  <ListMusic size={20} aria-hidden="true" />
                )}
                <p>
                  {categories.length
                    ? `Aucune sélection ne correspond à « ${query.trim()} ».`
                    : "Aucune sélection : crée-en une pour qu'une étape « Titres » puise dans la banque."}
                </p>
                {categories.length ? (
                  <Button size="1" variant="soft" color="gray" onClick={() => setQuery("")}>
                    Effacer la recherche
                  </Button>
                ) : (
                  <Button size="2" highContrast onClick={() => setEditing("new")}>
                    <Plus className="ui-button-icon" />
                    Créer une sélection
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      </SessionGate>

      <SelectionDialog
        target={editing}
        names={categories.map((row) => row.name)}
        onClose={() => setEditing(null)}
        onSaved={async (text) => {
          await reload();
          void clocksRes.reload();
          show(text, "success");
        }}
      />
      <ConfirmDialog
        open={deleting != null}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) setDeleting(null);
        }}
        title={`Supprimer « ${deleting?.name ?? ""} » ?`}
        description="La sélection disparaît. Aucune heure type ne l'utilise."
        confirmLabel="Supprimer la sélection"
        busy={deleteBusy}
        onConfirm={remove}
      />
      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}

/** Create or edit a sélection, and see what its query finds before saving. */
function SelectionDialog({
  target,
  names,
  onClose,
  onSaved,
}: {
  target: Category | "new" | null;
  names: string[];
  onClose: () => void;
  onSaved: (message: string) => Promise<void>;
}) {
  const initial = target && target !== "new" ? target : null;
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [fallback, setFallback] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [test, setTest] = useState<{ query: string; result: TestResult | null; error: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!target) return;
    setName(initial?.name ?? "");
    setQuery(initial?.query ?? "");
    setFallback(initial?.empty_query ?? "");
    setFailure("");
    setBusy(false);
    setTest(null);
  }, [target]); // a new target resets the form; the list refreshing does not

  const others = names.filter((row) => row !== initial?.name);
  const clash = nameTaken(name, others);
  const ready = Boolean(name.trim()) && Boolean(query.trim()) && !clash;

  const runTest = async (text: string) => {
    const wanted = text.trim();
    if (!wanted) return;
    setTesting(true);
    try {
      const result = await apiGet<TestResult>(`/autodj/testquery.json?query=${encodeURIComponent(wanted)}`);
      setTest({ query: wanted, result, error: "" });
    } catch (caught) {
      setTest({ query: wanted, result: null, error: errorText(caught, "Test impossible.") });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setFailure("");
    const body = { name: name.trim(), query: query.trim(), empty_query: fallback.trim() };
    try {
      if (initial) await apiPut(`/autodj/categories/${initial.id}.json`, body);
      else await apiPostJson("/autodj/categories.json", body);
      await onSaved(initial ? `« ${body.name} » enregistrée` : `« ${body.name} » créée`);
      onClose();
    } catch (caught) {
      setFailure(errorText(caught, "Enregistrement impossible."));
    } finally {
      setBusy(false);
    }
  };

  const stale = test != null && test.query !== query.trim();

  return (
    <Dialog.Root
      open={target != null}
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="34rem">
        <Dialog.Title>{initial ? "Modifier la sélection" : "Nouvelle sélection de titres"}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          La requête interroge la banque indexée par Beets. Teste-la avant d'enregistrer.
        </Dialog.Description>
        <form
          className="prog-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <FormField label="Nom" error={clash ? "Une sélection porte déjà ce nom." : undefined}>
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={name}
              placeholder="Rotation"
              autoFocus
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>
          <div className="ui-field">
            <label className="ui-field-label" htmlFor="selection-query">
              Requête
            </label>
            <div className="prog-query-row">
              <TextField.Root
                id="selection-query"
                size="2"
                className="ui-field-control prog-code-input"
                value={query}
                spellCheck={false}
                onChange={(event) => setQuery(event.target.value)}
              />
              <Button
                type="button"
                size="2"
                variant="soft"
                color="gray"
                disabled={!query.trim() || testing}
                onClick={() => void runTest(query)}
              >
                {testing ? <Spinner size="1" /> : <FlaskConical className="ui-button-icon" />}
                Tester
              </Button>
            </div>
            <span className="ui-field-hint">Exemples : path:/media/10-rotation · grouping:ntf1 · genre:Jazz</span>
          </div>
          {test ? (
            <div className={`prog-test${stale ? " is-stale" : ""}`} role="status" aria-live="polite">
              {test.error ? (
                <p className="prog-warn">{test.error}</p>
              ) : test.result ? (
                <>
                  <p>
                    <strong>
                      {test.result.count} titre{test.result.count === 1 ? "" : "s"}
                    </strong>{" "}
                    {stale
                      ? "pour la requête d'avant : reteste."
                      : test.result.count
                        ? "trouvés, par exemple :"
                        : "trouvé : le repli servira."}
                  </p>
                  {test.result.sample.length && !stale ? (
                    <ul>
                      {test.result.sample.slice(0, 6).map((item, index) => (
                        <li key={`${item.artist}-${item.title}-${index}`}>
                          <span>{item.title || "Sans titre"}</span>
                          {item.artist ? <small>{item.artist}</small> : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}
          <FormField label="Si elle ne trouve rien" hint="Facultatif : une autre requête, essayée à la place.">
            <TextField.Root
              size="2"
              className="ui-field-control prog-code-input"
              value={fallback}
              spellCheck={false}
              onChange={(event) => setFallback(event.target.value)}
            />
          </FormField>
          {failure ? (
            <p className="prog-dialog-error" role="alert">
              {failure}
            </p>
          ) : null}
          <div className="prog-dialog-actions">
            <Dialog.Close>
              <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" size="2" highContrast disabled={!ready || busy}>
              {busy ? "Enregistrement…" : initial ? "Enregistrer" : "Créer la sélection"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
