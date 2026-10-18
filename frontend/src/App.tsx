// Phase 1 (SRC-002 §12.2): a served page proving the static container works. Nothing else - no
// movie list, no sign-in, no API call. Browsing arrives in Phase 3.
export function App() {
  return (
    <main className="shell">
      <p className="eyebrow">FrontRow</p>
      <h1>The skeleton is running.</h1>
      <p className="lede">
        This page is static files served by a small nginx container. There is nothing to book yet:
        Phase 1 exists so the deployment pipeline can be learned against something trivial.
      </p>
      <dl className="facts">
        <div>
          <dt>Frontend</dt>
          <dd>static, served by nginx</dd>
        </div>
        <div>
          <dt>API liveness</dt>
          <dd>
            <code>/health/live</code>
          </dd>
        </div>
        <div>
          <dt>API readiness</dt>
          <dd>
            <code>/health/ready</code>
          </dd>
        </div>
      </dl>
    </main>
  );
}
