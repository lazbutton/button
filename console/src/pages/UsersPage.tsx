import {
  Badge,
  Button,
  Checkbox,
  Dialog,
  DropdownMenu,
  Flex,
  IconButton,
  Spinner,
  Table,
  Text,
  TextField,
} from "@radix-ui/themes";
import { KeyRound, MoreHorizontal, Plus, Search, SearchX, ShieldCheck, Trash2, Users } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { apiDelete, apiPostJson, apiPut, ApiRequestError } from "../api/client";
import { emissionWindowLabel } from "../api/emissionMeta";
import { slotsForHost } from "../api/hostSlots";
import { setVolumePassword } from "../api/volume";
import {
  canBroadcast,
  permissionsFromRole,
  ROLE_LABEL,
  roleFromPermissions,
  type Role,
} from "../api/roles";
import { SessionGate } from "../api/SessionGate";
import type { Emission, EmissionsResponse, User, UsersResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import "../styles/pages/admin.css";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { EmptyState } from "../ui/EmptyState";
import { FormField, SelectField } from "../ui/FormField";
import { PageHeader } from "../ui/PageHeader";
import { Panel, SectionHeader } from "../ui/Panel";

type UserFilter = "all" | Role | "direct";

const ROLE_OPTIONS = (Object.keys(ROLE_LABEL) as Role[]).map((role) => ({
  value: role,
  label: ROLE_LABEL[role],
}));

const USER_FILTERS = [
  { value: "all", label: "Tous les rôles" },
  ...ROLE_OPTIONS,
  { value: "direct", label: "Peuvent passer en direct" },
];

export function UsersPage({ embedded = false }: { embedded?: boolean }) {
  const { data, error, loading, reload } = useApiJson<UsersResponse>("/users.json");
  const emissions = useApiJson<EmissionsResponse>("/antenne/emissions.json");
  const { message, show } = useProtoToast();
  const users = data?.users ?? [];
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<UserFilter>("all");
  const filteredUsers = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("fr");
    return users.filter((user) => {
      const role = roleFromPermissions(user.permissions);
      const broadcast = canBroadcast(user.permissions);
      const matchesSearch =
        !needle ||
        [user.username, user.notes, ROLE_LABEL[role], broadcast ? "direct" : ""].some((value) =>
          value.toLocaleLowerCase("fr").includes(needle),
        );
      const matchesFilter =
        filter === "all" ||
        (filter === "direct" ? broadcast : role === filter);
      return matchesSearch && matchesFilter;
    });
  }, [filter, search, users]);
  const adminCount = users.filter((user) => roleFromPermissions(user.permissions) === "admin").length;
  const resetFilters = () => {
    setSearch("");
    setFilter("all");
  };

  const actions = (
    <>
      <Badge variant="soft" color="gray">
        <Users size={13} aria-hidden="true" />
        {users.length} compte{users.length === 1 ? "" : "s"}
      </Badge>
      <Badge variant="soft" color="gray">
        <ShieldCheck size={13} aria-hidden="true" />
        {adminCount} admin{adminCount === 1 ? "" : "s"}
      </Badge>
      <Button onClick={() => setCreateOpen(true)}>
        <Plus className="ui-button-icon" aria-hidden="true" />
        Nouveau compte
      </Button>
    </>
  );

  return (
    <>
      <div className={embedded ? "admin-page admin-page--embedded" : "ui-page admin-page"}>
        {embedded ? null : (
          <PageHeader
            eyebrow="Administration"
            title="Comptes"
            description="Chaque personne a un rôle. L’interrupteur « Peut passer en direct » est indépendant."
            actions={actions}
          />
        )}

        <SessionGate loading={loading} error={error} ready={data != null} onRetry={() => void reload()}>
          <Panel padded={false} className="admin-panel">
            <div className="admin-panel-heading">
              <SectionHeader
                title="Accès Radiotomate"
                description="Chaque compte a un rôle. L’interrupteur « Peut passer en direct » est à part."
                count={filteredUsers.length}
                actions={embedded ? <div className="admin-page-actions">{actions}</div> : undefined}
              />
            </div>

            <div className="admin-toolbar">
              <FormField label="Rechercher">
                <TextField.Root
                  className="ui-field-control admin-search-control"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Identifiant ou rôle…"
                  aria-label="Rechercher un compte"
                >
                  <TextField.Slot>
                    <Search size={15} aria-hidden="true" />
                  </TextField.Slot>
                </TextField.Root>
              </FormField>
              <SelectField
                label="Afficher"
                value={filter}
                options={USER_FILTERS}
                onValueChange={(value) => setFilter(value as UserFilter)}
              />
              <Text className="admin-result-count" size="1" color="gray">
                {filteredUsers.length === users.length
                  ? `${users.length} au total`
                  : `${filteredUsers.length} sur ${users.length}`}
              </Text>
            </div>

            {filteredUsers.length ? (
              <div className="admin-table-scroll">
                <Table.Root className="admin-table admin-users-table">
                  <Table.Header>
                    <Table.Row>
                      <Table.ColumnHeaderCell>Compte</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell>Rôle</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell aria-label="Actions" />
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {filteredUsers.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  emissions={emissions.data?.emissions}
                  onChanged={reload}
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
                  icon={users.length ? SearchX : Users}
                  title={users.length ? "Aucun résultat" : "Aucun compte"}
                  description={
                    users.length
                      ? "Aucun compte ne correspond à cette recherche ou à ce rôle."
                      : "Créez un compte pour donner accès à l’administration Radiotomate."
                  }
                  actionLabel={users.length ? "Réinitialiser les filtres" : "Créer un compte"}
                  onAction={users.length ? resetFilters : () => setCreateOpen(true)}
                />
              </div>
            )}
          </Panel>
        </SessionGate>
      </div>
      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={reload}
        onFeedback={show}
      />
      <ProtoToast message={message} />
    </>
  );
}

const DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];

function UserRow({
  user,
  emissions,
  onChanged,
  onFeedback,
  onError,
}: {
  user: User;
  emissions?: Emission[];
  onChanged: () => Promise<unknown> | void;
  onFeedback: (text: string) => void;
  onError: (text: string) => void;
}) {
  const [updating, setUpdating] = useState<"role" | "direct" | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [ficheOpen, setFicheOpen] = useState(false);
  const role = roleFromPermissions(user.permissions);
  const broadcast = canBroadcast(user.permissions);

  const save = async (nextRole: Role, nextBroadcast: boolean, kind: "role" | "direct") => {
    setUpdating(kind);
    try {
      await apiPut(`/users/${user.id}.json`, {
        permissions: permissionsFromRole(nextRole, nextBroadcast),
      });
      await onChanged();
      onFeedback(`Rôle de ${user.username} mis à jour`);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Mise à jour impossible.");
    } finally {
      setUpdating(null);
    }
  };

  const deleteUser = async () => {
    setDeleting(true);
    try {
      await apiDelete(`/users/${user.id}.json`);
      await onChanged();
      onFeedback("Compte supprimé");
      setConfirmOpen(false);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Suppression impossible.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Table.Row>
      <Table.RowHeaderCell data-label="Compte">
        <div className="admin-primary-cell">
          <span className="admin-primary-title">{user.username}</span>
          {user.notes ? <span className="admin-primary-meta">{user.notes}</span> : null}
        </div>
      </Table.RowHeaderCell>
      <Table.Cell data-label="Rôle">
        <div className="admin-permissions" role="group" aria-label={`Rôle de ${user.username}`}>
          <SelectField
            label="Rôle"
            value={role}
            options={ROLE_OPTIONS}
            disabled={updating != null || deleting}
            onValueChange={(value) => void save(value as Role, broadcast, "role")}
          />
          <label className={`admin-permission${broadcast ? " is-active" : ""}`}>
            {updating === "direct" ? (
              <Spinner size="1" />
            ) : (
              <Checkbox
                checked={broadcast}
                disabled={updating != null || deleting}
                onCheckedChange={(next) => void save(role, next === true, "direct")}
                aria-label={`Peut passer en direct pour ${user.username}`}
              />
            )}
            <span>Peut passer en direct</span>
          </label>
        </div>
      </Table.Cell>
      <Table.Cell className="admin-actions-cell" data-label="Actions">
        <div className="admin-user-actions">
          {updating ? (
            <span className="admin-row-busy" role="status" aria-live="polite">
              Mise à jour…
            </span>
          ) : null}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              <IconButton
                className="admin-row-menu"
                size="1"
                variant="ghost"
                color="gray"
                disabled={updating != null || deleting}
                aria-label={`Actions pour ${user.username}`}
              >
                {deleting ? <Spinner size="1" /> : <MoreHorizontal size={16} aria-hidden="true" />}
              </IconButton>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end">
              <DropdownMenu.Item
                disabled={updating != null || deleting}
                onSelect={() => setFicheOpen(true)}
              >
                Fiche du compte
              </DropdownMenu.Item>
              <DropdownMenu.Item
                color="red"
                disabled={updating != null || deleting}
                onSelect={() => setConfirmOpen(true)}
              >
                <Trash2 size={14} aria-hidden="true" />
                Supprimer le compte
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
          <ConfirmDialog
            open={confirmOpen}
            onOpenChange={setConfirmOpen}
            title="Supprimer le compte ?"
            description={
              <>
                Le compte <strong>{user.username}</strong> perdra immédiatement tous ses accès.
              </>
            }
            confirmLabel="Supprimer"
            busy={deleting}
            onConfirm={deleteUser}
          />
          <UserFiche
            user={user}
            emissions={emissions}
            open={ficheOpen}
            onOpenChange={setFicheOpen}
            onChanged={onChanged}
            onFeedback={onFeedback}
            onError={onError}
          />
        </div>
      </Table.Cell>
    </Table.Row>
  );
}

function UserFiche({
  user,
  emissions,
  open,
  onOpenChange,
  onChanged,
  onFeedback,
  onError,
}: {
  user: User;
  emissions?: Emission[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChanged: () => Promise<unknown> | void;
  onFeedback: (text: string) => void;
  onError: (text: string) => void;
}) {
  const [notes, setNotes] = useState(user.notes);
  const [password, setPassword] = useState("");
  const [folderPassword, setFolderPassword] = useState("");
  const [folderError, setFolderError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const slots = slotsForHost(emissions, user.username);
  const role = roleFromPermissions(user.permissions);

  const saveNotes = async () => {
    setBusy(true);
    try {
      await apiPut(`/users/${user.id}.json`, { notes });
      await onChanged();
      onFeedback("Notes enregistrées");
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Notes impossibles.");
    } finally {
      setBusy(false);
    }
  };

  const savePassword = async () => {
    if (!password.trim()) return;
    setBusy(true);
    try {
      await apiPut(`/users/${user.id}.json`, { password });
      setPassword("");
      onFeedback("Mot de passe réinitialisé");
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Réinitialisation impossible.");
    } finally {
      setBusy(false);
    }
  };

  const saveFolder = async (clear: boolean) => {
    setBusy(true);
    setFolderError(null);
    try {
      await setVolumePassword(user.username, clear ? "" : folderPassword);
      setFolderPassword("");
      onFeedback(clear ? "Accès au dossier retiré" : "Mot de passe du dossier enregistré");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Enregistrement impossible.";
      setFolderError(message);
      onError(message);
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
          setNotes(user.notes);
          setPassword("");
          setFolderPassword("");
          setFolderError(null);
        }
      }}
    >
      <Dialog.Content className="admin-dialog" maxWidth="29rem">
        <Dialog.Title>{user.username}</Dialog.Title>
        <Dialog.Description>
          {ROLE_LABEL[roleFromPermissions(user.permissions)]}
          {canBroadcast(user.permissions) ? " · peut passer en direct" : ""}
        </Dialog.Description>
        <div className="admin-dialog-fields">
          <h3 className="admin-account-title">Créneaux</h3>
          {slots.length === 0 ? (
            <p>Aucun créneau nommé pour ce compte.</p>
          ) : (
            <ul className="admin-slots">
              {slots.map((row) => (
                <li key={row.id}>
                  {row.day_of_week != null ? `${DAYS[row.day_of_week]} · ` : ""}
                  {emissionWindowLabel(row)} · {row.title}
                </li>
              ))}
            </ul>
          )}
          <FormField label="Notes">
            <TextField.Root
              className="ui-field-control"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </FormField>
          <Button type="button" disabled={busy} onClick={() => void saveNotes()}>
            Enregistrer les notes
          </Button>
          <FormField label="Nouveau mot de passe" hint="Remplace l’ancien. La personne s’en sert à la prochaine connexion.">
            <TextField.Root
              className="ui-field-control"
              type="password"
              value={password}
              autoComplete="new-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </FormField>
          <Button type="button" disabled={busy || !password.trim()} onClick={() => void savePassword()}>
            Réinitialiser le mot de passe
          </Button>
          {role === "animateur" ? (
            <p>Ce compte n’a pas le dossier de la station.</p>
          ) : (
            <>
              <FormField
                label="Mot de passe du dossier"
                hint="Distinct du mot de passe de la console. Huit caractères au moins. Il ouvre le volume dans le Finder."
              >
                <TextField.Root
                  className="ui-field-control"
                  type="password"
                  value={folderPassword}
                  autoComplete="new-password"
                  onChange={(event) => setFolderPassword(event.target.value)}
                />
              </FormField>
              {folderError ? (
                <Text size="2" color="red" role="alert">
                  {folderError}
                </Text>
              ) : null}
              <Flex gap="2" wrap="wrap">
                <Button type="button" disabled={busy || folderPassword.length < 8} onClick={() => void saveFolder(false)}>
                  Enregistrer le mot de passe du dossier
                </Button>
                <Button type="button" variant="soft" color="gray" disabled={busy} onClick={() => void saveFolder(true)}>
                  Retirer l’accès
                </Button>
              </Flex>
            </>
          )}
        </div>
        <Flex gap="2" mt="4" justify="end">
          <Dialog.Close>
            <Button type="button" variant="soft" color="gray" disabled={busy}>
              Fermer
            </Button>
          </Dialog.Close>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function CreateUserDialog({
  open,
  onOpenChange,
  onCreated,
  onFeedback,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => Promise<unknown> | void;
  onFeedback: (text: string) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("animateur");
  const [broadcast, setBroadcast] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !username.trim() || !password) return;
    setBusy(true);
    setFormError(null);
    try {
      await apiPostJson("/users.json", {
        username: username.trim(),
        password,
        permissions: permissionsFromRole(role, broadcast),
      });
      await onCreated();
      onFeedback("Compte créé");
      onOpenChange(false);
    } catch (caught) {
      setFormError(caught instanceof ApiRequestError ? caught.message : "Création impossible.");
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
          setUsername("");
          setPassword("");
          setRole("animateur");
          setBroadcast(false);
          setFormError(null);
        }
      }}
    >
      <Dialog.Content className="admin-dialog" maxWidth="29rem">
        <form onSubmit={(event) => void submit(event)}>
          <Dialog.Title>Nouveau compte</Dialog.Title>
          <Dialog.Description>
            Choisis un rôle. L’interrupteur ouvre le harbor sur le créneau de cette personne.
          </Dialog.Description>
          <div className="admin-dialog-icon" aria-hidden="true">
            <KeyRound size={20} />
          </div>
          <div className="admin-dialog-fields">
            <FormField label="Identifiant">
              <TextField.Root
                className="ui-field-control"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </FormField>
            <SelectField
              label="Rôle"
              value={role}
              options={ROLE_OPTIONS}
              disabled={busy}
              onValueChange={(value) => setRole(value as Role)}
            />
            <label className="admin-permission">
              <Checkbox
                checked={broadcast}
                disabled={busy}
                onCheckedChange={(next) => setBroadcast(next === true)}
                aria-label="Peut passer en direct"
              />
              <span>Peut passer en direct</span>
            </label>
            <FormField
              label="Mot de passe"
              hint="Il sera demandé dès la première connexion."
            >
              <TextField.Root
                className="ui-field-control"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                required
              />
            </FormField>
            {formError ? (
              <Text size="2" color="red" role="alert">
                {formError}
              </Text>
            ) : null}
          </div>
          <Flex gap="2" mt="5" justify="end">
            <Dialog.Close>
              <Button type="button" variant="soft" color="gray" disabled={busy}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" disabled={busy || !username.trim() || !password}>
              {busy ? <Spinner size="1" /> : null}
              {busy ? "Création…" : "Créer le compte"}
            </Button>
          </Flex>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
