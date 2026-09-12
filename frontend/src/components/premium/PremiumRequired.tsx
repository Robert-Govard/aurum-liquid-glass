import { Lock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";

/** Rendered instead of a page's normal content when the current user
 * isn't on Premium — used by CryptoPage/AdvicePage/RoiPage/CsvImportPage
 * (see the spec: these four features stay visible in navigation with a
 * lock badge rather than being hidden, so this is what a free user sees
 * on actually opening one of them). There's no payment flow here —
 * subscriptions are granted manually by the server's admin. */
export function PremiumRequired() {
  const { t } = useTranslation();

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
        <Lock size={28} className="text-text-muted" />
        <p className="text-sm font-semibold text-text-primary">{t("premium.requiredTitle")}</p>
        <p className="max-w-sm text-sm text-text-muted">{t("premium.requiredBody")}</p>
      </CardContent>
    </Card>
  );
}
