import { CloudOff } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAccount } from "../../api/AccountContext";
import { BankUnsupportedError, bankShelves, type BankShelf } from "../../api/bankContent";
import { createBank } from "../../api/banks";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import { CollectionView } from "./CollectionView";
import { CreateBankDialog } from "./CreateBankDialog";
import { ShelfList } from "./ShelfList";

/**
 * What the bank holds: rotation and the collections on the left, the titles of
 * the one chosen on the right. The collection chosen stays in the address
 * (`?collection=`), so a link or a reload keeps it.
 */
export function BankContent({ onAdd }: { onAdd: (id: string) => void }) {
  const { isAdmin } = useAccount();
  const [params, setParams] = useSearchParams();
  const wanted = params.get("collection") || "rotation";
  const [shelves, setShelves] = useState<BankShelf[] | null>(null);
  const [problem, setProblem] = useState("");
  const [unsupported, setUnsupported] = useState(false);
  const [view, setView] = useState<"list" | "detail">(params.get("collection") ? "detail" : "list");
  const [creating, setCreating] = useState<string | null>(null);
  const { toast, show, dismiss } = useAppToast();
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      const next = await bankShelves();
      if (!alive.current) return;
      setShelves(next);
      setProblem("");
      setUnsupported(false);
    } catch (caught) {
      if (!alive.current) return;
      if (caught instanceof BankUnsupportedError) setUnsupported(true);
      else setProblem(caught instanceof Error ? caught.message : "Le catalogue ne répond pas.");
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
    };
  }, [load]);

  const choose = (id: string) => {
    const next = new URLSearchParams(params);
    if (id === "rotation") next.delete("collection");
    else next.set("collection", id);
    setParams(next, { replace: true });
    setView("detail");
  };

  // A collection gone from the disk, or a name typed in the address: rotation.
  const shelf = shelves?.find((item) => item.id === wanted) ?? shelves?.find((item) => item.group === "rotation") ?? null;

  let body;
  if (unsupported) {
    body = (
      <EmptyState
        icon={CloudOff}
        title="Mets à jour la station"
        description="Le catalogue de cette station ne sait pas encore montrer le contenu de la banque. L'envoi de fichiers, dans « Ajouter », marche toujours."
      />
    );
  } else if (!shelves) {
    body = problem ? (
      <ErrorState title="Banque illisible" description={problem} onRetry={() => void load()} />
    ) : (
      <LoadingState label="Lecture de la banque…" />
    );
  } else if (!shelf) {
    body = <ErrorState title="Banque illisible" description="Le catalogue n'a rendu aucune collection." onRetry={() => void load()} />;
  } else {
    body = (
      <div className="bacs banque-shelves" data-view={view}>
        <ShelfList
          shelves={shelves}
          selectedId={shelf.id}
          onSelect={choose}
          onCreate={isAdmin ? (label) => setCreating(label) : undefined}
        />
        <CollectionView
          key={shelf.id}
          shelf={shelf}
          shelves={shelves}
          isAdmin={isAdmin}
          onBack={() => setView("list")}
          onAdd={onAdd}
          onChanged={() => void load()}
          onRenamed={(destination, before) => {
            show(`La collection « ${before} » s'appelle maintenant « ${destination.label} ».`, "success");
            void load();
          }}
          onDeleted={(gone) => {
            show(`Collection « ${gone.label} » supprimée.`, "success");
            choose("rotation");
            setView("list");
            void load();
          }}
          notify={show}
        />
      </div>
    );
  }

  return (
    <div className="bacs-page">
      {body}
      <CreateBankDialog
        open={creating != null}
        onOpenChange={(open) => {
          if (!open) setCreating(null);
        }}
        initialLabel={creating ?? ""}
        destinations={shelves ?? []}
        onCreate={async (label, folder) => {
          const created = await createBank(label, folder);
          await load();
          choose(created.id);
          show(`Collection « ${created.label} » créée. « Ajouter des titres » y envoie des fichiers.`, "success");
        }}
      />
      <AppToast toast={toast} onDismiss={dismiss} />
    </div>
  );
}
