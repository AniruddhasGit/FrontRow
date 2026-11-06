import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Self-hosted web fonts (FR-ADR-074 4): Vite bundles the woff2 files, so no request leaves for a font CDN.
import "@fontsource/inter-tight/400.css";
import "@fontsource/inter-tight/500.css";
import "@fontsource/inter-tight/700.css";
import "@fontsource/inter-tight/800.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/700.css";
import "./styles/tokens.css";
import "./styles/app.css";
import { App } from "./App";
import "./styles/premium.css"; // after App, so it lands after every feature stylesheet

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
