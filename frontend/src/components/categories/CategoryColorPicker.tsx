import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface CategoryColorPickerProps {
  value: string;
  onChange: (color: string) => void;
}

// The same 8-slot colorblind-safe categorical palette the seeded default
// categories and every chart in the app already use — see
// backend/app/db/seed.py and index.css's --series-* tokens.
const PRESET_COLORS = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#4a3aa7",
  "#e34948",
  "#898781",
];

export function CategoryColorPicker({ value, onChange }: CategoryColorPickerProps) {
  const { t } = useTranslation();
  const normalized = value.toLowerCase();

  return (
    <div className="flex flex-wrap items-center gap-2">
      {PRESET_COLORS.map((color) => (
        <button
          key={color}
          type="button"
          aria-label={color}
          aria-pressed={normalized === color}
          onClick={() => onChange(color)}
          className={cn(
            "h-7 w-7 rounded-full border-2 transition-transform",
            normalized === color ? "scale-110 border-text-primary" : "border-transparent hover:scale-105"
          )}
          style={{ backgroundColor: color }}
        />
      ))}
      <input
        type="color"
        aria-label={t("category.form.customColorLabel")}
        title={t("category.form.customColorLabel")}
        value={/^#[0-9a-f]{6}$/i.test(value) ? value : "#898781"}
        onChange={(event) => onChange(event.target.value)}
        className="h-7 w-7 cursor-pointer rounded-md border border-border bg-transparent p-0"
      />
    </div>
  );
}
