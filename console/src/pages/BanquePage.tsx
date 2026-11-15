import { SegmentedControl } from "@radix-ui/themes";
import { useSearchParams } from "react-router-dom";
import { useAccount } from "../api/AccountContext";
import { BankArrivalsView } from "../components/banque/BankArrivals";
import { BankHealthView } from "../components/banque/BankHealth";
import { BankContent } from "../components/banque/BankContent";
import { StationFolder } from "../components/banque/StationFolder";
import { ReviewView } from "../components/fiches/ReviewView";
import { ImporterPage, presetDestination } from "./ImporterPage";

type Vue = "contenu" | "ajouter" | "arrivees" | "relire" | "sante";

/**
 * Sons → Banque : ce qu'elle contient, l'envoi de fichiers, les arrivées
 * (FON-81), les fiches à relire (FON-26) ou sa santé (FON-72), une fois le
 * rangement de la banque ouvert. La vue ouverte reste dans l'adresse
 * (`?vue=ajouter`), comme l'onglet.
 */
export function BanquePage() {
  const [params, setParams] = useSearchParams();
  const { account, isAdmin } = useAccount();
  // FON-26 : les fiches à relire, pour le Programmateur, une fois le rangement de la banque ouvert.
  const review = account?.features?.bank_tidy === true && (isAdmin || account.permissions.autodj === true);
  const health = account?.features?.bank_health === true;
  // FON-81 : les arrivées, pour le Programmateur.
  const arrivals = account?.features?.bank_arrivals === true && (isAdmin || account.permissions.autodj === true);
  const asked = params.get("vue");
  const vue: Vue =
    asked === "ajouter"
      ? "ajouter"
      : asked === "arrivees" && arrivals
        ? "arrivees"
        : asked === "relire" && review
          ? "relire"
          : asked === "sante" && health
            ? "sante"
            : "contenu";

  const open = (next: Vue) => {
    const updated = new URLSearchParams(params);
    if (next === "contenu") updated.delete("vue");
    else updated.set("vue", next);
    setParams(updated, { replace: true });
  };

  // From the Santé view, the table ranged or searched as it says.
  const openTable = (table: Record<string, string>) => {
    const updated = new URLSearchParams(params);
    for (const key of ["vue", "ranger", "groupe", "collection", "q"]) updated.delete(key);
    for (const [key, value] of Object.entries(table)) updated.set(key, value);
    setParams(updated);
  };

  return (
    <div className="banque-page">
      <div className="banque-views">
        <SegmentedControl.Root
          size="2"
          value={vue}
          aria-label="Vue de la banque"
          onValueChange={(value) => open(value as Vue)}
        >
          <SegmentedControl.Item value="contenu">Contenu</SegmentedControl.Item>
          <SegmentedControl.Item value="ajouter">Ajouter</SegmentedControl.Item>
          {arrivals ? <SegmentedControl.Item value="arrivees">Arrivées</SegmentedControl.Item> : null}
          {review ? <SegmentedControl.Item value="relire">À relire</SegmentedControl.Item> : null}
          {health ? <SegmentedControl.Item value="sante">Santé</SegmentedControl.Item> : null}
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
      ) : vue === "arrivees" ? (
        <BankArrivalsView />
      ) : vue === "relire" ? (
        <ReviewView />
      ) : vue === "sante" ? (
        <BankHealthView onOpenTable={openTable} />
      ) : (
        <BankContent
          onAdd={(id) => {
            presetDestination(id);
            open("ajouter");
          }}
        />
      )}
    </div>
  );
}
