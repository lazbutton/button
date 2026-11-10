import { Tabs } from "@radix-ui/themes";
import { useSearchParams } from "react-router-dom";
import type { ReactNode } from "react";
import { PageHeader } from "../ui/PageHeader";

export type SectionTab = {
  id: string;
  label: string;
  panel: ReactNode;
  /** Onglet secondaire, à l’écart des onglets principaux. */
  advanced?: boolean;
};

/**
 * L'onglet ouvert, gardé dans l'adresse (`?onglet=`) : un lien mène à un onglet, et
 * un rechargement le garde. Le premier onglet n'y figure pas. Un onglet inconnu, ou
 * que le rôle ne voit pas, ouvre le premier.
 */
export function useOnglet(ids: readonly string[]): [string, (id: string) => void] {
  const [params, setParams] = useSearchParams();
  const requested = params.get("onglet");
  const current = requested && ids.includes(requested) ? requested : ids[0];
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    if (id === ids[0]) next.delete("onglet");
    else next.set("onglet", id);
    setParams(next, { replace: true });
  };
  return [current, select];
}

export function SectionTabs({
  title,
  description,
  tabs,
}: {
  title?: string;
  description?: string;
  tabs: SectionTab[];
}) {
  const [current, select] = useOnglet(tabs.map((tab) => tab.id));
  const primary = tabs.filter((tab) => !tab.advanced);
  const advanced = tabs.filter((tab) => tab.advanced);

  return (
    <div className="ui-page section-page">
      {title || description ? <PageHeader title={title} description={description} /> : null}
      <Tabs.Root value={current} onValueChange={select}>
        <Tabs.List className="section-tabs">
          {primary.map((tab) => (
            <Tabs.Trigger key={tab.id} value={tab.id}>
              {tab.label}
            </Tabs.Trigger>
          ))}
          {advanced.length ? (
            <span className="section-tabs-kicker" aria-hidden="true">
              Avancé
            </span>
          ) : null}
          {advanced.map((tab) => (
            <Tabs.Trigger key={tab.id} value={tab.id} className="section-tab-advanced">
              {tab.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        {tabs.map((tab) => (
          <Tabs.Content key={tab.id} value={tab.id} className="section-tab-panel">
            {tab.panel}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </div>
  );
}
