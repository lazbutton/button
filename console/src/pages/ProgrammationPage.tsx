import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { CategoriesPage } from "./CategoriesPage";
import { HorlogesPage } from "./HorlogesPage";
import { SemainePage } from "./SemainePage";
import { SectionTabs } from "../layout/SectionTabs";

export function ProgrammationPage() {
  const [params, setParams] = useSearchParams();
  useEffect(() => {
    if (params.get("onglet") !== "rotation") return;
    const next = new URLSearchParams(params);
    next.delete("onglet");
    setParams(next, { replace: true });
  }, [params, setParams]);

  return (
    <SectionTabs
      tabs={[
        { id: "horloges", label: "Heures types", panel: <HorlogesPage /> },
        { id: "semaine", label: "Semaine", panel: <SemainePage /> },
        {
          id: "categories",
          label: "Sélections de titres",
          advanced: true,
          panel: <CategoriesPage />,
        },
      ]}
    />
  );
}
