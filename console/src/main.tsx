import "@radix-ui/themes/styles.css";
import { Theme } from "@radix-ui/themes";
import { StrictMode, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { withStation } from "./api/station";
import type { PublicStation } from "./api/types";
import { BrandContext, StationContext } from "./lib/BrandContext";
import { AppearanceProvider, useAppearance } from "./lib/Appearance";
import { applyTheme, loadBrand, loadStation, paletteFor, readAppearance, type LoadedBrand } from "./lib/brand";
import "./styles.css";
import "./styles/tokens.css";
import "./styles/ui.css";
import "./styles/shell.css";
import "./styles/desk.css";
import "./styles/antenne.css";
import "./styles/topbar.css";

applyTheme(paletteFor(readAppearance()));

/** Un moteur qui ne répondait pas au chargement : la console relit ses réglages à ce rythme. */
const STATION_RETRY_MS = 15_000;

function ThemedApp() {
  const { appearance } = useAppearance();
  return (
    <Theme
      appearance={appearance}
      accentColor="gray"
      grayColor="gray"
      radius="medium"
      scaling="100%"
      panelBackground="solid"
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Theme>
  );
}

function Root() {
  const [loaded, setLoaded] = useState<LoadedBrand | null>(null);
  useEffect(() => {
    loadBrand().then((data) => {
      applyTheme(paletteFor(readAppearance(), data.file.theme));
      setLoaded(data);
    });
  }, []);
  // Sans réponse du moteur, la console garde brand.json et relit, jusqu'à une réponse.
  useEffect(() => {
    if (!loaded?.retry) return;
    const timer = window.setTimeout(() => {
      void loadStation().then((read) => setLoaded((current) => (current ? { ...current, ...read } : current)));
    }, STATION_RETRY_MS);
    return () => window.clearTimeout(timer);
  }, [loaded]);
  // Les réglages du moteur d'abord, brand.json en repli.
  const brand = useMemo(() => (loaded ? withStation(loaded.file, loaded.station) : null), [loaded]);
  const applyStation = useCallback((station: PublicStation) => {
    setLoaded((current) => (current ? { ...current, station, retry: false } : current));
  }, []);
  const imageBrand = loaded?.file;
  const binding = useMemo(() => (imageBrand ? { imageBrand, applyStation } : null), [imageBrand, applyStation]);
  if (!brand || !binding) return null;
  return (
    <BrandContext.Provider value={brand}>
      <StationContext.Provider value={binding}>
        <AppearanceProvider brandTheme={brand.theme}>
          <ThemedApp />
        </AppearanceProvider>
      </StationContext.Provider>
    </BrandContext.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
