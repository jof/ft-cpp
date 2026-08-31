#!/usr/bin/env node
// Replays the tap-a-control race against the real code in both panels:
// the front page (deploy/www/index.html) and the full form (demos/ftsched_ui.html).
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


// ---------------------------------------------------------------------------
// The full-form panel. Its held state is a pair of helpers rather than one
// flag -- a mode, and a switch per effect -- so they are exercised directly,
// and the wiring that feeds them is checked by reading the call sites.
// ---------------------------------------------------------------------------

const ui = fs.readFileSync(
  path.join(__dirname, "demos", "ftsched_ui.html"), "utf-8");

const ua = ui.lastIndexOf("/* ---- optimistic intent");
const ub = ui.lastIndexOf("/* ---- acknowledgement");
if (ua < 0 || ub < ua) { console.error("cannot find the intent block"); process.exit(2); }

console.log("");
let posted = [];
{
  // eslint-disable-next-line no-unused-vars
  const post = (op, extra) => { posted.push([op, extra]); };
  // Wrapped rather than eval'd bare: `let` inside an eval is scoped to that
  // eval, so the block has to hand its own bindings back out to be driven.
  const {settleGroup, settleEnabled, wantToggle, setWantGroup} =
    eval("(() => {" + ui.slice(ua, ub) + 
      "\n; return {settleGroup, settleEnabled, wantToggle," +
      " setWantGroup: (k, t) => { wantGroup = {key: k, since: t}; }};})()");

  NOW = 0;
  wantToggle("pigeon", false);
  check("a switch posts its toggle", JSON.stringify(posted.at(-1)) ===
        '["toggle",{"name":"pigeon","on":false}]');

  NOW = 80;                       // the queue is not drained yet
  check("a stale state does not flip the switch back",
        settleEnabled({name: "pigeon", enabled: true}) === false);
  check("an untouched effect is painted from the wall",
        settleEnabled({name: "lathe", enabled: true}) === true);

  NOW = 1000;
  check("the confirmed state is taken",
        settleEnabled({name: "pigeon", enabled: false}) === false);
  NOW = 1001;                     // and the hold is released, not sticky
  check("the wall wins again once confirmed",
        settleEnabled({name: "pigeon", enabled: true}) === true);

  NOW = 2000; wantToggle("dolly", true);
  NOW = 6500;
  check("a refused toggle lets go before long",
        settleEnabled({name: "dolly", enabled: false}) === false);

  NOW = 7000;
  setWantGroup("calm", NOW);
  NOW = 7080;
  check("a stale state does not drop the mode",
        settleGroup({group: "all"}) === "calm");
  NOW = 8000;
  check("the confirmed mode is taken", settleGroup({group: "calm"}) === "calm");
  NOW = 9000;
  check("another phone's mode wins once settled",
        settleGroup({group: "loud"}) === "loud");
}

// The helpers are only worth anything if the controls actually call them.
check("the switch is wired to the latch",
      /box\.addEventListener\("change", \(\) => wantToggle\(/.test(ui));
check("the mode button is wired to the latch",
      /wantGroup = \{key: b\.key, since: performance\.now\(\)\};/.test(ui));
check("the row is painted from the held state",
      /const on = settleEnabled\(e\);/.test(ui) &&
      /r\.box\.checked = on;/.test(ui));
check("the mode pills are painted from the held state",
      /const group = settleGroup\(s\);/.test(ui) &&
      /const active = group === p\.key;/.test(ui));

console.log(fail.length ? "\nFAILED: " + fail.length : "\nPASS");
process.exit(fail.length ? 1 : 0);
