import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useAccount } from "../api/AccountContext";
import { JournalView } from "../components/journal/JournalView";
import { BanquePage } from "./BanquePage";
import { CartsPage } from "./CartsPage";
import { SectionTabs, type SectionTab } from "../layout/SectionTabs";

export function SonsPage() {
  const [params, setParams] = useSearchParams();
  const onglet = params.get("onglet");
  const { account, isAdmin } = useAccount();
  // FON-71 : le journal des gestes, pour le Programmateur, une fois le rangement de la banque ouvert.
  const journal = account?.features?.bank_tidy === true && (isAdmin || account.permissions.autodj === true);

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

  const tabs: SectionTab[] = [
    { id: "bacs", label: "Bacs", panel: <CartsPage /> },
    { id: "importer", label: "Banque", panel: <BanquePage /> },
  ];
  if (journal) tabs.push({ id: "journal", label: "Journal", panel: <JournalView /> });
  return <SectionTabs tabs={tabs} />;
}
