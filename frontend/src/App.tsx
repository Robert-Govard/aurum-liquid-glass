import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { MobileTabBar } from "@/components/layout/MobileTabBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useEdgeSwipeBack } from "@/hooks/useEdgeSwipeBack";
import { useIsMobileViewport } from "@/hooks/useIsMobileViewport";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { useAppSettings } from "@/hooks/useSettings";
import { setCurrency } from "@/lib/i18n";
import { AccountsPage } from "@/pages/AccountsPage";
import { AdminPage } from "@/pages/AdminPage";
import { AdvicePage } from "@/pages/AdvicePage";
import { BudgetPage } from "@/pages/BudgetPage";
import { CashFlowPage } from "@/pages/CashFlowPage";
import { CategoriesPage } from "@/pages/CategoriesPage";
import { CryptoPage } from "@/pages/CryptoPage";
import { CsvImportPage } from "@/pages/CsvImportPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { GoalsPage } from "@/pages/GoalsPage";
import { NetWorthPage } from "@/pages/NetWorthPage";
import { RecurringPage } from "@/pages/RecurringPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { RoiPage } from "@/pages/RoiPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TransactionsPage } from "@/pages/TransactionsPage";

export default function App() {
  const [collapsed, setCollapsed] = useLocalStorageState("aurum:sidebar-collapsed", false);
  useEdgeSwipeBack(useIsMobileViewport());

  // Primary currency is server-persisted, unlike language — sync the
  // client-side reactive mirror (lib/i18n's getCurrency/formatCurrency)
  // once the setting loads, so it's not stuck on the "USD" fallback default.
  const { data: settings } = useAppSettings();
  useEffect(() => {
    if (settings) setCurrency(settings.currency);
  }, [settings]);

  return (
    <div className="flex min-h-screen">
      {/* Амбиентная подложка, на которой «преломляется» стеклянный хром
          (Sidebar/Topbar/Dialog) — на плоском surface-0 полупрозрачные
          поверхности выглядели бы просто серыми. Fixed + отрицательный
          z-index: слой позади всего контента приложения, но поверх обычного
          фона <body> из index.css. Цвета — уже существующие токены (золото
          логотипа ~= series-4, один акцентный series-1), а не новые
          хардкод-значения. Три пятна, а не одно: Sidebar тянется на всю
          высоту экрана, а Topbar — на всю ширину, так что нужен цвет и
          сверху, и снизу, и справа — иначе блюрить там нечего и стекло не
          видно почти нигде (обнаружено при визуальной проверке). blur-2xl
          вместо blur-3xl и более высокая непрозрачность — иначе цвет
          растворяется до полной незаметности ещё до того, как дойдёт до
          самих панелей. */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -left-32 -top-32 h-[28rem] w-[28rem] rounded-full bg-series-4/16 blur-2xl" />
        <div className="absolute -top-32 right-0 h-[28rem] w-[28rem] rounded-full bg-series-1/16 blur-2xl" />
        <div className="absolute -bottom-32 -left-32 h-[28rem] w-[28rem] rounded-full bg-series-1/14 blur-2xl" />
      </div>
      <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed(!collapsed)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="mx-auto w-full max-w-6xl px-4 pt-5 pb-[calc(4.5rem+var(--safe-area-bottom))] sm:px-6 sm:pt-6 lg:px-8 lg:pb-6">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/net-worth" element={<NetWorthPage />} />
            <Route path="/crypto" element={<CryptoPage />} />
            <Route path="/roi" element={<RoiPage />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/categories" element={<CategoriesPage />} />
            <Route path="/cash-flow" element={<CashFlowPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/transactions/import" element={<CsvImportPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/budget" element={<BudgetPage />} />
            <Route path="/advice" element={<AdvicePage />} />
            <Route path="/goals" element={<GoalsPage />} />
            <Route path="/recurring" element={<RecurringPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/admin" element={<AdminPage />} />
            {/* Пользователь попадает сюда по ссылке из письма, пока ещё нет
                сессии — LoginGate в этом случае рендерит VerifyEmailScreen
                напрямую. Но verifyEmail() внутри него синхронно обновляет
                сессию, LoginGate тут же переключается на этот <App/>, а URL
                в адресной строке остаётся "/verify-email" — без этого
                маршрута он не совпадёт ни с одним <Route> выше и контент
                останется пустым. Редиректим на главную. */}
            <Route path="/verify-email" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      <MobileTabBar />
    </div>
  );
}
