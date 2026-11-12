import { Tabs } from "@radix-ui/themes";
import { Activity, CircleFadingArrowUp, RadioTower, UserRound, Users, type LucideIcon } from "lucide-react";
import { useRef, type ReactNode } from "react";
import { useAccount } from "../api/AccountContext";
import { reglagesSections, type ReglagesSection, type ReglagesSectionId } from "../api/reglages";
import { useOnglet } from "../layout/SectionTabs";
import { useMediaQuery } from "../lib/useMediaQuery";
import { LoadingState } from "../ui/DataState";
import { PageHeader } from "../ui/PageHeader";
import { AutomatePage } from "./AutomatePage";
import { MisesAJourPage } from "./MisesAJourPage";
import { MonComptePage } from "./MonComptePage";
import { StationPage } from "./StationPage";
import { UsersPage } from "./UsersPage";
import "../styles/pages/reglages.css";

const ICON: Record<ReglagesSectionId, LucideIcon> = {
  comptes: Users,
  station: RadioTower,
  automate: Activity,
  "mises-a-jour": CircleFadingArrowUp,
  compte: UserRound,
};

function panel(id: ReglagesSectionId): ReactNode {
  switch (id) {
    case "comptes":
      return <UsersPage />;
    case "station":
      return <StationPage />;
    case "automate":
      return <AutomatePage />;
    case "mises-a-jour":
      return <MisesAJourPage />;
    case "compte":
      return <MonComptePage />;
  }
}

/** Sous cette largeur, sur un téléphone ou une page zoomée, le menu passe en ligne, au-dessus. */
const NARROW = "(max-width: 760px)";

function Trigger({ section }: { section: ReglagesSection }) {
  const Icon = ICON[section.id];
  return (
    <Tabs.Trigger value={section.id} className="reglages-nav-item">
      <Icon className="reglages-nav-icon" aria-hidden="true" />
      {section.label}
    </Tabs.Trigger>
  );
}

/**
 * Réglages : pour l'admin, un menu à gauche, la station d'abord, puis son compte.
 * Les autres rôles n'ont que leur compte, sans menu. La partie ouverte est dans
 * l'adresse (`?onglet=`).
 */
export function ReglagesPage() {
  const { ready, role } = useAccount();
  const sections = reglagesSections(role);
  const [current, select] = useOnglet(sections.map((section) => section.id));
  const narrow = useMediaQuery(NARROW);
  const layout = useRef<HTMLDivElement>(null);

  // Le rôle n'est pas encore lu : sans attendre, un admin verrait d'abord la page d'un animateur.
  if (!ready) return <LoadingState label="Lecture du compte…" />;

  if (sections.length === 1) {
    return (
      <div className="ui-page reglages-page">
        <PageHeader title="Réglages" />
        <div className="reglages-solo">{panel(sections[0].id)}</div>
      </div>
    );
  }

  return (
    <div className="ui-page reglages-page">
      <PageHeader
        title="Réglages"
        description="Les comptes de l’équipe, la station, l’automate et ses mises à jour, pour toute la radio. Puis ton compte."
      />
      <Tabs.Root
        ref={layout}
        className="reglages-layout"
        orientation={narrow ? "horizontal" : "vertical"}
        value={current}
        onValueChange={(id) => {
          select(id);
          // Une autre partie s'ouvre en haut, pas au défilement de la précédente.
          layout.current?.closest(".app-page")?.scrollTo({ top: 0 });
        }}
      >
        <Tabs.List className="reglages-nav" aria-label="Parties des réglages">
          <span className="reglages-nav-kicker" aria-hidden="true">
            Administration
          </span>
          {sections
            .filter((section) => section.admin)
            .map((section) => (
              <Trigger key={section.id} section={section} />
            ))}
          <span className="reglages-nav-rule" aria-hidden="true" />
          {sections
            .filter((section) => !section.admin)
            .map((section) => (
              <Trigger key={section.id} section={section} />
            ))}
        </Tabs.List>
        {sections.map((section) => (
          <Tabs.Content key={section.id} value={section.id} className="reglages-panel">
            {panel(section.id)}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </div>
  );
}
