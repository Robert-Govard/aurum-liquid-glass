import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { PillSelector } from "@/components/layout/PillSelector";
import { useTranslation } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";

export function ThemeCard() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  const options: Array<{ value: Theme; label: string }> = [
    { value: "light", label: t("settings.themeLight") },
    { value: "dark", label: t("settings.themeDark") },
    { value: "system", label: t("settings.themeSystem") },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.theme")}</CardTitle>
      </CardHeader>
      <CardContent>
        <PillSelector options={options} value={theme} onChange={setTheme} />
      </CardContent>
    </Card>
  );
}
