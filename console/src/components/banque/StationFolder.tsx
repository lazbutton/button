import { Button } from "@radix-ui/themes";
import { FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchVolume, stationSmbUrl, type StationVolume } from "../../api/volume";

/** Finder link for the station volume. Hidden when the catalogue does not answer. */
export function StationFolder() {
  const [volume, setVolume] = useState<StationVolume | null>(null);

  useEffect(() => {
    let cancel = false;
    void fetchVolume().then((value) => {
      if (!cancel) setVolume(value);
    });
    return () => {
      cancel = true;
    };
  }, []);

  if (!volume) return null;
  const url = volume.host ? stationSmbUrl(volume.host, volume.name) : "";

  if (!url) {
    return (
      <section className="banque-volume" aria-label="Dossier de la station">
        <span className="banque-volume-icon" aria-hidden="true">
          <FolderOpen size={14} />
        </span>
        <div className="banque-volume-text">
          <span className="banque-volume-title">Dossier de la station</span>
          <small>Non publié</small>
        </div>
      </section>
    );
  }

  return (
    <section
      className="banque-volume"
      aria-label="Ouvrir sur mon ordinateur"
      title="Via Tailscale. Mot de passe du dossier dans Comptes."
    >
      <Button size="1" variant="soft" color="gray" asChild>
        <a href={url}>
          <FolderOpen className="ui-button-icon" />
          Ouvrir sur mon ordinateur
        </a>
      </Button>
    </section>
  );
}
