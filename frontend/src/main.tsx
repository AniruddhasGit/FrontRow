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
import { Wake } from "./features/wake/Wake";
import "./styles/premium.css"; // after App, so it lands after every feature stylesheet
import "./styles/immersive.css"; // CR-004: edge to edge, after premium
import "./styles/buttons.css"; // one button system for the whole site, last

// The first render waits for the faces it uses (2026-11-23: a font that swaps in after the text is laid out reflows
// every line on the page), capped so a slow font costs at most FONTS_MS of blank page; past that it swaps in as before.
const FONTS_MS = 800;
const faces = ["400 1em 'Inter Tight'", "700 1em 'Inter Tight'", "800 1em 'Inter Tight'", "400 1em 'JetBrains Mono'"];
void Promise.race([
  Promise.all(faces.map((f) => document.fonts.load(f))).catch(() => null),
  new Promise((done) => setTimeout(done, FONTS_MS)),
]).then(() => createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Wake>
      <App />
    </Wake>
  </StrictMode>,
));
