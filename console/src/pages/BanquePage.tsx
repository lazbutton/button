import { Button, SegmentedControl } from "@radix-ui/themes";
import { ArrowLeft } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useAccount } from "../api/AccountContext";
import { tasksCount } from "../api/bankTasks";
import { BankTable } from "../components/banque/BankTable";
import { BankTasksView, useBankTasks } from "../components/banque/BankTasks";
import { StationFolder } from "../components/banque/StationFolder";
import { ReviewView } from "../components/fiches/ReviewView";
import { ImporterPage, presetDestination } from "./ImporterPage";

type Vue = "contenu" | "ajouter" | "a-ranger" | "relire";

/**
 * Sons → Banque : ce qu'elle contient, l'envoi de fichiers, et ce qui reste à
 * ranger (FON-92), une fois le rangement de la banque ouvert. « À ranger »
 * remplace les vues Arrivées et Santé, et ouvre la relecture des fiches
 * trouvées en ligne (FON-26). La vue ouverte reste dans l'adresse
 * (`?vue=ajouter`), comme l'onglet.
 */
export function BanquePage() {
  const [params, setParams] = useSearchParams();
  const { account, isAdmin } = useAccount();
  // Ce qui reste à ranger, et la relecture, pour le Programmateur, une fois le rangement de la banque ouvert.
  const tidy = account?.features?.bank_tidy === true && (isAdmin || account.permissions.autodj === true);
  const tasks = useBankTasks(tidy, account?.features?.bank_health === true);
  const count = tasksCount(tasks.tasks);
  const asked = params.get("vue");
  const vue: Vue =
    asked === "ajouter"
      ? "ajouter"
      : asked === "relire" && tidy
        ? "relire"
        : // Arrivées et Santé, d'avant FON-92 : leurs adresses ouvrent « À ranger ».
          (asked === "a-ranger" || asked === "arrivees" || asked === "sante") && tidy
          ? "a-ranger"
          : "contenu";

  const open = (next: Vue) => {
    const updated = new URLSearchParams(params);
    if (next === "contenu") updated.delete("vue");
    else updated.set("vue", next);
    setParams(updated, { replace: true });
  };

  // From « À ranger », the table ranged, sorted or searched as a task says.
  const openTable = (table: Record<string, string>) => {
    const updated = new URLSearchParams(params);
    for (const key of ["vue", "ranger", "groupe", "collection", "tri", "ordre", "q"]) updated.delete(key);
    for (const [key, value] of Object.entries(table)) updated.set(key, value);
    setParams(updated);
  };

  return (
    <div className="banque-page">
      <div className="banque-views">
        <SegmentedControl.Root
          size="2"
          // La relecture s'ouvre depuis « À ranger », qui reste l'onglet choisi.
          value={vue === "relire" ? "a-ranger" : vue}
          aria-label="Vue de la banque"
          onValueChange={(value) => open(value as Vue)}
        >
          <SegmentedControl.Item value="contenu">Contenu</SegmentedControl.Item>
          <SegmentedControl.Item value="ajouter">Ajouter</SegmentedControl.Item>
          {tidy ? (
            <SegmentedControl.Item value="a-ranger">
              À ranger
              {count ? <span className="banque-views-count"> {count}</span> : null}
            </SegmentedControl.Item>
          ) : null}
        </SegmentedControl.Root>
        {/* The upload view has it in its own header. */}
        {vue === "contenu" ? (
          <div className="banque-views-tools">
            <StationFolder />
          </div>
        ) : null}
      </div>
      {vue === "ajouter" ? (
        <ImporterPage />
      ) : vue === "a-ranger" ? (
        <BankTasksView data={tasks} onOpenTable={openTable} onReview={() => open("relire")} />
      ) : vue === "relire" ? (
        <>
          <Button size="2" variant="ghost" color="gray" className="banque-back" onClick={() => open("a-ranger")}>
            <ArrowLeft className="ui-button-icon" />
            Retour à « À ranger »
          </Button>
          <ReviewView />
        </>
      ) : (
        <BankTable
          onAdd={(id) => {
            presetDestination(id);
            open("ajouter");
          }}
        />
      )}
    </div>
  );
}
