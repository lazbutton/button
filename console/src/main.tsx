import "@radix-ui/themes/styles.css";
import { Theme } from "@radix-ui/themes";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { BrandContext } from "./lib/BrandContext";
import { AppearanceProvider, useAppearance } from "./lib/Appearance";
import { applyTheme, label, loadBrand, paletteFor, readAppearance, type Brand } from "./lib/brand";
import "./styles.css";
import "./styles/tokens.css";
import "./styles/ui.css";
import "./styles/shell.css";
import "./styles/desk.css";
import "./styles/antenne.css";
import "./styles/pupitre.css";
import "./styles/player.css";

applyTheme(paletteFor(readAppearance()));

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
  const [brand, setBrand] = useState<Brand | null>(null);
  useEffect(() => {
    loadBrand().then((data) => {
      applyTheme(paletteFor(readAppearance(), data.theme));
      const consoleTitle = label(data, "console", "title") || "Horloges";
      document.title = `${data.suite.name} — ${consoleTitle}`;
      setBrand(data);
    });
  }, []);
  if (!brand) return null;
  return (
    <BrandContext.Provider value={brand}>
      <AppearanceProvider brandTheme={brand.theme}>
        <ThemedApp />
      </AppearanceProvider>
    </BrandContext.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
