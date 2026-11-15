import { Button, Dialog, Spinner } from "@radix-ui/themes";
import { CheckCheck, Keyboard } from "lucide-react";
import { FIELD_LABELS, count, fieldValue, lotsOf, natureCount, type NatureGroup } from "../../api/fiches";

/**
 * « Par nature de changement » (FON-79) : les propositions sûres de toute la
 * banque, regroupées par ce qu'elles changent, chacune avec son nombre et dix
 * exemples pris au hasard. Un groupe s'accepte d'un geste, après confirmation,
 * ou se relit au clavier (FON-78).
 */
export function NatureGroups({
  groups,
  canWrite,
  busy,
  onAccept,
  onKeyboard,
}: {
  groups: NatureGroup[];
  canWrite: boolean;
  busy: boolean;
  onAccept: (group: NatureGroup) => void;
  onKeyboard: (group: NatureGroup) => void;
}) {
  return (
    <section className="fiches-natures" aria-labelledby="fiches-natures-title">
      <h3 id="fiches-natures-title" className="fiches-natures-title">
        Par nature de changement
      </h3>
      <p className="fiches-hint">
        Les propositions sûres de toute la banque, regroupées par ce qu'elles changent. Lis dix exemples, puis accepte
        le groupe d'un geste, ou relis-le au clavier.
      </p>
      <ul className="fiches-natures-list">
        {groups.map((group) => (
          <li key={group.nature} className="fiches-nature">
            <div className="fiches-nature-head">
              <div className="fiches-nature-copy">
                <strong>{group.label}</strong>
                <span>{natureCount(group)}</span>
              </div>
              <div className="fiches-nature-actions">
                <Button size="2" variant="soft" color="gray" disabled={busy} onClick={() => onKeyboard(group)}>
                  <Keyboard className="ui-button-icon" />
                  Relire au clavier<span className="ui-visually-hidden"> : {group.label}</span>
                </Button>
                {canWrite ? (
                  <Button size="2" variant="soft" disabled={busy} onClick={() => onAccept(group)}>
                    <CheckCheck className="ui-button-icon" />
                    Accepter les {count(group.count)}
                    <span className="ui-visually-hidden"> : {group.label}</span>
                  </Button>
                ) : null}
              </div>
            </div>
            <details className="fiches-nature-examples">
              <summary>
                {group.examples.length === 1 ? "Un exemple" : `${group.examples.length} exemples`}, pris au hasard
              </summary>
              <NatureExamples group={group} />
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Ce que changent les exemples d'un groupe, champ par champ. */
function NatureExamples({ group }: { group: NatureGroup }) {
  return (
    <ul className="fiches-nature-list" aria-label={`Exemples : ${group.label}`}>
      {group.examples.map((example) => (
        <li key={example.id}>
          <span className="fiches-field">{FIELD_LABELS[example.field] ?? example.field}</span>{" "}
          <span className="fiches-before">{fieldValue(example.field, example.before)}</span>
          <span aria-hidden="true"> → </span>
          <span className="ui-visually-hidden"> devient </span>
          <strong>{fieldValue(example.field, example.value)}</strong>
          <span className="fiches-nature-who">
            {" "}
            · {example.title || "Sans titre"}
            {example.artist ? `, ${example.artist}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * « Accepter les N » d'un groupe : son nombre, ses lots, et ses dix exemples
 * avant d'écrire. Les lots partent par 500, comme le moteur les prend.
 */
export function AcceptGroupDialog({
  group,
  busy,
  onCancel,
  onConfirm,
}: {
  group: NatureGroup;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const lots = lotsOf(group.ids.length);
  const titles = `${count(group.titles)} titre${group.titles === 1 ? "" : "s"}`;
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onCancel();
      }}
    >
      <Dialog.Content maxWidth="34rem">
        <Dialog.Title>
          {group.label} : accepter les {count(group.ids.length)} propositions ?
        </Dialog.Title>
        <Dialog.Description size="2" mb="2">
          Elles s'écrivent dans les fichiers de {titles}, puis dans la bibliothèque,{" "}
          {lots > 1 ? `en ${lots} lots de 500 au plus, chacun noté au journal` : "et le lot se note au journal"}. Un
          titre à l'antenne ou en file attend la fin de son passage. Ce qu'elles changent, sur dix prises au hasard :
        </Dialog.Description>
        <NatureExamples group={group} />
        <div className="bacs-dialog-actions">
          {busy ? <Spinner size="2" /> : null}
          <Button size="2" variant="soft" color="gray" disabled={busy} onClick={onCancel}>
            Garder
          </Button>
          <Button size="2" highContrast disabled={busy} onClick={onConfirm}>
            {busy ? "En cours…" : `Accepter les ${count(group.ids.length)}`}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
