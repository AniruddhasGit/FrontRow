// CR-008 T14 (state-machine review #15): an admin form sends at most one request at a time. A double click used to
// send two; the server refused the second (overlap, unique name, version), so the admin saw an error after a success.
import { useRef, useState, type FormEvent } from "react";

export function useOnce() {
  const running = useRef(false); // a ref, not state: the second click can land before the re-render disables the button
  const [busy, setBusy] = useState(false);
  const guard = (fn: (e: FormEvent) => Promise<void>) => async (e: FormEvent) => {
    e.preventDefault();
    if (running.current) return;
    running.current = true;
    setBusy(true);
    try {
      await fn(e);
    } finally {
      running.current = false;
      setBusy(false);
    }
  };
  return { busy, guard };
}
