import { Button, Code, Spinner } from "@radix-ui/themes";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { ApiRequestError, apiGet } from "../../api/client";
import { FICHES_FAMILIES_JSON, count, fichesErrorText, type FamiliesPayload } from "../../api/fiches";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; data: FamiliesPayload }
  | { status: "outdated" }
  | { status: "failed"; message: string };

/**
 * Programmation → Sélections de titres : où tombent les familles (FON-28). Pour
 * chaque famille acceptée, les sélections qui prennent ses titres, et ceux
 * qu'aucune ne prend. En lecture : la correspondance se lit, elle ne s'impose pas.
 * `version` relit le tableau après qu'une sélection a changé.
 */
export function FamiliesPanel({ version }: { version: number }) {
  // Replié d'abord : il joue toutes les sélections sur la bibliothèque, et la liste
  // des sélections garde la place.
  const [shown, setShown] = useState(false);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    if (!shown) return;
    let cancelled = false;
    setLoaded({ status: "loading" });
    apiGet<FamiliesPayload>(FICHES_FAMILIES_JSON).then(
      (data) => {
        if (cancelled) return;
        setLoaded({ status: "ready", data });
      },
      (caught: unknown) => {
        if (cancelled) return;
        setLoaded(
          caught instanceof ApiRequestError && caught.status === 404
            ? { status: "outdated" }
            : {
                status: "failed",
                message: fichesErrorText(caught, "Le tableau ne s'est pas lu."),
              },
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [shown, version, attempt]);

  const head = (
    <header className="prog-fam-head">
      <div className="prog-fam-copy">
        <h3 id="prog-fam-title">Familles et sélections</h3>
        <p>
          Pour chaque famille acceptée dans les fiches, les sélections qui prennent ses titres, et ceux qu'aucune ne
          prend. Une sélection lit la famille par sa requête : <Code size="1">famille:jazz</Code>.
        </p>
      </div>
      <Button size="2" variant="soft" color="gray" aria-expanded={shown} onClick={() => setShown((value) => !value)}>
        {shown ? <ChevronDown className="ui-button-icon" /> : <ChevronRight className="ui-button-icon" />}
        {shown ? "Replier les familles" : "Voir les familles"}
      </Button>
    </header>
  );

  if (!shown) {
    return (
      <section className="prog-fam" aria-labelledby="prog-fam-title">
        {head}
      </section>
    );
  }

  if (loaded.status === "outdated") {
    return (
      <section className="prog-fam" aria-labelledby="prog-fam-title">
        {head}
        <p className="prog-faint" role="status">
          Mets à jour le moteur pour voir les familles ici.
        </p>
      </section>
    );
  }
  if (loaded.status === "loading") {
    return (
      <section className="prog-fam" aria-labelledby="prog-fam-title" aria-busy="true">
        {head}
        <p className="prog-faint" role="status">
          <Spinner size="1" /> Lecture des familles…
        </p>
      </section>
    );
  }
  if (loaded.status === "failed") {
    return (
      <section className="prog-fam" aria-labelledby="prog-fam-title">
        {head}
        <div className="prog-fam-error" role="alert">
          <span>Le tableau des familles ne s'est pas lu : {loaded.message}</span>
          <Button size="1" variant="soft" color="gray" onClick={() => setAttempt((value) => value + 1)}>
            Réessayer
          </Button>
        </div>
      </section>
    );
  }

  const { families } = loaded.data;
  return (
    <section className="prog-fam" aria-labelledby="prog-fam-title">
      {head}
      {families.length === 0 ? (
        <p className="prog-faint">La bibliothèque n'a encore aucun titre.</p>
      ) : (
        <div className="prog-fam-frame">
          <table className="prog-sel-table prog-fam-table">
            <thead>
              <tr>
                <th scope="col">Famille</th>
                <th scope="col" className="c-count">
                  Titres
                </th>
                <th scope="col">Sélections qui les prennent</th>
                <th scope="col" className="c-count">
                  Sans sélection
                </th>
              </tr>
            </thead>
            <tbody>
              {families.map((family) => {
                const label = family.label || "Sans famille";
                const shown = open === family.value;
                return (
                  <Fragment key={family.value || "none"}>
                    <tr>
                      <th scope="row">{label}</th>
                      <td className="c-count">
                        <span className="prog-fam-label">{"Titres\u202f: "}</span>
                        {count(family.count)}
                      </td>
                      <td>
                        <span className="prog-fam-label">{"Sélections\u202f: "}</span>
                        {family.selections.length ? (
                          <span className="prog-sel-uses">
                            {family.selections.map((one) => (
                              <span key={one.id} className="prog-chip">
                                {one.name} · {count(one.count)}
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span className="prog-faint">Aucune</span>
                        )}
                      </td>
                      <td className="c-count">
                        <span className="prog-fam-label">{"Sans sélection\u202f: "}</span>
                        {family.uncategorized ? (
                          <button
                            type="button"
                            className="prog-fam-toggle"
                            aria-expanded={shown}
                            onClick={() => setOpen(shown ? null : family.value)}
                          >
                            {shown ? (
                              <ChevronDown size={14} aria-hidden="true" />
                            ) : (
                              <ChevronRight size={14} aria-hidden="true" />
                            )}
                            {count(family.uncategorized)}
                            <span className="ui-visually-hidden"> titres de {label} sans sélection</span>
                          </button>
                        ) : (
                          <span className="prog-faint">0</span>
                        )}
                      </td>
                    </tr>
                    {shown ? (
                      <tr className="prog-fam-sample">
                        <td colSpan={4}>
                          <ul>
                            {family.sample.map((title) => (
                              <li key={title.id}>{[title.artist, title.title].filter(Boolean).join(" – ")}</li>
                            ))}
                          </ul>
                          {family.uncategorized > family.sample.length ? (
                            <p className="prog-faint">
                              Et {count(family.uncategorized - family.sample.length)} autres. Le tableau de la banque,
                              rangé par famille, les montre tous.
                            </p>
                          ) : null}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
