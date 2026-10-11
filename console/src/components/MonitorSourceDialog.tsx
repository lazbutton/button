import { Dialog, Tooltip } from "@radix-ui/themes";
import { Check, FileAudio, Radio, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useMonitorState } from "../lib/MonitorContext";
import type { MonitorSourceId } from "../lib/monitorSource";

const SOURCE_ICON: Record<MonitorSourceId, LucideIcon> = {
  files: FileAudio,
  public: Radio,
};

function shortStream(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`;
  } catch {
    return url;
  }
}

export function MonitorSourceDialog() {
  const { sourceId, sources, setSourceId, canChooseSource } = useMonitorState();
  const [open, setOpen] = useState(false);
  if (!canChooseSource) return null;
  const current = sources.find((source) => source.id === sourceId);
  const Icon = SOURCE_ICON[sourceId] ?? Radio;
  const chip = current?.chip ?? "Source";
  const full = current?.label ?? chip;

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Tooltip content={`Source d’écoute : ${full}`}>
        <Dialog.Trigger>
          <button
            type="button"
            className="app-listen-source"
            data-source={sourceId}
            aria-label={`Source d’écoute : ${full}. Changer.`}
            aria-haspopup="dialog"
          >
            <Icon size={14} strokeWidth={2} aria-hidden="true" />
            <span className="app-listen-source-label">{chip}</span>
          </button>
        </Dialog.Trigger>
      </Tooltip>
      <Dialog.Content className="app-listen-dialog" maxWidth="26rem">
        <Dialog.Title>Source d’écoute</Dialog.Title>
        <Dialog.Description size="2">
          Ce que tu entends dans le casque. Les auditeurs restent sur l’antenne.
        </Dialog.Description>
        <div className="app-listen-choices" role="radiogroup" aria-label="Source d’écoute">
          {sources.map((source) => {
            const SourceIcon = SOURCE_ICON[source.id];
            const selected = source.id === sourceId;
            return (
              <label
                key={source.id}
                className="app-listen-choice"
                data-source={source.id}
                data-selected={selected ? "true" : "false"}
              >
                <input
                  type="radio"
                  name="listen-source"
                  value={source.id}
                  checked={selected}
                  onChange={() => {
                    setSourceId(source.id);
                    setOpen(false);
                  }}
                />
                <span className="app-listen-choice-icon" aria-hidden="true">
                  <SourceIcon size={18} strokeWidth={2} />
                </span>
                <span className="app-listen-choice-copy">
                  <span className="app-listen-choice-title">{source.label}</span>
                  <span className="app-listen-choice-hint">{source.hint}</span>
                  {source.id === "public" ? (
                    <span className="app-listen-choice-url">{shortStream(source.stream)}</span>
                  ) : null}
                </span>
                <span className="app-listen-choice-mark" aria-hidden="true">
                  {selected ? <Check size={16} strokeWidth={2.5} /> : null}
                </span>
              </label>
            );
          })}
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
