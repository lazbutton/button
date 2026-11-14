import { Button, Checkbox, IconButton, Popover } from "@radix-ui/themes";
import { ArrowDown, ArrowUp, Columns3 } from "lucide-react";
import {
  DEFAULT_COLUMNS,
  columnLabel,
  moveColumn,
  toggleColumn,
  type ColumnKey,
} from "../../api/bankTitles";

/**
 * « Colonnes » : which columns the table shows, and in which order. The shown
 * ones come first, in their order, each moved with its arrows; the hidden ones
 * after, in their own order. The title always shows.
 */
export function ColumnsPicker({
  columns,
  known = DEFAULT_COLUMNS,
  onChange,
}: {
  columns: ColumnKey[];
  /** The columns the engine fills: not the tags before FON-74. */
  known?: ColumnKey[];
  onChange: (columns: ColumnKey[]) => void;
}) {
  const hidden = known.filter((key) => !columns.includes(key));
  const rows = [...columns, ...hidden];
  const changed = columns.join(",") !== known.join(",");

  return (
    <Popover.Root>
      <Popover.Trigger>
        <Button size="2" variant="soft" color="gray">
          <Columns3 className="ui-button-icon" />
          Colonnes
        </Button>
      </Popover.Trigger>
      <Popover.Content size="1" align="end" className="banque-columns" aria-label="Colonnes du tableau">
        <p className="banque-columns-title">Colonnes du tableau</p>
        <ul className="banque-columns-list">
          {rows.map((key) => {
            const shown = columns.includes(key);
            const index = columns.indexOf(key);
            const label = columnLabel(key);
            return (
              <li key={key} className={shown ? "" : "is-hidden"}>
                <label className="banque-columns-check">
                  <Checkbox
                    size="1"
                    checked={shown}
                    disabled={key === "title"}
                    onCheckedChange={() => onChange(toggleColumn(columns, key))}
                  />
                  <span>{label}</span>
                </label>
                {shown ? (
                  <span className="banque-columns-move">
                    <IconButton
                      size="1"
                      variant="ghost"
                      color="gray"
                      disabled={index === 0}
                      aria-label={`Monter ${label}`}
                      onClick={() => onChange(moveColumn(columns, key, -1))}
                    >
                      <ArrowUp size={14} />
                    </IconButton>
                    <IconButton
                      size="1"
                      variant="ghost"
                      color="gray"
                      disabled={index === columns.length - 1}
                      aria-label={`Descendre ${label}`}
                      onClick={() => onChange(moveColumn(columns, key, 1))}
                    >
                      <ArrowDown size={14} />
                    </IconButton>
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
        <Button size="1" variant="soft" color="gray" disabled={!changed} onClick={() => onChange(DEFAULT_COLUMNS)}>
          Rétablir les colonnes
        </Button>
      </Popover.Content>
    </Popover.Root>
  );
}
