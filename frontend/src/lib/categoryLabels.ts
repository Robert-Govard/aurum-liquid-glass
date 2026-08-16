import { t, type TranslationKey } from "@/lib/i18n";

// Maps the exact seeded English category name (backend/app/db/seed.py) to
// its translation key. There's no category-management UI yet, so every
// category currently in the database is one of these — anything that
// doesn't match (a renamed default, or a future custom category) falls
// through unchanged.
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
  "Other Income": "category.otherIncome",
};

export function translateCategoryName(name: string): string {
  const key = DEFAULT_CATEGORY_KEYS[name];
  return key ? t(key) : name;
}
