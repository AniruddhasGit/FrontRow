// CR-010 L1: each live seat lit by the light Blender's Cycles saw at that seat (hall_probes.py). Pure: no three.js
// runtime, so node --test loads it. Two probes per seat (LO near the cushion, HI at the top of the back), each 9 RGB
// spherical-harmonic coefficients already convolved with the cosine lobe and divided by pi: evaluated at a world
// normal they give E(n)/pi, the radiance a white matte surface facing n sends back (scene-linear, the bake's units).

/** One seat's probes as hallN.json stores them: y = the two probe heights (three.js metres), lo/hi = 27 floats each. */
export interface SeatSH { y: number[]; lo: number[]; hi: number[] }

/** Texels per seat in the lookup texture: 9 LO coefficients, 9 HI coefficients, then (yLo, yHi, 0, 0). */
export const SH_TEXELS = 19;

/** One row of RGBA float texels per instance, in instance order (row = gl_InstanceID). A seat with no probes gets a
 *  dim neutral fill, so a stale file never draws a black seat. */
export function packSH(seats: (SeatSH | undefined)[]): Float32Array {
  const out = new Float32Array(seats.length * SH_TEXELS * 4);
  seats.forEach((s, i) => {
    const row = i * SH_TEXELS * 4;
    for (let k = 0; k < 9; k++) {
      for (let c = 0; c < 3; c++) {
        out[row + k * 4 + c] = s ? s.lo[k * 3 + c] : k === 0 ? 0.05 : 0;
        out[row + (9 + k) * 4 + c] = s ? s.hi[k * 3 + c] : k === 0 ? 0.05 : 0;
      }
    }
    out[row + 18 * 4] = s ? s.y[0] : 0;
    out[row + 18 * 4 + 1] = s ? s.y[1] : 1;
  });
  return out;
}

const BASIS = (x: number, y: number, z: number) => [
  0.282095, 0.488603 * y, 0.488603 * z, 0.488603 * x, 1.092548 * x * y, 1.092548 * y * z, 0.315392 * (3 * z * z - 1),
  1.092548 * x * z, 0.546274 * (x * x - y * y),
];

/** E(n)/pi for 27 coefficients at unit normal n (the shader's sum, for tests and checks). */
export function evalSH(c: number[], n: number[]): [number, number, number] {
  const b = BASIS(n[0], n[1], n[2]);
  const out: [number, number, number] = [0, 0, 0];
  for (let k = 0; k < 9; k++) for (let ch = 0; ch < 3; ch++) out[ch] += c[k * 3 + ch] * b[k];
  return out;
}

/** The seat's light at world height y: LO below its probe, HI above, linear between (the shader's mix). */
export function seatIrradiance(s: SeatSH, n: number[], y: number): [number, number, number] {
  const t = Math.min(1, Math.max(0, (y - s.y[0]) / (s.y[1] - s.y[0])));
  const a = evalSH(s.lo, n), b = evalSH(s.hi, n);
  return [0, 1, 2].map((i) => Math.max(0, a[i] + (b[i] - a[i]) * t)) as [number, number, number];
}

/** The bake's look, for the seats: hall_bake.py saves AgX (Base Contrast) at exposure +0.4, and the site draws the
 *  room at x ROOM_GAIN. Seats lit in the bake's units go through the same curve, so they sit in the room as it does. */
export const EXPOSURE = 2 ** 0.4;

export const SH_VERT_PARS = "flat varying int vSeat;\nvarying vec3 vRoomW;\n";
export const SH_VERT = `#include <project_vertex>
  vec4 seatW = vec4(transformed, 1.0);
  #ifdef USE_INSTANCING
    seatW = instanceMatrix * seatW;
  #endif
  vRoomW = (modelMatrix * seatW).xyz;
  vSeat = gl_InstanceID;`;
export const SH_FRAG_PARS = `uniform highp sampler2D uSH; uniform float uSeatGain;
flat varying int vSeat;
vec3 seatSH(int base, vec3 n) {
  vec3 c[9];
  for (int k = 0; k < 9; k++) c[k] = texelFetch(uSH, ivec2(base + k, vSeat), 0).rgb;
  return c[0] * 0.282095 + 0.488603 * (c[1] * n.y + c[2] * n.z + c[3] * n.x)
    + 1.092548 * (c[4] * n.x * n.y + c[5] * n.y * n.z + c[7] * n.x * n.z)
    + c[6] * 0.315392 * (3.0 * n.z * n.z - 1.0) + c[8] * 0.546274 * (n.x * n.x - n.y * n.y);
}
`;
/** (The fragment also needs `varying vec3 vRoomW;`, which HallScene's glow chunk declares.)
 *  Replaces the diffuse light the environment map would give (one point, mid-hall) with the seat's own probes; the
 *  environment still gives the reflections. */
export const SH_FRAG = `#include <lights_fragment_maps>
  {
    vec3 seatN = transformNormalByInverseViewMatrix(geometryNormal, viewMatrix);
    vec4 seatY = texelFetch(uSH, ivec2(18, vSeat), 0);
    float seatT = clamp((vRoomW.y - seatY.x) / max(1e-3, seatY.y - seatY.x), 0.0, 1.0);
    iblIrradiance = PI * uSeatGain * max(vec3(0.0), mix(seatSH(0, seatN), seatSH(9, seatN), seatT));
  }`;
