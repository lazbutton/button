import { SegmentedControl } from "@radix-ui/themes";
import { useSearchParams } from "react-router-dom";
import { BankContent } from "../components/banque/BankContent";
import { StationFolder } from "../components/banque/StationFolder";
import { ImporterPage, presetDestination } from "./ImporterPage";

type Vue = "contenu" | "ajouter";

/**
 * Sons → Banque : ce qu'elle contient, ou l'envoi de fichiers. La vue ouverte
 * reste dans l'adresse (`?vue=ajouter`), comme l'onglet.
 */
export function BanquePage() {
  const [params, setParams] = useSearchParams();
  const vue: Vue = params.get("vue") === "ajouter" ? "ajouter" : "contenu";

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
