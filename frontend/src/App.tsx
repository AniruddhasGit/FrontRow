// The app: the shell around whichever screen the path selects. Feature screens live in
// src/features/<feature>/ and register their paths in that feature's routes.tsx.
import { HallHost } from "./features/hall3d/host";
import { Shell } from "./Shell";
import { Link, Outlet, allRoutes } from "./router";

// Never a dead end: the way back to what is showing (ui-design redesign pass, 2026-11-22).
function NotFound() {
  return (
    <section className="fr-notfound">
      <h1>That page does not exist.</h1>
      <p>The address may be mistyped, or the page has moved.</p>
      <Link to="/films" className="fr-action">See what is showing</Link>
    </section>
  );
}

export function App() {
  return (
    // CR-014: the one live 3D hall, above the pages, so it outlives a page change (film page -> seat page and back)
    <HallHost>
      <Shell>
        <Outlet routes={allRoutes()} notFound={<NotFound />} />
      </Shell>
    </HallHost>
  );
}
