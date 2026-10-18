// The poster box (COMPONENTS.md §3): 2:3, its space reserved before the image arrives. When the image does not
// load - no poster, an object missing from the bucket, or the redirect not yet served - the img is REMOVED and the
// box draws the perforation motif with the title inside it. No icon, no words added, no broken-image glyph.
import { useState } from "react";

export function Poster({ src, title }: { src: string; title: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="fr-poster" data-empty={failed ? "" : undefined}>
      {failed ? <span className="fr-poster-title">{title}</span> : <img src={src} alt="" onError={() => setFailed(true)} />}
    </div>
  );
}
