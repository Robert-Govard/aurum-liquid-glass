import {
  Banknote,
  Bitcoin,
  Briefcase,
  Building2,
  Car,
  Clapperboard,
  Gem,
  Gift,
  HeartPulse,
  Home,
  MoreHorizontal,
  Package,
  PlusCircle,
  Repeat,
  ShoppingBag,
  ShoppingBasket,
  TrendingUp,
  Utensils,
  Wallet,
  type LucideIcon,
} from "lucide-react";

// Maps the backend's plain-string icon keys (Category.icon) to a concrete
// lucide component. New categories fall back to a generic wallet glyph so an
// unmapped icon key never breaks rendering.
const ICON_MAP: Record<string, LucideIcon> = {
  home: Home,
  "shopping-basket": ShoppingBasket,
  utensils: Utensils,
  car: Car,
  "heart-pulse": HeartPulse,
  "shopping-bag": ShoppingBag,
  clapperboard: Clapperboard,
  repeat: Repeat,
  banknote: Banknote,
  briefcase: Briefcase,
  "trending-up": TrendingUp,
  gift: Gift,
  "plus-circle": PlusCircle,
  "more-horizontal": MoreHorizontal,
  wallet: Wallet,
  bitcoin: Bitcoin,
  "building-2": Building2,
  package: Package,
  gem: Gem,
};

export function getCategoryIcon(icon: string | null | undefined): LucideIcon {
  if (!icon) return Wallet;
  return ICON_MAP[icon] ?? Wallet;
}
