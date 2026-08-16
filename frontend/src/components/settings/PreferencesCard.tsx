import { Card, CardContent } from "@/components/ui/Card";
import { PillSelector } from "@/components/layout/PillSelector";
import { useTranslation, type Language } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";

/** Language and theme side by side — both are pure client-side display
 * preferences (unlike currency, which is server-persisted), so pairing
 * them saves a whole card's worth of vertical space over listing each on
 * its own. Stacks back to one column on mobile. */
export function PreferencesCard() {
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme } = useTheme();

  const languageOptions: Array<{ value: Language; label: string }> = [
    { value: "ru", label: t("settings.languageRussian") },
    { value: "en", label: t("settings.languageEnglish") },
  ];
  const themeOptions: Array<{ value: Theme; label: string }> = [
    { value: "light", label: t("settings.themeLight") },
    { value: "dark", label: t("settings.themeDark") },
    { value: "system", label: t("settings.themeSystem") },
  ];

  return (
    <Card>
      <CardContent className="grid grid-cols-1 gap-5 divide-y divide-border pt-4 sm:grid-cols-2 sm:gap-6 sm:divide-x sm:divide-y-0 sm:pt-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t("settings.language")}</p>
          <div className="mt-2">
            <PillSelector options={languageOptions} value={language} onChange={setLanguage} />
          </div>
        </div>
        <div className="pt-5 sm:pl-6 sm:pt-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t("settings.theme")}</p>
          <div className="mt-2">
            <PillSelector options={themeOptions} value={theme} onChange={setTheme} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
