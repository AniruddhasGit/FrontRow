// The app: the shell around whichever screen the path selects. Feature screens live in
// src/features/<feature>/ and register their paths in that feature's routes.tsx.
import { Layout } from "./layout";
import { Outlet, allRoutes } from "./router";

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
      <Outlet routes={allRoutes()} notFound={<NotFound />} />
    </Layout>
  );
}
