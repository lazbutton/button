import { Dialog, IconButton, Tooltip } from "@radix-ui/themes";
import {
  ChevronsLeft,
  ChevronsRight,
  Layers3,
  Library,
  ListMusic,
  Menu,
  Radio,
  Settings,
  X,
} from "lucide-react";
import { useCallback, useState, type MouseEventHandler } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { DiskMeter } from "../components/DiskMeter";
import { Topbar } from "../components/topbar/Topbar";
import { MonitorProvider } from "../lib/MonitorContext";
import { useAccount } from "../api/AccountContext";
import { roleAtLeast, type Role } from "../api/roles";
import { useBrand } from "../lib/BrandContext";

const NAV = [
  { to: "/antenne", label: "Antenne", icon: Radio, min: "animateur" },
  { to: "/conducteur", label: "Conducteur", icon: ListMusic, min: "animateur" },
  { to: "/programmation", label: "Programmation", icon: Layers3, min: "programmateur" },
  { to: "/sons", label: "Sons", icon: Library, min: "programmateur" },
  { to: "/reglages", label: "Réglages", icon: Settings, min: "animateur" },
] as const satisfies ReadonlyArray<{
  to: string;
  label: string;
  icon: typeof Radio;
  min: Role;
}>;

const NAV_KEY = "app-nav-collapsed";

function readCollapsed(preferCollapsed: boolean): boolean {
  try {
    const stored = window.localStorage.getItem(NAV_KEY);
    if (stored === "1") return true;
    if (stored === "0") return false;
    return preferCollapsed;
  } catch {
    return preferCollapsed;
  }
}

function Brand({ onNavigate }: { onNavigate?: MouseEventHandler<HTMLAnchorElement> }) {
  const brand = useBrand();
  // La barre latérale repliée cache le texte : le lien garde un nom, qui le reprend.
  return (
    <Link className="app-brand" to="/antenne" aria-label={brand.suite.name} onClick={onNavigate}>
      <img src="/logo.svg" alt="" width={28} height={28} />
      <span className="app-brand-text">{brand.suite.name}</span>
    </Link>
  );
}

function Navigation({
  collapsed = false,
  onNavigate,
  role,
}: {
  collapsed?: boolean;
  onNavigate?: MouseEventHandler<HTMLAnchorElement>;
  role: Role;
}) {
  const { pathname } = useLocation();
  const items = NAV.filter((item) => roleAtLeast(role, item.min));
  return (
    <nav className="app-nav" aria-label="Console">
      {items.map((item) => {
        const link = (
          <NavLink
            key={item.to}
            to={item.to}
            aria-label={item.label}
            className={({ isActive }) =>
              isActive || (item.to === "/antenne" && pathname === "/") ? "is-active" : undefined
            }
            onClick={onNavigate}
          >
            <item.icon aria-hidden="true" />
            <span className="app-nav-label">{item.label}</span>
          </NavLink>
        );
        return collapsed ? (
          <Tooltip key={item.to} content={item.label} side="right">
            {link}
          </Tooltip>
        ) : (
          link
        );
      })}
    </nav>
  );
}

function MobileNav({ role }: { role: Role }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger>
        <IconButton className="app-mobile-nav-trigger" aria-label="Ouvrir la navigation" variant="ghost" color="gray">
          <Menu size={18} strokeWidth={1.75} />
        </IconButton>
      </Dialog.Trigger>
      <Dialog.Content className="app-mobile-nav" maxWidth="16rem">
        <Dialog.Title className="ui-visually-hidden">Navigation</Dialog.Title>
        <div className="app-mobile-nav-head">
          <Brand onNavigate={() => setOpen(false)} />
          <Dialog.Close>
            <IconButton variant="ghost" color="gray" aria-label="Fermer la navigation">
              <X size={18} strokeWidth={1.75} />
            </IconButton>
          </Dialog.Close>
        </div>
        <Navigation role={role} onNavigate={() => setOpen(false)} />
        {roleAtLeast(role, "programmateur") ? <DiskMeter /> : null}
      </Dialog.Content>
    </Dialog.Root>
  );
}

export function Shell() {
  const { pathname } = useLocation();
  const { isAdmin, role } = useAccount();
  const sons = pathname === "/sons";
  const programmation = pathname === "/programmation";
  const desk = pathname === "/antenne" || pathname === "/";
  const [collapsed, setCollapsed] = useState(() => readCollapsed(false));

  const toggleNav = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(NAV_KEY, next ? "1" : "0");
      } catch {
        /* proto */
      }
      return next;
    });
  }, []);

  return (
    <MonitorProvider lockPublic={!isAdmin}>
    <div className={`app-shell${collapsed ? " is-nav-collapsed" : ""}`}>
      <aside className="app-sidebar" id="app-sidebar" aria-label="Navigation automate">
        <div className="app-sidebar-head">
          <Brand />
          <Tooltip content={collapsed ? "Déplier le menu" : "Replier le menu"}>
            <IconButton
              className="app-nav-toggle"
              variant="ghost"
              color="gray"
              size="1"
              aria-expanded={!collapsed}
              aria-controls="app-sidebar"
              aria-label={collapsed ? "Déplier le menu" : "Replier le menu"}
              onClick={toggleNav}
            >
              {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
            </IconButton>
          </Tooltip>
        </div>

        <Navigation collapsed={collapsed} role={role} />
        {roleAtLeast(role, "programmateur") ? <DiskMeter /> : null}
      </aside>

      <div className="app-main">
        <Topbar leading={<MobileNav role={role} />} />
        <div
          className={`app-page${sons ? " app-page--carts" : ""}${programmation ? " app-page--horloges app-page--autodj" : ""}${desk ? " app-page--desk" : ""}`}
        >
          <Outlet />
        </div>
      </div>
    </div>
    </MonitorProvider>
  );
}
