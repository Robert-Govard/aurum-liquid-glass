import { useState } from "react";

export function useLocalStorageState(key: string, initial: boolean) {
  const [value, setValue] = useState<boolean>(() => {
    const stored = localStorage.getItem(key);
    return stored === null ? initial : stored === "true";
  });

  const update = (next: boolean) => {
    setValue(next);
    localStorage.setItem(key, String(next));
  };

  return [value, update] as const;
}
