// The confirm response, handed from the checkout to the confirmation page for ONE render (P-TKT-03). In memory only:
// it does not survive a page load, which is exactly the rule - a reload renders the later-visit state.
let handed: string | null = null;

export function handOver(reference: string): void {
  handed = reference;
}

/** True once, for the reference the checkout just confirmed; false on every later visit. */
export function takeHandOver(reference: string): boolean {
  const mine = handed === reference;
  handed = null;
  return mine;
}
