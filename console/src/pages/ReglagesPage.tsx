import { useAccount } from "../api/AccountContext";
import { UsersPage } from "./UsersPage";
import { MonComptePage } from "./MonComptePage";
import { AutomatePage } from "./AutomatePage";
import { StationPage } from "./StationPage";
import { SectionTabs } from "../layout/SectionTabs";

export function ReglagesPage() {
  const { isAdmin } = useAccount();
  const tabs = [
    ...(isAdmin
      ? [
          { id: "comptes", label: "Comptes", panel: <UsersPage embedded /> },
          { id: "station", label: "Station", panel: <StationPage /> },
        ]
      : []),
    { id: "compte", label: "Mon compte", panel: <MonComptePage /> },
    ...(isAdmin ? [{ id: "automate", label: "Automate", panel: <AutomatePage /> }] : []),
  ];
  return (
    <SectionTabs
      title="Réglages"
      description="Ton compte, et pour l’admin les comptes et les réglages de la station."
      tabs={tabs}
    />
  );
}
