import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { CartsPage } from "./CartsPage";
import { ImporterPage } from "./ImporterPage";
import { SectionTabs } from "../layout/SectionTabs";

export function SonsPage() {
  const [params, setParams] = useSearchParams();
  const onglet = params.get("onglet");

  useEffect(() => {
    if (onglet !== "habillage" && onglet !== "relais" && onglet !== "carts") return;
    const next = new URLSearchParams(params);
    next.delete("onglet");
    if (!params.get("id")) {
      if (onglet === "habillage" || onglet === "relais") next.set("filtre", onglet);
      if (onglet === "carts") next.set("filtre", "fichiers");
    }
    setParams(next, { replace: true });
  }, [onglet, params, setParams]);

  return (
    <SectionTabs
      tabs={[
        { id: "bacs", label: "Bacs", panel: <CartsPage /> },
        { id: "importer", label: "Banque", panel: <ImporterPage /> },
      ]}
    />
  );
}
