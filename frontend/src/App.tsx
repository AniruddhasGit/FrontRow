// The app: the shell around whichever screen the path selects. Feature screens live in
// src/features/<feature>/ and register their paths in that feature's routes.tsx.
import { Layout } from "./layout";
import { Outlet, allRoutes, type AppRoute } from "./router";

const home: AppRoute = {
  path: "/",
  // Browsing (the movie list) arrives with the browse lane, Phase 3.
  render: () => (
    <>
      <p className="eyebrow">FrontRow</p>
      <h1>Now showing</h1>
      <p className="lede">The movie list arrives in Phase 3.</p>
    </>
  ),
};

function NotFound() {
  return (
    <>
      <h1>That page does not exist.</h1>
    </>
  );
}

export function App() {
  return (
    <Layout>
      <Outlet routes={allRoutes(home)} notFound={<NotFound />} />
    </Layout>
  );
}
