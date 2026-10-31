import { DropdownMenu } from "@radix-ui/themes";
import { CodeXml, ExternalLink, LogOut, Monitor, Moon, Sun, UserRound, type LucideIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAccount } from "../../api/AccountContext";
import { ROLE_LABEL } from "../../api/roles";
import { useLogout } from "../../api/SessionGate";
import { accountLabel, initials } from "../../api/topbar";
import { APPEARANCE_OPTIONS, useAppearance } from "../../lib/Appearance";
import { useBrand } from "../../lib/BrandContext";
import { DEFAULT_SOURCE_URL, type AppearanceChoice } from "../../lib/brand";

const APPEARANCE_ICON: Record<AppearanceChoice, LucideIcon> = {
  system: Monitor,
  light: Sun,
  dark: Moon,
};

/** Compte : identité, apparence, code source (AGPL), déconnexion. */
export function AccountMenu() {
  const { account, role } = useAccount();
  const { choice, setChoice } = useAppearance();
  const logout = useLogout();
  const navigate = useNavigate();
  const brand = useBrand();
  const username = account?.username ?? "";
  const mark = initials(username);
  const sourceUrl = brand.suite.sourceUrl || DEFAULT_SOURCE_URL;

  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger>
        <button type="button" className="tb-account" aria-label={accountLabel(username)}>
          <span className="tb-avatar" aria-hidden="true">
            {mark}
          </span>
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content variant="soft" align="end" sideOffset={6} className="tb-menu tb-menu--account">
        <div className="tb-menu-who">
          <span className="tb-avatar is-large" aria-hidden="true">
            {mark}
          </span>
          <span className="tb-menu-copy">
            <span>{username || "Compte"}</span>
            <small>{ROLE_LABEL[role]}</small>
          </span>
        </div>
        <DropdownMenu.Separator />
        <DropdownMenu.Item onSelect={() => navigate("/reglages?onglet=compte")}>
          <UserRound size={15} aria-hidden="true" />
          Mon compte
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Label>Apparence</DropdownMenu.Label>
        <DropdownMenu.RadioGroup value={choice} onValueChange={(value) => setChoice(value as AppearanceChoice)}>
          {APPEARANCE_OPTIONS.map((option) => {
            const Icon = APPEARANCE_ICON[option.id];
            return (
              <DropdownMenu.RadioItem
                key={option.id}
                value={option.id}
                // Le menu reste ouvert : on voit le thème changer.
                onSelect={(event) => event.preventDefault()}
              >
                <Icon size={15} aria-hidden="true" />
                {option.label}
              </DropdownMenu.RadioItem>
            );
          })}
        </DropdownMenu.RadioGroup>
        <DropdownMenu.Separator />
        <DropdownMenu.Item asChild>
          <a href={sourceUrl} target="_blank" rel="noreferrer">
            <CodeXml size={15} aria-hidden="true" />
            Code source
            <span className="tb-menu-tag">AGPL</span>
            <ExternalLink size={13} aria-hidden="true" className="tb-menu-end" />
          </a>
        </DropdownMenu.Item>
        <DropdownMenu.Item onSelect={logout}>
          <LogOut size={15} aria-hidden="true" />
          Se déconnecter
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
