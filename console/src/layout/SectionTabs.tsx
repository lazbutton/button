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

export function SectionTabs({
  title,
  description,
  tabs,
}: {
  title: string;
  description?: string;
  tabs: SectionTab[];
}) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("onglet");
  const current = tabs.some((tab) => tab.id === requested) ? requested! : tabs[0].id;
  const primary = tabs.filter((tab) => !tab.advanced);
  const advanced = tabs.filter((tab) => tab.advanced);

  return (
    <div className="ui-page section-page">
      <PageHeader title={title} description={description} />
      <Tabs.Root
        value={current}
        onValueChange={(value) => {
          const next = new URLSearchParams(params);
          if (value === tabs[0].id) next.delete("onglet");
          else next.set("onglet", value);
          setParams(next, { replace: true });
        }}
      >
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
