import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  applyTheme,
  paletteFor,
  readAppearanceChoice,
  resolveAppearance,
  systemAppearance,
  writeAppearance,
  type Appearance,
  type AppearanceChoice,
  type BrandTheme,
} from "./brand";

/** Mêmes libellés dans Mon compte et dans le menu du compte. */
export const APPEARANCE_OPTIONS: { id: AppearanceChoice; label: string }[] = [
  { id: "system", label: "Machine" },
  { id: "light", label: "Clair" },
  { id: "dark", label: "Sombre" },
];

type AppearanceValue = {
  appearance: Appearance;
  choice: AppearanceChoice;
  setChoice: (next: AppearanceChoice) => void;
};

const AppearanceContext = createContext<AppearanceValue | null>(null);

export function AppearanceProvider({
  brandTheme,
  children,
}: {
  brandTheme?: BrandTheme;
  children: ReactNode;
}) {
  const [choice, setChoiceState] = useState<AppearanceChoice>(() => readAppearanceChoice());
  const [appearance, setAppearanceState] = useState<Appearance>(() => resolveAppearance(choice));

  useEffect(() => {
    if (choice !== "system") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const next = systemAppearance();
      applyTheme(paletteFor(next, brandTheme));
      setAppearanceState(next);
    };
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [brandTheme, choice]);

  const value = useMemo<AppearanceValue>(() => {
    const setChoice = (next: AppearanceChoice) => {
      writeAppearance(next);
      const resolved = resolveAppearance(next);
      applyTheme(paletteFor(resolved, brandTheme));
      setChoiceState(next);
      setAppearanceState(resolved);
    };
    return { appearance, choice, setChoice };
  }, [appearance, brandTheme, choice]);

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance(): AppearanceValue {
  const value = useContext(AppearanceContext);
  if (!value) throw new Error("useAppearance hors AppearanceProvider");
  return value;
}

