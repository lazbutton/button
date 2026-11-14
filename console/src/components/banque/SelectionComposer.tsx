import { Code, Select, Spinner, TextField } from "@radix-ui/themes";
import { useEffect, useId, useRef, useState } from "react";
import { bankShelves, type BankShelf } from "../../api/bankContent";
import type { BankFacet, BankTitlesPage } from "../../api/bankTitles";
import { ApiRequestError, apiGet } from "../../api/client";
import {
  filtersProblem,
  filtersQuery,
  hasFilter,
  type ComposedSelection,
  type SelectionFilters,
} from "../../api/selectionFilters";
import { FormField } from "../../ui/FormField";

type Facets = { famille: BankFacet[]; collection: BankFacet[]; artist: BankFacet[]; album: BankFacet[]; genre: BankFacet[] };

const ANY = "__toutes__";

/**
 * « Nouvelle sélection », par filtres (FON-73) : une famille, une collection, un
 * artiste, un album, un genre, des années. À chaque choix, le moteur écrit la
 * requête Beets qui dit la même chose, la vérifie, la compte et en montre dix
 * titres. `onComposed` reçoit la requête, ou rien tant qu'elle ne tient pas.
 */
export function SelectionComposer({
  filters,
  onChange,
  onComposed,
}: {
  filters: SelectionFilters;
  onChange: (filters: SelectionFilters) => void;
  onComposed: (query: string) => void;
}) {
  const [facets, setFacets] = useState<Facets | null>(null);
  const [shelves, setShelves] = useState<BankShelf[]>([]);
  const [composed, setComposed] = useState<ComposedSelection | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const ticket = useRef(0);
  const artists = useId();
  const albums = useId();
  const genres = useId();
  const local = filtersProblem(filters);
  const onComposedRef = useRef(onComposed);
  onComposedRef.current = onComposed;

  useEffect(() => {
    void apiGet<BankTitlesPage>("/media/titles.json?limit=1&facets=famille,collection,artist,album,genre").then(
      (page) =>
        setFacets({
          famille: page.facets.famille ?? [],
          collection: page.facets.collection ?? [],
          artist: page.facets.artist ?? [],
          album: page.facets.album ?? [],
          genre: (page.facets as Record<string, BankFacet[] | undefined>).genre ?? [],
        }),
      (caught) => setProblem(caught instanceof Error ? caught.message : "La banque ne s'est pas lue."),
    );
    void bankShelves().then(setShelves, () => setShelves([]));
  }, []);

  // Each choice asks the engine again, once the typing stops.
  useEffect(() => {
    const mine = ++ticket.current;
    if (!hasFilter(filters) || local) {
      setComposed(null);
      onComposedRef.current("");
      return;
    }
    setBusy(true);
    const timer = window.setTimeout(() => {
      void apiGet<ComposedSelection>(`/media/selection.json?${filtersQuery(filters)}`).then(
        (next) => {
          if (mine !== ticket.current) return;
          setComposed(next);
          setProblem("");
          setBusy(false);
          onComposedRef.current(next.query);
        },
        (caught) => {
          if (mine !== ticket.current) return;
          setComposed(null);
          setBusy(false);
          onComposedRef.current("");
          setProblem(
            caught instanceof ApiRequestError || caught instanceof Error ? caught.message : "Le moteur n'a pas compté.",
          );
        },
      );
    }, 250);
    return () => window.clearTimeout(timer);
  }, [filters, local]);

  const set = (key: keyof SelectionFilters, value: string) => onChange({ ...filters, [key]: value });
  const label = (facet: BankFacet) => facet.label || facet.value;
  const collectionLabel = (value: string) => shelves.find((shelf) => shelf.id === value)?.label ?? value;

  return (
    <div className="banque-composer">
      <div className="banque-composer-grid">
        <FormField label="Famille">
          <Select.Root value={filters.famille || ANY} onValueChange={(value) => set("famille", value === ANY ? "" : value)}>
            <Select.Trigger variant="surface" className="ui-field-control" aria-label="Famille" />
            <Select.Content position="popper">
              <Select.Item value={ANY}>Toutes</Select.Item>
              {(facets?.famille ?? []).filter((facet) => facet.value).map((facet) => (
                <Select.Item key={facet.value} value={facet.value}>
                  {label(facet)} · {facet.count}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </FormField>
        <FormField label="Collection">
          <Select.Root
            value={filters.collection || ANY}
            onValueChange={(value) => set("collection", value === ANY ? "" : value)}
          >
            <Select.Trigger variant="surface" className="ui-field-control" aria-label="Collection" />
            <Select.Content position="popper">
              <Select.Item value={ANY}>Toute la banque</Select.Item>
              {(facets?.collection ?? []).filter((facet) => facet.value).map((facet) => (
                <Select.Item key={facet.value} value={facet.value}>
                  {collectionLabel(facet.value)} · {facet.count}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </FormField>
        <FormField label="Artiste" hint="Cet artiste seul, pas un nom qui le contient.">
          <TextField.Root
            size="2"
            className="ui-field-control"
            value={filters.artist}
            list={artists}
            autoComplete="off"
            onChange={(event) => set("artist", event.target.value)}
          />
        </FormField>
        <FormField label="Album">
          <TextField.Root
            size="2"
            className="ui-field-control"
            value={filters.album}
            list={albums}
            autoComplete="off"
            onChange={(event) => set("album", event.target.value)}
          />
        </FormField>
        <FormField label="Genre du fichier">
          <TextField.Root
            size="2"
            className="ui-field-control"
            value={filters.genre}
            list={genres}
            autoComplete="off"
            onChange={(event) => set("genre", event.target.value)}
          />
        </FormField>
        <div className="banque-composer-years">
          <FormField label="Depuis" error={yearProblemOf(filters.year_from)}>
            <TextField.Root
              size="2"
              className="ui-field-control"
              inputMode="numeric"
              placeholder="2015"
              value={filters.year_from}
              onChange={(event) => set("year_from", event.target.value)}
            />
          </FormField>
          <FormField label="Jusqu'à" error={yearProblemOf(filters.year_to) || (local && !yearProblemOf(filters.year_from) ? local : undefined)}>
            <TextField.Root
              size="2"
              className="ui-field-control"
              inputMode="numeric"
              placeholder="2024"
              value={filters.year_to}
              onChange={(event) => set("year_to", event.target.value)}
            />
          </FormField>
        </div>
      </div>
      <datalist id={artists}>
        {(facets?.artist ?? []).filter((facet) => facet.value).map((facet) => (
          <option key={facet.value} value={facet.value} />
        ))}
      </datalist>
      <datalist id={albums}>
        {(facets?.album ?? []).filter((facet) => facet.value).map((facet) => (
          <option key={facet.value} value={facet.value} />
        ))}
      </datalist>
      <datalist id={genres}>
        {(facets?.genre ?? []).filter((facet) => facet.value).map((facet) => (
          <option key={facet.value} value={facet.value} />
        ))}
      </datalist>

      <div className="prog-test banque-composer-result" role="status" aria-live="polite">
        {!hasFilter(filters) ? (
          <p>Choisis un filtre : la sélection compte ses titres à chaque choix.</p>
        ) : problem ? (
          <p className="prog-warn">{problem}</p>
        ) : busy && !composed ? (
          <p>
            <Spinner size="1" /> Compte en cours…
          </p>
        ) : composed ? (
          <>
            <p>
              <strong>
                {composed.count} titre{composed.count === 1 ? "" : "s"}
              </strong>{" "}
              {composed.count ? "pris, par exemple :" : "pris : le repli servira."}
              {busy ? <Spinner size="1" /> : null}
            </p>
            {composed.sample.length ? (
              <ul>
                {composed.sample.slice(0, 6).map((item, index) => (
                  <li key={`${item.artist}-${item.title}-${index}`}>
                    <span>{item.title || "Sans titre"}</span>
                    {item.artist ? <small>{item.artist}</small> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="banque-composer-query">
              Requête Beets : <Code size="1">{composed.query}</Code>
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}

function yearProblemOf(value: string): string | undefined {
  const text = value.trim();
  if (!text) return undefined;
  return /^\d{4}$/.test(text) ? undefined : "Quatre chiffres.";
}
