import {
  Button,
  Dialog,
  DropdownMenu,
  Flex,
  IconButton,
  Select,
  Spinner,
  Switch,
  Text,
  TextField,
} from "@radix-ui/themes";
import { MoreHorizontal, Plus, Search, SearchX, Trash2, Users } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { apiDelete, apiPostJson, apiPut, ApiRequestError } from "../api/client";
import { emissionWindowLabel } from "../api/emissionMeta";
import { slotsForHost } from "../api/hostSlots";
import { DAY_LONG } from "../api/programmationView";
import { setVolumePassword } from "../api/volume";
import {
  canBroadcast,
  listedAsHost,
  permissionsFromRole,
  ROLE_LABEL,
  roleFromPermissions,
  type Role,
} from "../api/roles";
import { SessionGate } from "../api/SessionGate";
import { initials } from "../api/topbar";
import type { Emission, EmissionsResponse, User, UsersResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { StreamToken } from "../components/antenne/StreamToken";
import { SettingsHead } from "../components/reglages/SettingsCard";
import "../styles/pages/reglages.css";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { EmptyState } from "../ui/EmptyState";
import { FormField, SelectField } from "../ui/FormField";

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

/** Réglages → Comptes, pour un admin : qui entre dans la console, avec quel rôle. */
export function UsersPage() {
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
      const matchesFilter = filter === "all" || (filter === "direct" ? broadcast : role === filter);
      return matchesSearch && matchesFilter;
    });
  }, [filter, search, users]);
  const filtering = search.trim() !== "" || filter !== "all";
  const resetFilters = () => {
    setSearch("");
    setFilter("all");
  };

  return (
    <div className="reglages-section">
      <SettingsHead
        title="Comptes"
        count={data ? users.length : undefined}
        description="Une personne, un compte. Le rôle dit ce qu’elle peut faire, et « Peut passer en direct » s’y ajoute."
        actions={
          <Button highContrast onClick={() => setCreateOpen(true)}>
            <Plus className="ui-button-icon" aria-hidden="true" />
            Nouveau compte
          </Button>
        }
      />

      <SessionGate loading={loading} error={error} ready={data != null} onRetry={() => void reload()}>
        <div className="reglages-card reglages-users">
          <div className="reglages-toolbar">
            <TextField.Root
              className="ui-field-control reglages-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rechercher un compte…"
              aria-label="Rechercher un compte"
            >
              <TextField.Slot>
                <Search size={15} aria-hidden="true" />
              </TextField.Slot>
            </TextField.Root>
            <Select.Root value={filter} onValueChange={(value) => setFilter(value as UserFilter)}>
              <Select.Trigger className="reglages-filter" aria-label="Afficher" />
              <Select.Content variant="soft" position="popper">
                {USER_FILTERS.map((option) => (
                  <Select.Item key={option.value} value={option.value}>
                    {option.label}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <span className="reglages-toolbar-count" role="status">
              {filtering ? `${filteredUsers.length} sur ${users.length}` : ""}
            </span>
          </div>

          {filteredUsers.length ? (
            <table className="reglages-users-table">
              <thead>
                <tr>
                  <th scope="col">Compte</th>
                  <th scope="col">Rôle</th>
                  <th scope="col">Peut passer en direct</th>
                  <th scope="col">
                    <span className="ui-visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
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
              </tbody>
            </table>
          ) : (
            <div className="reglages-users-empty">
              <EmptyState
                icon={users.length ? SearchX : Users}
                title={users.length ? "Aucun résultat" : "Aucun compte"}
                description={
                  users.length
                    ? "Aucun compte ne correspond à cette recherche ou à ce rôle."
                    : "Crée un compte pour ouvrir la console à quelqu’un."
                }
                actionLabel={users.length ? "Tout afficher" : "Nouveau compte"}
                onAction={users.length ? resetFilters : () => setCreateOpen(true)}
              />
            </div>
          )}
        </div>
      </SessionGate>
      <CreateUserDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={reload} onFeedback={show} />
      <ProtoToast message={message} />
    </div>
  );
}

function slotLabel(row: Emission): string {
  return `${row.day_of_week != null ? `${DAY_LONG[row.day_of_week]} · ` : ""}${emissionWindowLabel(row)}`;
}

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
  const locked = updating != null || deleting;

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
    <tr>
      <th scope="row" className="reglages-user-cell">
        {/* La mise en page va dans un bloc à part : une cellule en flex perdrait son rôle de cellule. */}
        <div className="reglages-user">
          <span className="reglages-avatar" aria-hidden="true">
            {initials(user.username)}
          </span>
          <span className="reglages-user-copy">
            <span className="reglages-user-name">{user.username}</span>
            {user.notes ? <span className="reglages-user-notes">{user.notes}</span> : null}
          </span>
        </div>
      </th>
      <td className="reglages-user-role">
        <Select.Root value={role} disabled={locked} onValueChange={(value) => void save(value as Role, broadcast, "role")}>
          <Select.Trigger className="ui-field-control" aria-label={`Rôle de ${user.username}`} />
          <Select.Content variant="soft" position="popper">
            {ROLE_OPTIONS.map((option) => (
              <Select.Item key={option.value} value={option.value}>
                {option.label}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </td>
      <td className="reglages-user-direct">
        <label className="reglages-direct">
          <Switch
            checked={broadcast}
            disabled={locked}
            onCheckedChange={(next) => void save(role, next, "direct")}
            aria-label={`Peut passer en direct pour ${user.username}`}
          />
          {/* Sur un téléphone, la colonne n'a plus d'en-tête : le libellé revient à côté. */}
          <span className="reglages-direct-label" aria-hidden="true">
            Peut passer en direct
          </span>
        </label>
      </td>
      <td className="reglages-user-actions">
        {updating ? (
          <span className="reglages-row-busy" role="status">
            Mise à jour…
          </span>
        ) : null}
        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger>
            <IconButton
              className="reglages-row-menu"
              variant="ghost"
              color="gray"
              disabled={locked}
              aria-label={`Actions pour ${user.username}`}
            >
              {deleting ? <Spinner size="1" /> : <MoreHorizontal size={16} aria-hidden="true" />}
            </IconButton>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content variant="soft" align="end">
            <DropdownMenu.Item disabled={locked} onSelect={() => setFicheOpen(true)}>
              Fiche du compte
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item color="red" disabled={locked} onSelect={() => setConfirmOpen(true)}>
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
      </td>
    </tr>
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

  const saveNotes = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
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

  const savePassword = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !password.trim()) return;
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
      <Dialog.Content className="reglages-dialog" maxWidth="31rem">
        <div className="reglages-dialog-who">
          <span className="reglages-avatar is-large" aria-hidden="true">
            {initials(user.username)}
          </span>
          <div className="reglages-dialog-who-copy">
            <Dialog.Title>{user.username}</Dialog.Title>
            <Dialog.Description>
              {ROLE_LABEL[role]}
              {canBroadcast(user.permissions) ? " · peut passer en direct" : ""}
            </Dialog.Description>
          </div>
        </div>

        <section className="reglages-dialog-section">
          <h3>Créneaux</h3>
          {slots.length === 0 ? (
            <p className="reglages-empty">Aucun créneau nommé pour ce compte.</p>
          ) : (
            <ul className="reglages-list">
              {slots.map((row) => (
                <li key={row.id}>
                  <span className="reglages-list-when">{slotLabel(row)}</span>{" "}
                  <span className="reglages-list-what">{row.title}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <form className="reglages-dialog-section" onSubmit={(event) => void saveNotes(event)}>
          <FormField label="Notes">
            <TextField.Root className="ui-field-control" value={notes} onChange={(event) => setNotes(event.target.value)} />
          </FormField>
          <div className="reglages-actions">
            <Button type="submit" variant="soft" color="gray" disabled={busy}>
              Enregistrer les notes
            </Button>
          </div>
        </form>

        <form className="reglages-dialog-section" onSubmit={(event) => void savePassword(event)}>
          <FormField label="Nouveau mot de passe" hint="Remplace l’ancien. La personne s’en sert à la prochaine connexion.">
            <TextField.Root
              className="ui-field-control"
              type="password"
              value={password}
              autoComplete="new-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </FormField>
          <div className="reglages-actions">
            <Button type="submit" variant="soft" color="gray" disabled={busy || !password.trim()}>
              Réinitialiser le mot de passe
            </Button>
          </div>
        </form>

        {listedAsHost(user.permissions) ? (
          <section className="reglages-dialog-section">
            <h3>Jeton d’encodeur</h3>
            <p className="reglages-dialog-text">
              Le mot de passe de son encodeur. Renouveler le jeton coupe l’ancien : transmets le nouveau.
            </p>
            <StreamToken owner={user.id} />
          </section>
        ) : null}

        <section className="reglages-dialog-section">
          <h3>Dossier de la station</h3>
          {role === "animateur" ? (
            <p className="reglages-dialog-text">Ce compte n’a pas le dossier de la station.</p>
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
                <Text as="p" size="2" color="red" role="alert">
                  {folderError}
                </Text>
              ) : null}
              <div className="reglages-actions">
                <Button
                  type="button"
                  variant="soft"
                  color="gray"
                  disabled={busy || folderPassword.length < 8}
                  onClick={() => void saveFolder(false)}
                >
                  Enregistrer le mot de passe du dossier
                </Button>
                <Button type="button" variant="soft" color="gray" disabled={busy} onClick={() => void saveFolder(true)}>
                  Retirer l’accès
                </Button>
              </div>
            </>
          )}
        </section>

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
      <Dialog.Content className="reglages-dialog" maxWidth="29rem">
        <form onSubmit={(event) => void submit(event)}>
          <Dialog.Title>Nouveau compte</Dialog.Title>
          <Dialog.Description>
            Un identifiant, un mot de passe et un rôle. Transmets ensuite le mot de passe à la personne.
          </Dialog.Description>
          <div className="reglages-dialog-fields">
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
            <FormField label="Mot de passe" hint="Il sera demandé dès la première connexion.">
              <TextField.Root
                className="ui-field-control"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
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
            <label className="reglages-switch-row">
              <span className="reglages-switch-copy">
                <span className="reglages-switch-title">Peut passer en direct</span>
                <span className="reglages-switch-hint">Ouvre le harbor sur le créneau de cette personne.</span>
              </span>
              <Switch checked={broadcast} disabled={busy} onCheckedChange={setBroadcast} />
            </label>
            {formError ? (
              <Text as="p" size="2" color="red" role="alert">
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
            <Button type="submit" highContrast disabled={busy || !username.trim() || !password}>
              {busy ? <Spinner size="1" /> : null}
              {busy ? "Création…" : "Créer le compte"}
            </Button>
          </Flex>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
