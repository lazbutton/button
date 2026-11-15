import { FichesCard } from "../components/reglages/FichesCard";
import { ListenLinkCard } from "../components/reglages/ListenLinkCard";
import { SettingsHead } from "../components/reglages/SettingsCard";
import { VerdictEraser } from "../components/reglages/VerdictEraser";
import "../styles/pages/reglages.css";

/**
 * Réglages → Fiches (FON-26), pour un admin, une fois le rangement de la banque ouvert :
 * la recherche des fiches et ses sources, puis le lien d'écoute (FON-84). Les pochettes
 * (FON-83) viendront ici.
 */
export function FichesReglagesPage() {
  return (
    <div className="reglages-section">
      <SettingsHead
        title="Fiches"
        description="Ce que la station cherche en ligne sur les titres de sa banque, et ce qu’elle en envoie. Chaque carte s’enregistre à part."
      />
      <div className="reglages-stack reglages-stack--form">
        <FichesCard />
        <ListenLinkCard title="Lien d’écoute" />
        <VerdictEraser />
      </div>
    </div>
  );
}
