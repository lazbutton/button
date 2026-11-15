import { useState } from "react";
import { coverUrl } from "../../api/covers";
import "../../styles/pages/fiches.css";

/**
 * La pochette d'un titre trouvé (FON-83), par son lien seulement : le navigateur la demande à Deezer,
 * Apple Music ou Bandcamp, sans dire d'où il vient. Une image qui ne se charge pas disparaît, sans
 * rien laisser de cassé.
 */
export function Cover({ url, album, size = 96 }: { url: unknown; album?: string; size?: number }) {
  const link = coverUrl(url);
  const [broken, setBroken] = useState<string | null>(null);
  if (!link || link === broken) return null;
  return (
    <img
      className="fiches-cover"
      src={link}
      alt={album ? `Pochette de « ${album} »` : "Pochette de l’album trouvé"}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setBroken(link)}
    />
  );
}
