#!/usr/bin/env node
// Replays the tap-a-mode race against the real code in deploy/www/index.html.
//
// The panel polls once a second and post() refreshes again straight after the
// command goes out -- before the scheduler has drained its queue, so that
// reply still names the old group. Painting it back used to take the tick out
// from under the finger and put it back a second later, which reads as the
// wall ignoring you. The mode block is pulled out of the page and run here
// against a stub DOM whose activeElement is null throughout, which is what a
// tap on a label gives you on iOS -- the case the old focus guard missed.
//
// Usage: node test-panel-modes.js

const fs = require("fs");
const path = require("path");

const page = fs.readFileSync(
  path.join(__dirname, "deploy", "www", "index.html"), "utf-8");
const a = page.lastIndexOf("/* ---- the modes");
const b = page.lastIndexOf("/* ---- the wall");
if (a < 0 || b < a) { console.error("cannot find the mode block"); process.exit(2); }
const modeCode = page.slice(a, b);

let NOW = 0;
global.performance = {now: () => NOW};
const mkEl = (tag) => ({
  tag, className: "", textContent: "", checked: false, type: "", name: "",
  value: "", hidden: false, children: [], listeners: {},
  addEventListener(ev, fn) { (this.listeners[ev] ||= []).push(fn); },
  append(...c) { this.children.push(...c); },
});
const els = {};
global.document = {
  createElement: mkEl,
  activeElement: null,            // a tap on a label focuses nothing on iOS
  getElementById: (id) => (els[id] ||= mkEl("div")),
  querySelectorAll: () => [],
};

const $ = document.getElementById;
const posts = [];
const post = (op, extra) => { posts.push([op, extra]); };
const toast = () => {};
let groups = [], state = null, modeInputs = new Map();

eval(modeCode);                   // buildModes / paintModes / wantGroup

buildModes([{key: "all", label: "Everything", count: 20},
            {key: "calm", label: "Calm", count: 6},
            {key: "loud", label: "Loud", count: 8}]);
const on = (k) => modeInputs.get(k).checked;
const tap = (k) => {
  for (const [key, i] of modeInputs) i.checked = (key === k);
  modeInputs.get(k).listeners.change[0]();
};

const fail = [];
const check = (what, cond) => {
  console.log((cond ? "ok   " : "FAIL ") + what);
  if (!cond) fail.push(what);
};

paintModes({group: "all"});
check("starts on the group the wall reports", on("all") && !on("calm"));

tap("calm");
check("the tap is posted", JSON.stringify(posts.at(-1)) ===
      '["select",{"group":"calm"}]');

NOW = 80;                         // the refresh post() fires, queue undrained
paintModes({group: "all"});
check("a stale state does not steal the tick", on("calm") && !on("all"));

NOW = 1000;
paintModes({group: "calm"});
check("the confirmed state keeps it", on("calm"));

NOW = 2000;                       // somebody else's phone, or a cue
paintModes({group: "loud"});
check("the wall wins once we are settled", on("loud") && !on("calm"));

NOW = 3000; tap("calm");          // a select the scheduler refuses
NOW = 4000; paintModes({group: "loud"});
check("a refused select is still held a second later", on("calm"));
NOW = 7500; paintModes({group: "loud"});
check("a refused select lets go before long", on("loud") && !on("calm"));

console.log(fail.length ? "\nFAILED: " + fail.length : "\nPASS");
process.exit(fail.length ? 1 : 0);
