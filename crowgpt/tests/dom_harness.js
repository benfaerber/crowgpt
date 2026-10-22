// A DOM stub strict enough to catch the bugs a real browser found.
//
// The media element is the point. A real one starts an ASYNCHRONOUS load when
// src is assigned, throws InvalidStateError if you seek before it is ready, and
// rejects play() if a load is still in flight. A permissive stub reports every
// broken page as working, which is how a page shipped twice with dead buttons.

function makeElement(tag) {
  return {
    tagName: (tag || "div").toUpperCase(),
    children: [], _listeners: {}, _attrs: {}, style: {},
    classList: { toggle() {}, add() {}, remove() {} },
    set className(v) { this._cls = v; }, get className() { return this._cls || ""; },
    set textContent(v) { this._text = v; }, get textContent() { return this._text || ""; },
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
    append(...kids) { this.children.push(...kids); },
    replaceWith() {}, remove() {}, scrollIntoView() {}, select() {},
    prepend(...kids) { this.children.unshift(...kids); },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    click() {
      global.IN_GESTURE = true;                  // only for the synchronous turn
      try { (this._listeners.click || []).forEach(fn => fn({ preventDefault() {} })); }
      finally { global.IN_GESTURE = false; }
    },
    getContext() {
      return { scale() {}, clearRect() {}, fillRect() {}, set fillStyle(v) {} };
    },
  };
}

global.PLAYED = [];
global.ERRORS = [];

// USER ACTIVATION. A browser only permits play() from inside the synchronous
// turn of a user gesture. Deferring it to a canplay handler leaves that window
// and the call is rejected as autoplay — silently, if the promise is caught.
// The stub did not model this, so it certified a page that made no sound.
global.IN_GESTURE = false;

global.Audio = class {
  constructor(src) {
    this._src = src || "";
    this.readyState = src ? 4 : 0;
    this.paused = true; this.duration = 1; this._cur = 0; this._l = {};
  }
  addEventListener(type, fn, opts) {
    (this._l[type] = this._l[type] || []).push({ fn, once: opts && opts.once });
  }
  _emit(type) {
    const hooks = (this._l[type] || []).slice();
    this._l[type] = (this._l[type] || []).filter(h => !h.once);
    hooks.forEach(h => h.fn());
  }
  set src(v) {
    this._src = v;
    this.readyState = 0;                       // a load is now in flight
    setTimeout(() => { this.readyState = 4; this._emit("canplay"); }, 0);
  }
  get src() { return this._src; }
  set currentTime(v) {
    if (this.readyState === 0) throw new Error("InvalidStateError: seek before load");
    this._cur = v;
  }
  get currentTime() { return this._cur; }
  load() {}
  pause() { this.paused = true; }
  play() {
    // Playing before the load finishes is FINE — the browser queues it and
    // starts when data arrives. The stub used to reject here, which is what
    // pushed the fix toward waiting for canplay and out of the gesture window.
    if (!IN_GESTURE) {
      ERRORS.push("NotAllowedError: play() outside a user gesture");
      return Promise.reject(new Error("NotAllowedError: play() outside a user gesture"));
    }
    this.paused = false;
    PLAYED.push(this._src);
    return Promise.resolve();
  }
};

global.document = {
  _byId: {},
  _bySel: {},
  getElementById(id) { return (this._byId[id] = this._byId[id] || makeElement("div")); },
  createElement: makeElement,
  querySelector(sel) { return (this._bySel[sel] = this._bySel[sel] || makeElement("div")); },
  querySelectorAll() { return []; },
  addEventListener(type, fn) { (this._keys = this._keys || []).push(fn); },
  body: makeElement("body"),
};
global.window = { devicePixelRatio: 1, addEventListener() {} };
global.performance = { now: () => Date.now() };
global.localStorage = { setItem() {}, getItem() { return null; } };
global.navigator = { clipboard: { writeText: async () => {} } };
global.Blob = function () {};
global.URL = { createObjectURL: () => "", revokeObjectURL() {} };
global.getComputedStyle = () => ({ getPropertyValue: () => "#000" });
global.requestAnimationFrame = fn => { fn(); return 0; };
global.cancelAnimationFrame = () => {};

process.on("unhandledRejection", e => ERRORS.push("unhandledRejection: " + e.message));
