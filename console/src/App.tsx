import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ShieldOff } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Shell } from "./layout/Shell";
import { useAccount } from "./api/AccountContext";
import { roleAtLeast, type Role } from "./api/roles";
import { ApiSession } from "./api/SessionGate";
import { label } from "./lib/brand";
import { useBrand } from "./lib/BrandContext";
import { AntennePage } from "./pages/AntennePage";
import { ConducteurPage } from "./pages/ConducteurPage";
import { InvitationPage } from "./pages/InvitationPage";
import { ProgrammationPage } from "./pages/ProgrammationPage";
import { ReglagesPage } from "./pages/ReglagesPage";
import { SonsPage } from "./pages/SonsPage";
import { LoadingState } from "./ui/DataState";
import { EmptyState } from "./ui/EmptyState";

function RoleGate({ allow, children }: { allow: Role; children: ReactNode }) {
  const { ready, role } = useAccount();
  if (!ready) return <LoadingState label="Chargement…" />;
  if (!roleAtLeast(role, allow)) return <ReservedAccess />;
  return children;
}

function MissingPage() {
  const navigate = useNavigate();
  return (
    <div className="ui-page">
      <EmptyState
        icon={ShieldOff}
        title="Page introuvable"
        description="Cette adresse ne correspond à aucune section."
        actionLabel="Retour à l’antenne"
        onAction={() => navigate("/antenne")}
      />
    </div>
  );
}

function ReservedAccess() {
  const navigate = useNavigate();
  return (
    <div className="ui-page">
      <EmptyState
        icon={ShieldOff}
        title="Accès réservé"
        description="Cette page n’est pas ouverte pour ton rôle."
        actionLabel="Retour à l’antenne"
        onAction={() => navigate("/antenne")}
      />
    </div>
  );
}

/** Le titre de l'onglet suit le nom de la station, réglé dans le moteur. La page d'un invité pose le sien. */
function ConsoleTitle() {
  const brand = useBrand();
  useEffect(() => {
    document.title = `${brand.suite.name} — ${label(brand, "console", "title") || "Horloges"}`;
  }, [brand]);
  return null;
}

export function App() {
  const location = useLocation();
  // A guest's page: no console session, no shell, only their link.
  if (location.pathname === "/invitation") return <InvitationPage />;
  return (
    <>
      {/* Hors de la session : l'écran de connexion prend aussi le titre. */}
      <ConsoleTitle />
      <ApiSession>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<AntennePage />} />
            <Route path="antenne" element={<AntennePage />} />
            <Route path="conducteur" element={<ConducteurPage />} />
            <Route path="programmation" element={<RoleGate allow="programmateur"><ProgrammationPage /></RoleGate>} />
            <Route path="sons" element={<RoleGate allow="programmateur"><SonsPage /></RoleGate>} />
            <Route path="reglages" element={<ReglagesPage />} />
            <Route path="*" element={<MissingPage />} />
          </Route>
        </Routes>
      </ApiSession>
    </>
  );
}
