import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { PillSelector } from "@/components/layout/PillSelector";
import { useTranslation, type Language } from "@/lib/i18n";

export function LanguageCard() {
  const { t, language, setLanguage } = useTranslation();

  const options: Array<{ value: Language; label: string }> = [
    { value: "ru", label: t("settings.languageRussian") },
    { value: "en", label: t("settings.languageEnglish") },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.language")}</CardTitle>
      </CardHeader>
      <CardContent>
        <PillSelector options={options} value={language} onChange={setLanguage} />
      </CardContent>
    </Card>
  );
}
