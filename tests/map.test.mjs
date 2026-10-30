// The DualSense's map overlay (Omarchy shell plugin ormus.hypr-gamepad-map): its words and choices are
// Map.js, run here as the shell runs it; the QML, the manifest and hypr-gamepad must agree on the names
// that tie them together, and the map must stay visual only (no keyboard, no input region).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import vm from "node:vm";

const PLUGIN = new URL("../omarchy/ormus.hypr-gamepad-map/", import.meta.url);
const read = (name) => readFileSync(new URL(name, PLUGIN), "utf8");
const qml = read("PadMap.qml");
const manifest = JSON.parse(read("manifest.json"));
const M = vm.runInNewContext(`${read("Map.js").replace(/^\.pragma library\n/, "")}
({ kindPhrase, applies, labelFor, opensGroup, layerOrder })`);

test("where the map says the pad is", () => {
  assert.equal(M.kindPhrase("herdr"), "inside herdr");
  assert.equal(M.kindPhrase("browser"), "in the browser");
  assert.equal(M.kindPhrase("board"), "on the board");  // any board app, not one desk's
  assert.equal(M.kindPhrase("whatever"), "in this window");
});

test("a row is lit where its action works, dimmed elsewhere; list-likes count as lists", () => {
  assert.equal(M.applies({ kinds: ["*"] }, "browser"), true);
  assert.equal(M.applies({ kinds: ["board", "herdr"] }, "browser"), false);
  assert.equal(M.applies({ kinds: ["board", "herdr"] }, "herdr"), true);
  // what a Repeater hands QML: indexable, with a length, but not an Array
  const listLike = { 0: "board", 1: "herdr", length: 2 };
  assert.equal(M.applies({ kinds: listLike }, "browser"), false);
  assert.equal(M.applies({ kinds: listLike }, "herdr"), true);
  assert.equal(M.applies({}, "browser"), true);
});

test("a row speaks the window's own words when it has them", () => {
  const row = { label: "Previous herdr space; browser back", labels: { browser: "Back" } };
  assert.equal(M.labelFor(row, "browser"), "Back");
  assert.equal(M.labelFor(row, "herdr"), "Previous herdr space; browser back");
});

test("groups open once; the side in force comes first", () => {
  const rows = [{ group: "Buttons" }, { group: "Buttons" }, { group: "D-pad" }];
  assert.deepEqual(rows.map((_, i) => M.opensGroup(rows, i)), [true, false, true]);
  assert.deepEqual(Array.from(M.layerOrder("world")), ["world", "base"]);  // a copy: vm arrays are another realm's
  assert.deepEqual(Array.from(M.layerOrder("base")), ["base", "world"]);
});

test("names tie together: manifest, QML, IPC target, hypr-gamepad's events", () => {
  assert.equal(manifest.id, "ormus.hypr-gamepad-map");
  assert.deepEqual(manifest.kinds, ["overlay"]);
  assert.equal(manifest.keepLoaded, true);
  assert.equal(manifest.entryPoints.overlay, "PadMap.qml");
  assert.match(qml, /readonly property string pluginId: "ormus\.hypr-gamepad-map"/);
  assert.match(qml, /target: "ormus\.hypr-gamepad-map"/);
  assert.match(qml, /parts\[1\] === "show" && parts\.length === 4\) show\(parts\[2\], parts\[3\], false\)/);
  assert.match(qml, /parts\[1\] === "hide" && parts\.length === 2\) hide\(\)/);
  const pad = readFileSync(new URL("../hypr-gamepad", import.meta.url), "utf8");
  assert.match(pad, /MAP_ID = "ormus\.hypr-gamepad-map"/);
  assert.match(pad, /self\.send\(f"show \{kind\} \{layer\} \{int\(grouped\)\}"\)/);
});

test("visual only, and one gold: the side in force", () => {
  assert.match(qml, /WlrLayershell\.keyboardFocus: WlrKeyboardFocus\.None/);
  assert.match(qml, /mask: Region \{\}/);
  assert.equal((qml.match(/#FFD700/g) || []).length, 1);
  assert.match(qml, /color: side\.inForce \? root\.gold : Color\.popups\.text/);
  assert.doesNotMatch(qml, /Color\.popups\.border/, "the theme's popup border can be gold");
  assert.doesNotMatch(qml, /property string layer:/, "Item.layer is FINAL: overriding it fails the load");
});

test("the rows hypr-gamepad gives are the rows the QML reads", () => {
  const doc = JSON.parse(execFileSync("python3", [new URL("../hypr-gamepad", import.meta.url).pathname, "map", "--json"]));
  for (const side of ["base", "world"]) {
    assert.ok(doc.layers[side].length > 10);
    for (const row of doc.layers[side]) {
      for (const key of ["group", "glyph", "name", "label", "labels", "kinds"]) assert.ok(key in row, `${side} ${row.control} ${key}`);
    }
  }
  assert.ok("battery" in doc);
});

// Independent review, 2026-10-29: L1/R1 switch the tabs of a Hyprland group in any window, and do
// nothing in a terminal that is in no group; the map must say so.
test("a grouped window lights the group's rows, an ungrouped terminal does not", () => {
  const tab = { kinds: ["board", "browser", "group", "herdr"], label: "Previous tab",
                labels: { herdr: "Previous herdr tab", group: "Previous tab of the group" } };
  assert.equal(M.applies(tab, "other", true), true);
  assert.equal(M.applies(tab, "terminal", false), false);
  assert.equal(M.applies(tab, "herdr", false), true);
  assert.equal(M.labelFor(tab, "other", true), "Previous tab of the group");
  assert.equal(M.labelFor(tab, "herdr", true), "Previous herdr tab");   // herdr's own words win
  assert.match(qml, /parts\[1\] === "show" && parts\.length === 5\) show\(parts\[2\], parts\[3\], parts\[4\] === "1"\)/);
});

test("the battery sits on the title's line: title, phrase and battery are siblings", () => {
  assert.doesNotMatch(qml, /Row \{[^}]*id: title/s, "a Text in a Row cannot be another Row's anchor");
});

// 2026-10-29 s2: the map is about 1040 px high once it lists L3 and the right stick's text size, and
// it never shrank: on a laptop screen (1280x800 at scale 2) its title and last rows were off the
// screen (headless sway render), on DP-1 (1021 high) a few pixels at each edge.
const fitScale = vm.runInNewContext(`${read("Map.js").replace(/^\.pragma library\n/, "")}
typeof fitScale === "function" ? fitScale : null`);

test("the map shrinks to fit its screen and never grows", () => {
  assert.ok(fitScale, "Map.js has fitScale");
  assert.equal(fitScale(900, 1067, 20), 1);                // it fits: as drawn
  assert.equal(fitScale(1040, 800, 20), 760 / 1040);       // the laptop: the whole plate, 20 above and below
  assert.equal(fitScale(1040, 1021, 20), 981 / 1040);      // DP-1
  assert.equal(fitScale(0, 800, 20), 1);                   // nothing measured yet: as drawn
  assert.equal(fitScale(1040, 0, 20), 1);
});

test("the plate takes the fitting scale from its screen's height", () => {
  assert.match(qml, /scale:\s*MapLogic\.fitScale\(plate\.height,\s*panel\.height,\s*root\.pad\)/);
});
