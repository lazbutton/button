import { Button, Spinner } from "@radix-ui/themes";
import { Radio, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { playLine, playsHeadline, playsOrigins, type TitlePlays } from "../../api/bankPlays";
import { ApiRequestError, apiGet } from "../../api/client";

/**
 * The plays of a title, in its fiche (FON-76): how many in 90 days, from where,
 * and the last ones, read in the air log. An older engine has no such route:
 * the section hides.
 */
export function TitlePlaysSection({ titleId }: { titleId: number }) {
  const [plays, setPlays] = useState<TitlePlays | null>(null);
  const [problem, setProblem] = useState("");
  const [hidden, setHidden] = useState(false);

  const load = useCallback(async () => {
    setProblem("");
    try {
      setPlays(await apiGet<TitlePlays>(`/media/titles/${titleId}/plays.json`));
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 404) setHidden(true);
      else setProblem(caught instanceof Error && caught.message ? caught.message : "Les passages ne se sont pas lus.");
    }
  }, [titleId]);

  useEffect(() => {
    setPlays(null);
    setHidden(false);
    void load();
  }, [load]);

  if (hidden) return null;
  const origins = plays ? playsOrigins(plays) : "";
  return (
    <section className="banque-sheet-plays" aria-label="À l'antenne">
      <h3>
        <Radio size={13} aria-hidden="true" />
        À l'antenne
      </h3>
      {problem ? (
        <div className="banque-sheet-problem" role="alert">
          <span>{problem}</span>
          <Button size="1" variant="soft" color="gray" onClick={() => void load()}>
            <RefreshCw className="ui-button-icon" />
            Réessayer
          </Button>
        </div>
      ) : !plays ? (
        <p className="banque-sheet-muted">
          <Spinner size="1" /> Lecture du journal d'antenne…
        </p>
      ) : (
        <>
          <p className="banque-sheet-headline">
            <strong>{playsHeadline(plays)}</strong>
            {origins ? <span>{origins}</span> : null}
          </p>
          {plays.recent.length ? (
            <ol className="banque-sheet-recent" aria-label="Derniers passages">
              {plays.recent.map((play, index) => {
                const line = playLine(play);
                return (
                  <li key={`${play.on_air}-${index}`}>
                    <span>{line.when}</span>
                    <span>{line.from}</span>
                  </li>
                );
              })}
            </ol>
          ) : null}
        </>
      )}
    </section>
  );
}
