import { SegmentedControl } from "@radix-ui/themes";
import { useSearchParams } from "react-router-dom";
import { useAccount } from "../api/AccountContext";
import { BankContent } from "../components/banque/BankContent";
import { StationFolder } from "../components/banque/StationFolder";
import { ReviewView } from "../components/fiches/ReviewView";
import { ImporterPage, presetDestination } from "./ImporterPage";

type Vue = "contenu" | "ajouter" | "relire";

/**
 * Sons → Banque : ce qu'elle contient, l'envoi de fichiers, ou les fiches à
 * relire. La vue ouverte reste dans l'adresse (`?vue=ajouter`), comme l'onglet.
 */
export function BanquePage() {
  const [params, setParams] = useSearchParams();
  const { account, isAdmin } = useAccount();
  // FON-26 : les fiches à relire, pour le Programmateur, une fois le rangement de la banque ouvert.
  const review = account?.features?.bank_tidy === true && (isAdmin || account.permissions.autodj === true);
  const asked = params.get("vue");
  const vue: Vue = asked === "ajouter" ? "ajouter" : asked === "relire" && review ? "relire" : "contenu";

  const open = (next: Vue) => {
    const updated = new URLSearchParams(params);
    if (next === "contenu") updated.delete("vue");
    else updated.set("vue", next);
    setParams(updated, { replace: true });
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
          {review ? <SegmentedControl.Item value="relire">À relire</SegmentedControl.Item> : null}
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
      ) : vue === "relire" ? (
        <ReviewView />
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
