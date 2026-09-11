import type { ChangeEvent, ReactNode, SelectHTMLAttributes } from "react";
import { Children, isValidElement, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { Dialog } from "@/components/ui/Dialog";
import { GroupedList, GroupedListItem } from "@/components/ui/GroupedList";

interface ParsedOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

interface ParsedGroup {
  label: string;
  options: ParsedOption[];
}

/** Разбирает children `<Select>` (обычные `<option>` вперемешку с
 * `<optgroup>`, как у нативного `<select>`) в плоскую структуру для
 * рендера собственной панели выбора. `Children.forEach` сам пропускает
 * `false`/`null`/`undefined` — код вызова часто рендерит опции условно
 * (`{list.length > 0 && <optgroup>...}`), это не требует отдельной
 * обработки. */
function parseOptions(children: ReactNode): Array<ParsedOption | ParsedGroup> {
  const entries: Array<ParsedOption | ParsedGroup> = [];
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return;
    if (child.type === "option") {
      const props = child.props as { value?: string; disabled?: boolean; children?: ReactNode };
      entries.push({ value: String(props.value ?? ""), label: props.children, disabled: props.disabled });
    } else if (child.type === "optgroup") {
      const props = child.props as { label?: string; children?: ReactNode };
      const options: ParsedOption[] = [];
      Children.forEach(props.children, (groupChild) => {
        if (!isValidElement(groupChild) || groupChild.type !== "option") return;
        const optionProps = groupChild.props as { value?: string; disabled?: boolean; children?: ReactNode };
        options.push({ value: String(optionProps.value ?? ""), label: optionProps.children, disabled: optionProps.disabled });
      });
      entries.push({ label: String(props.label ?? ""), options });
    }
  });
  return entries;
}

function isGroup(entry: ParsedOption | ParsedGroup): entry is ParsedGroup {
  return "options" in entry;
}

type Block = { kind: "group"; group: ParsedGroup } | { kind: "options"; options: ParsedOption[] };

/** Схлопывает подряд идущие негруппированные опции в один блок — каждая
 * такая серия рисуется одной карточкой GroupedList, а не отдельной
 * карточкой на строку; `<optgroup>` всегда получает свою карточку. */
function toBlocks(entries: Array<ParsedOption | ParsedGroup>): Block[] {
  const blocks: Block[] = [];
  for (const entry of entries) {
    if (isGroup(entry)) {
      blocks.push({ kind: "group", group: entry });
      continue;
    }
    const last = blocks[blocks.length - 1];
    if (last?.kind === "options") {
      last.options.push(entry);
    } else {
      blocks.push({ kind: "options", options: [entry] });
    }
  }
  return blocks;
}

/** Замена нативного `<select>` — на Android WebView он открывался как
 * системное меню поверх приложения, визуально никак не связанное с
 * остальным интерфейсом (обнаружено на реальном устройстве). Показывает
 * те же варианты в уже существующей панели снизу (Dialog + GroupedList —
 * тот же компонент, что и панель "Ещё" в мобильной навигации).
 *
 * Публичный API намеренно такой же, как у нативного `<select>`
 * (`value`/`onChange`/`children` из `<option>`/`<optgroup>`,
 * `SelectHTMLAttributes`), чтобы ни один из мест использования в
 * приложении не пришлось переписывать — `onChange` получает объект с тем
 * же `target.value`, что и настоящее событие `change` у `<select>`. */
export function Select({ value, onChange, disabled, id, className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const entries = parseOptions(children);
  const flatOptions = entries.flatMap((entry) => (isGroup(entry) ? entry.options : [entry]));
  const selected = flatOptions.find((option) => option.value === value);

  function selectValue(next: string) {
    setOpen(false);
    onChange?.({ target: { value: next } } as unknown as ChangeEvent<HTMLSelectElement>);
  }

  function renderOption(option: ParsedOption) {
    return (
      <GroupedListItem
        key={option.value}
        label={option.label}
        disabled={option.disabled}
        onClick={option.disabled ? undefined : () => selectValue(option.value)}
        trailing={!option.disabled && option.value === value ? <Check size={16} className="shrink-0 text-text-primary" /> : null}
      />
    );
  }

  return (
    <>
      <button
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => setOpen(true)}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface-1 px-3 text-left text-sm text-text-primary outline-none focus:border-series-1 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...(rest as Record<string, unknown>)}
      >
        <span className="truncate">{selected?.label ?? value}</span>
        <ChevronDown size={16} className="shrink-0 text-text-muted" />
      </button>

      <Dialog open={open} onClose={() => setOpen(false)} title={t("common.select")}>
        <div className="space-y-4">
          {toBlocks(entries).map((block, index) =>
            block.kind === "group" ? (
              <div key={`group-${index}`}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">{block.group.label}</p>
                <GroupedList>{block.group.options.map(renderOption)}</GroupedList>
              </div>
            ) : (
              <GroupedList key={`options-${index}`}>{block.options.map(renderOption)}</GroupedList>
            )
          )}
        </div>
      </Dialog>
    </>
  );
}
