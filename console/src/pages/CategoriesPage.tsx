import {
  Badge,
  Button,
  Code,
  Dialog,
  DropdownMenu,
  Flex,
  IconButton,
  Spinner,
  Table,
  Text,
  TextField,
} from "@radix-ui/themes";
import { MoreHorizontal, Pencil, Plus, Search, SearchX, Tags, TestTube2, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { apiDelete, apiGet, apiPostJson, apiPut, ApiRequestError } from "../api/client";
import { SessionGate } from "../api/SessionGate";
import type { CategoriesResponse, Category } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import "../styles/pages/admin.css";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { EmptyState } from "../ui/EmptyState";
import { FormField, SelectField } from "../ui/FormField";
import { PageHeader } from "../ui/PageHeader";
import { Panel, SectionHeader } from "../ui/Panel";

type CategoryFilter = "all" | "populated" | "empty";

const CATEGORY_FILTERS = [
  { value: "all", label: "Toutes les sélections" },
  { value: "populated", label: "Avec des titres" },
  { value: "empty", label: "Sans titre" },
];

export function CategoriesPage() {
  const { data, error, reload } = useApiJson<CategoriesResponse>(
    "/autodj/categories.json",
  );
  const { message, show } = useProtoToast();
  const categories = data?.categories ?? [];
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<CategoryFilter>("all");
  const filteredCategories = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("fr");
    return categories.filter((category) => {
      const matchesSearch =
        !needle ||
        [category.name, category.query, category.empty_query].some((value) =>
          value.toLocaleLowerCase("fr").includes(needle),
        );
      const matchesFilter =
        filter === "all" ||
        (filter === "populated" && category.count > 0) ||
        (filter === "empty" && category.count === 0);
      return matchesSearch && matchesFilter;
    });
  }, [categories, filter, search]);
  const resetFilters = () => {
    setSearch("");
    setFilter("all");
  };

  return (
    <>
      <div className="ui-page admin-page">
        <PageHeader
          eyebrow="Programmation"
          title="Sélections de titres"
          description="Une requête choisit les titres. Le repli sert quand elle ne ramène rien."
          actions={
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="ui-button-icon" aria-hidden="true" />
              Nouvelle sélection
            </Button>
          }
        />

        <SessionGate
          loading={false}
          error={error}
          ready={data != null}
          onRetry={() => void reload()}
        >
          <Panel padded={false} className="admin-panel">
            <div className="admin-panel-heading">
              <SectionHeader
                title="Sélections de titres"
                description="Nom, requête, repli, et le nombre de titres trouvés."
                count={filteredCategories.length}
              />
            </div>

            <div className="admin-toolbar">
              <FormField label="Rechercher">
                <TextField.Root
                  className="ui-field-control admin-search-control"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Nom ou requête…"
                  aria-label="Rechercher une sélection"
                >
                  <TextField.Slot>
                    <Search size={15} aria-hidden="true" />
                  </TextField.Slot>
                </TextField.Root>
              </FormField>
              <SelectField
                label="Afficher"
                value={filter}
                options={CATEGORY_FILTERS}
                onValueChange={(value) => setFilter(value as CategoryFilter)}
              />
              <Text className="admin-result-count" size="1" color="gray">
                {filteredCategories.length === categories.length
                  ? `${categories.length} au total`
                  : `${filteredCategories.length} sur ${categories.length}`}
              </Text>
            </div>

            {filteredCategories.length ? (
              <div className="admin-table-scroll">
                <Table.Root className="admin-table admin-category-table">
                  <Table.Header>
                    <Table.Row>
                      <Table.ColumnHeaderCell>Nom</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell>Requête</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell>Titres</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell>Repli si vide</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell aria-label="Actions" />
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {filteredCategories.map((category) => (
                      <CategoryRow
                        key={category.id}
                        category={category}
                        onSaved={reload}
                        onFeedback={show}
                        onError={show}
                      />
                    ))}
                  </Table.Body>
                </Table.Root>
              </div>
            ) : (
              <div className="admin-empty">
                <EmptyState
                  icon={categories.length ? SearchX : Tags}
                  title={categories.length ? "Aucun résultat" : "Aucune sélection"}
                  description={
                    categories.length
                      ? "Aucune sélection ne correspond à cette recherche ou à ce filtre."
                      : "Crée une sélection de titres pour choisir les morceaux avec une requête."
                  }
                  actionLabel={categories.length ? "Réinitialiser les filtres" : "Créer une sélection"}
                  onAction={categories.length ? resetFilters : () => setCreateOpen(true)}
                />
              </div>
            )}
          </Panel>
        </SessionGate>
      </div>
      <CategoryDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSubmit={async (fields) => {
          await apiPostJson("/autodj/categories.json", fields);
          await reload();
          show("Sélection créée");
        }}
        onError={(text) => show(text)}
      />
      <ProtoToast message={message} />
    </>
  );
}

