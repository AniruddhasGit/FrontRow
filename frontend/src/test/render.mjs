// The render harness: node --test + Vite's own SSR loader + react-dom/server. No new dependency.
//   const { ListingScreen } = await load("/src/features/browse/ListingScreen.tsx");
//   const doc = render(ListingScreen, { seed: {...} });
//   all(doc, (e) => role(e) === "button").map((b) => name(b, doc));
//
// What it can assert: the markup React renders on the FIRST render - text, elements, roles, aria attributes,
// labels, tab stops by attribute. What it cannot: effects (react-dom/server runs none), events, layout, computed
// styles, focus movement. Screens take a `seed` prop (their first state) so the state an effect would have set
// can be rendered.
// ponytail: roles and names are computed from attributes by the small table below, not by a browser's
// accessibility engine - enough for presence/absence checks on this app's markup; a real browser (Playwright) is
// the upgrade path for the accessibility TREE, computed styles and focus.
import { after } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
let server = null;

/** ssrLoadModule a .ts/.tsx module by its root-relative path ("/src/..."), through the project's vite.config.ts. */
export async function load(path) {
  server ??= await createServer({
    root: ROOT, logLevel: "error", appType: "custom", server: { middlewareMode: true, hmr: false, watch: null, ws: false },
  });
  return server.ssrLoadModule(path);
}
after(() => server?.close());

/** A minimal `window` for the code that reads the address on first render (router, filters). */
export function atUrl(url) {
  const u = new URL(url, "http://frontrow.test");
  globalThis.window = {
    location: { pathname: u.pathname, search: u.search, href: u.href },
    history: { replaceState() {}, pushState() {} },
    addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
  };
}

export function markup(component, props = {}) {
  return renderToStaticMarkup(createElement(component, props));
}

export function render(component, props = {}) {
  return parse(markup(component, props));
}

// ---- a parser for react-dom/server's own output: well-formed, double-quoted attributes, escaped text ----
const VOID = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);
const ENTITY = { amp: "&", lt: "<", gt: ">", quot: '"', "#39": "'", "#x27": "'", nbsp: " " };
const unescape = (s) => s.replace(/&(#?\w+);/g, (m, e) => ENTITY[e] ?? m);

export function parse(html) {
  const root = { tag: "#root", attrs: {}, children: [], parent: null };
  let at = root;
  const re = /<(\/?)([a-zA-Z][\w-]*)((?:\s+[^\s=/>]+(?:="[^"]*")?)*)\s*(\/?)>|([^<]+)/g;
  for (let m; (m = re.exec(html)); ) {
    if (m[5] !== undefined) {
      at.children.push({ text: unescape(m[5]), parent: at });
      continue;
    }
    const tag = m[2].toLowerCase();
    if (m[1]) {
      if (at.tag !== tag) throw new Error(`unbalanced </${tag}> inside <${at.tag}>`);
      at = at.parent;
      continue;
    }
    const attrs = {};
    for (const a of m[3].matchAll(/([^\s=/>]+)(?:="([^"]*)")?/g)) attrs[a[1]] = a[2] === undefined ? "" : unescape(a[2]);
    const el = { tag, attrs, children: [], parent: at };
    at.children.push(el);
    if (!VOID.has(tag) && !m[4]) at = el;
  }
  return root;
}

/** Every element under `node` (document order) for which `pred(el)` holds. */
export function all(node, pred = () => true) {
  const out = [];
  const walk = (n) => {
    for (const c of n.children ?? []) {
      if (c.tag) {
        if (pred(c)) out.push(c);
        walk(c);
      }
    }
  };
  walk(node);
  return out;
}

export const byClass = (cls) => (e) => (e.attrs.class ?? "").split(/\s+/).includes(cls);

/** textContent. */
export function text(node) {
  if (node.text !== undefined) return node.text;
  return (node.children ?? []).map(text).join("");
}

const INPUT_ROLE = { checkbox: "checkbox", radio: "radio", button: "button", submit: "button", reset: "button", range: "slider", search: "searchbox" };
const LANDMARK_IN = new Set(["article", "aside", "main", "nav", "section"]);

/** The explicit role, else the HTML-AAM implicit role for the elements this app renders. */
export function role(el) {
  if (el.attrs.role) return el.attrs.role.split(/\s+/)[0];
  switch (el.tag) {
    case "button": return "button";
    case "a": return "href" in el.attrs ? "link" : null;
    case "input": return el.attrs.type === "hidden" ? null : (INPUT_ROLE[el.attrs.type] ?? "textbox");
    case "textarea": return "textbox";
    case "select": return "multiple" in el.attrs || Number(el.attrs.size) > 1 ? "listbox" : "combobox";
    case "nav": return "navigation";
    case "main": return "main";
    case "aside": return "complementary";
    case "ul": case "ol": return "list";
    case "li": return "listitem";
    case "h1": case "h2": case "h3": case "h4": case "h5": case "h6": return "heading";
    case "header": case "footer": {
      for (let p = el.parent; p; p = p.parent) if (LANDMARK_IN.has(p.tag)) return null;
      return el.tag === "header" ? "banner" : "contentinfo";
    }
    default: return null;
  }
}

export const CONTROL_ROLES = new Set([
  "button", "link", "checkbox", "radio", "textbox", "searchbox", "combobox", "listbox", "option", "slider", "spinbutton",
  "switch", "tab", "menuitem", "menuitemcheckbox", "menuitemradio", "gridcell",
]);

const visibleText = (n) => (n.text !== undefined ? n.text : n.attrs?.["aria-hidden"] === "true" ? "" : (n.children ?? []).map(visibleText).join(""));
const squash = (s) => s.replace(/\s+/g, " ").trim();

/** The accessible name: aria-labelledby, aria-label, a label (wrapping or for=), alt/title, then content. */
export function name(el, doc) {
  if (el.attrs["aria-labelledby"]) {
    return squash(el.attrs["aria-labelledby"].split(/\s+/).map((id) => all(doc, (e) => e.attrs.id === id).map(visibleText).join(" ")).join(" "));
  }
  if (el.attrs["aria-label"]) return squash(el.attrs["aria-label"]);
  if (["input", "select", "textarea"].includes(el.tag)) {
    const labels = [];
    for (let p = el.parent; p; p = p.parent) if (p.tag === "label") labels.push(p);
    if (el.attrs.id) labels.push(...all(doc, (e) => e.tag === "label" && e.attrs.for === el.attrs.id));
    // A wrapping label's own text, minus the control's (a select's options are not part of its label).
    const own = (n) => (n === el ? "" : n.text !== undefined ? n.text : n.tag === "select" || n.tag === "textarea" ? "" : (n.children ?? []).map(own).join(""));
    if (labels.length) return squash(labels.map(own).join(" "));
    return squash(el.attrs.title ?? el.attrs.placeholder ?? "");
  }
  if (el.tag === "img") return squash(el.attrs.alt ?? "");
  return squash(visibleText(el) || el.attrs.title || "");
}

/** Elements in the sequential focus order by attribute: natively focusable or tabindex >= 0, minus tabindex < 0
 *  and disabled. (This app sets no positive tabindex, so document order is the Tab order.) */
export function tabbable(node) {
  return all(node, (e) => {
    if ("disabled" in e.attrs) return false;
    if (e.attrs.tabindex !== undefined) return Number(e.attrs.tabindex) >= 0;
    return e.tag === "button" || e.tag === "select" || e.tag === "textarea" || (e.tag === "input" && e.attrs.type !== "hidden") || (e.tag === "a" && "href" in e.attrs);
  });
}
