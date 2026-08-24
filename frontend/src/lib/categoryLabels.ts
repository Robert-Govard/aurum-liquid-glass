import { t, type TranslationKey } from "@/lib/i18n";

// Maps the exact seeded English category name (backend/app/db/seed.py) to
// its translation key, so the fixed default set reads in the user's chosen
// language regardless of what the DB literally stores. Categories created
// through the category-management UI (CategoriesPage) aren't in this map —
// their name is whatever the user typed and is shown as-is.
const DEFAULT_CATEGORY_KEYS: Record<string, TranslationKey> = {
  "Housing & Utilities": "category.housingUtilities",
  Groceries: "category.groceries",
  "Dining Out": "category.diningOut",
  Transportation: "category.transportation",
  "Health & Fitness": "category.healthFitness",
  Shopping: "category.shopping",
  Entertainment: "category.entertainment",
  Subscriptions: "category.subscriptions",
  Salary: "category.salary",
  Freelance: "category.freelance",
  Investments: "category.investments",
  Gifts: "category.gifts",
  "Business Income": "category.businessIncome",
  "Rental Income": "category.rentalIncome",
  Benefits: "category.benefits",
  "Item Sales": "category.itemSales",
  "Other Income": "category.otherIncome",
};

export function translateCategoryName(name: string): string {
  const key = DEFAULT_CATEGORY_KEYS[name];
  return key ? t(key) : name;
}