function CategoryRow({
  category,
  onSaved,
  onFeedback,
  onError,
}: {
  category: Category;
  onSaved: () => Promise<unknown> | void;
  onFeedback: (text: string) => void;
  onError: (text: string) => void;
}) {
  const [editOpen, setEditOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sample, setSample] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const testCategory = async () => {
    setTesting(true);
    try {
      const result = await apiGet<{ count: number; sample: { title: string }[] }>(
        `/autodj/testquery.json?query=${encodeURIComponent(category.query)}`,
      );
      setSample(`${result.count} titres`);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Test impossible.");
    } finally {
      setTesting(false);
    }
  };

  const deleteCategory = async () => {
    setDeleting(true);
    try {
      await apiDelete(`/autodj/categories/${category.id}.json`);
      await onSaved();
      onFeedback("Sélection supprimée");
      setConfirmOpen(false);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Suppression impossible.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Table.Row>
      <Table.RowHeaderCell data-label="Nom">
        <div className="admin-primary-cell">
          <span className="admin-primary-title">{category.name}</span>
          {sample ? (
            <span className="admin-inline-feedback" role="status" aria-live="polite">
              {sample}
            </span>
          ) : null}
        </div>
      </Table.RowHeaderCell>
      <Table.Cell data-label="Requête">
        <Code className="ui-code admin-query-code" variant="ghost">
          {category.query}
        </Code>
      </Table.Cell>
      <Table.Cell data-label="Titres">
        <Badge color={category.count ? "green" : "gray"} variant="soft">
          {category.count}
        </Badge>
      </Table.Cell>
      <Table.Cell data-label="Repli si vide">
        {category.empty_query ? (
          <Code className="ui-code admin-query-code" variant="ghost">
            {category.empty_query}
          </Code>
        ) : (
          <span className="admin-muted">Non défini</span>
        )}
      </Table.Cell>
      <Table.Cell className="admin-actions-cell" data-label="Actions">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            <IconButton
              className="admin-row-menu"
              size="1"
              variant="ghost"
              color="gray"
              disabled={testing || deleting}
              aria-label={`Actions pour ${category.name}`}
            >
              {testing || deleting ? (
                <Spinner size="1" />
              ) : (
                <MoreHorizontal size={16} aria-hidden="true" />
              )}
            </IconButton>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end">
            <DropdownMenu.Item
              disabled={testing || deleting}
              onSelect={() => void testCategory()}
            >
              <TestTube2 size={14} aria-hidden="true" />
              Tester la requête
            </DropdownMenu.Item>
            <DropdownMenu.Item
              disabled={testing || deleting}
              onSelect={() => setEditOpen(true)}
            >
              <Pencil size={14} aria-hidden="true" />
              Modifier
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item
              color="red"
              disabled={testing || deleting}
              onSelect={() => setConfirmOpen(true)}
            >
              <Trash2 size={14} aria-hidden="true" />
              Supprimer
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
        <ConfirmDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Supprimer cette sélection ?"
          description={
            <>
              Tu supprimes <strong>{category.name}</strong> pour de bon.
            </>
          }
          confirmLabel="Supprimer"
          busy={deleting}
          onConfirm={deleteCategory}
        />
      </Table.Cell>
      <CategoryDialog
        open={editOpen}
        initial={category}
        onOpenChange={setEditOpen}
        onSubmit={async (fields) => {
          await apiPut(`/autodj/categories/${category.id}.json`, fields);
          await onSaved();
          setSample(null);
          onFeedback("Sélection enregistrée");
        }}
        onError={onError}
      />
    </Table.Row>
  );
}

function CategoryDialog({
  open,
  initial,
  onOpenChange,
  onSubmit,
  onError,
}: {
  open: boolean;
  initial?: Category;
  onOpenChange: (open: boolean) => void;
  onSubmit: (fields: { name: string; query: string; empty_query: string }) => Promise<void>;
  onError: (text: string) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [query, setQuery] = useState(initial?.query ?? "");
  const [emptyQuery, setEmptyQuery] = useState(initial?.empty_query ?? "");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !name.trim() || !query.trim()) return;
    setBusy(true);
    try {
      await onSubmit({
        name: name.trim(),
        query: query.trim(),
        empty_query: emptyQuery.trim(),
      });
      onOpenChange(false);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Enregistrement impossible.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        onOpenChange(next);
        if (next) {
          setName(initial?.name ?? "");
          setQuery(initial?.query ?? "");
          setEmptyQuery(initial?.empty_query ?? "");
        }
      }}
    >
      <Dialog.Content className="admin-dialog" maxWidth="31rem">
        <form onSubmit={(event) => void submit(event)}>
          <Dialog.Title>{initial ? "Modifier la sélection" : "Nouvelle sélection"}</Dialog.Title>
          <Dialog.Description>
            Définis la requête principale et, si besoin, une requête de repli.
          </Dialog.Description>
          <div className="admin-dialog-fields">
            <FormField label="Nom">
              <TextField.Root
                className="ui-field-control"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoFocus
                required
              />
            </FormField>
            <FormField
              label="Requête"
              hint="Rotation 24/24 : path:/media/10-rotation. Thème : grouping:jazz."
            >
              <TextField.Root
                className="ui-field-control admin-code-input"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                spellCheck={false}
                required
              />
            </FormField>
            <FormField
              label="Repli si vide"
              hint="Facultatif. Elle sert quand la requête principale ne ramène rien."
            >
              <TextField.Root
                className="ui-field-control admin-code-input"
                value={emptyQuery}
                onChange={(event) => setEmptyQuery(event.target.value)}
                spellCheck={false}
              />
            </FormField>
          </div>
          <Flex gap="2" mt="5" justify="end">
            <Dialog.Close>
              <Button type="button" variant="soft" color="gray" disabled={busy}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" disabled={busy || !name.trim() || !query.trim()}>
              {busy ? <Spinner size="1" /> : null}
              {busy ? "Enregistrement…" : initial ? "Enregistrer" : "Créer la sélection"}
            </Button>
          </Flex>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
