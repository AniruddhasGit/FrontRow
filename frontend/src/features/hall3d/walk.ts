// CR-014: the walk from the film page's corridor into the hall, and the lenses either side of it. Pure (three's maths
// only, no DOM, no WebGL), so node --test loads it.
//
// The route is hallN.json `enter`: eye/look waypoints from the corridor through the doorway to the all-seats view.
// Both curves are sampled at the SAME curve parameter, so the look stays with its waypoint (two separate arc-length
// samplings drift apart, and the view then turns early or late at the doorway). The time spent on each leg is its
// walk length plus its turn, so a leg that only turns on the spot still takes time instead of snapping round.
import { CatmullRomCurve3, Vector3 } from "three";

export type Pose = { eye: number[]; look: number[] };
export const WALK_MS = 3600; // the owner's brief: about 3-4 s from the press to the seats
const TURN_M = 1.6; // one radian of turning counts as this many metres of walking

/** Slow out of the corridor, slow onto the seats (a cubic ease in and out). */
export const walkEase = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2);

const v = (a: number[]) => new Vector3(a[0], a[1], a[2]);
const same = (a: number[], b: number[]) => a.every((n, i) => Math.abs(n - b[i]) < 1e-4);

/** The route that starts exactly at `from` (the corridor pose) and ends exactly at `to` (the all-seats view): the file's
 *  route, with the ends added when it does not already start and end there. */
export function walkRoute(enter: Pose[], from: Pose, to: Pose): Pose[] {
  const r = [...enter];
  if (!r.length || !same(r[0].eye, from.eye) || !same(r[0].look, from.look)) r.unshift(from);
  const last = r[r.length - 1];
  if (!same(last.eye, to.eye) || !same(last.look, to.look)) r.push(to);
  return r;
}

export type Walker = (e: number) => { eye: Vector3; look: Vector3 };

/** A sampler over the route: e in [0, 1] (already eased) to the camera's eye and look point. */
export function walker(route: Pose[]): Walker {
  if (route.length < 2) {
    const only = route[0] ?? { eye: [0, 0, 0], look: [0, 0, -1] };
    return () => ({ eye: v(only.eye), look: v(only.look) });
  }
  const eyes = new CatmullRomCurve3(route.map((p) => v(p.eye)), false, "centripetal");
  const looks = new CatmullRomCurve3(route.map((p) => v(p.look)), false, "centripetal");
  const dir = (p: Pose) => v(p.look).sub(v(p.eye)).normalize();
  const legs = route.slice(1).map((p, i) => v(p.eye).distanceTo(v(route[i].eye)) + TURN_M * dir(p).angleTo(dir(route[i])) + 1e-6);
  const total = legs.reduce((a, b) => a + b, 0);
  const n = legs.length;
  return (e) => {
    let at = Math.min(1, Math.max(0, e)) * total;
    let i = 0;
    while (i < n - 1 && at > legs[i]) at -= legs[i++];
    const t = (i + Math.min(1, at / legs[i])) / n;
    return { eye: eyes.getPoint(t), look: looks.getPoint(t) };
  };
}

const deg = (r: number) => (r * 180) / Math.PI;
/** The stand-in picture's lens: a square Cycles render at 32 mm on a 36 mm sensor (58.72 deg), shown `object-fit: cover`
 *  and centred. The live camera in a box of this aspect sees exactly what the picture shows there. */
export const PICTURE_FOV = 58.72;
export function corridorFov(aspect: number): number {
  return aspect >= 1 ? deg(2 * Math.atan(Math.tan((PICTURE_FOV * Math.PI) / 360) / aspect)) : PICTURE_FOV;
}

/** The hall's own lens (the entrance clip's: 90 deg across at 16:9; a wider box crops top and bottom; a phone held
 *  upright as wide as a 95 deg tall lens allows). Unchanged from CR-003. */
export function hallFov(aspect: number): number {
  const d = deg(2 * Math.atan(1 / aspect));
  return aspect >= 16 / 9 ? d : aspect >= 1 ? 58.72 : Math.min(95, d);
}

/** The part of the canvas that is seen: the seat page's panel covers the canvas's right (or, on a phone, its bottom),
 *  and the picture is framed for what is left. The canvas then renders that frame and runs on under the panel. */
export type Cover = { right: number; bottom: number };
export const NO_COVER: Cover = { right: 0, bottom: 0 };
export function seen(width: number, height: number, cover: Cover): { w: number; h: number } {
  return { w: Math.max(1, width - Math.max(0, cover.right)), h: Math.max(1, height - Math.max(0, cover.bottom)) };
}
