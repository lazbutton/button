import { Button } from "@radix-ui/themes";
import { Copy, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchVolume, stationSmbUrl, type StationVolume } from "../../api/volume";

/** Finder link for the station volume. Hidden when the catalogue does not answer. */
export function StationFolder() {
  const [volume, setVolume] = useState<StationVolume | null>(null);
  const [copied, setCopied] = useState(false);

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

  return (
    <section className="banque-volume" aria-label="Dossier de la station">
      <span className="ui-field-label">Dossier de la station</span>
      {url ? (
        <>
          <code>{url}</code>
          <span className="bacs-network-actions">
            <Button size="2" variant="soft" color="gray" asChild>
              <a href={url}>
                <FolderOpen className="ui-button-icon" />
                Ouvrir
              </a>
            </Button>
            <Button
              type="button"
              size="2"
              variant="ghost"
              color="gray"
              onClick={() => {
                void navigator.clipboard.writeText(url).then(() => {
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1500);
                });
              }}
            >
              <Copy className="ui-button-icon" />
              {copied ? "Copié" : "Copier"}
            </Button>
          </span>
          <small>
            Glisse des fichiers dans Rotation, une banque, l’habillage, une émission ou un bac. Le mot de passe du
            dossier se règle dans Comptes.
          </small>
        </>
      ) : (
        <p>Le dossier réseau n’est pas publié sur cette station.</p>
      )}
    </section>
  );
}
