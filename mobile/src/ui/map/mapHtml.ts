import type { CaptureRecord } from "../../domain/types";
import type { ScoutLayer } from "../../domain/scout";
import type { ScoutVisit } from "../../domain/scoutVisits";
import type { TreeStand } from "../../domain/trees";
import { displayCoords, mayShowCoords, type LocationPrecision } from "../../domain/location";
import { syncStateColors } from "../theme";
import { CROW_ICON_URI } from "./crowIconData";
import { LEAFLET_CSS, LEAFLET_JS } from "./leafletDist";

export interface MappedCapture {
  uuid: string;
  latitude: number;
  longitude: number;
  label: string;
  detail: string;
  /** The capture's name — its title, when the recordist gave it one. */
  title?: string;
  color: string;
  /** The family's colour, drawn as a glow behind the bird. Absent = no family. */
  glow?: string;
  familyName?: string;
  /** Marked a real observation. The map is mostly seeded pins without it. */
  keep?: boolean;
}

/**
 * Captures the map can actually place. One with no fix has nowhere to go.
 *
 * And one whose recordist asked for their location not to be shown has nowhere
 * to go either — a map is the most precise way there is to say where somebody
 * was, so it is the first thing the setting has to reach rather than the last.
 */
export function mappableCaptures(
  captures: CaptureRecord[],
  familyColors: Map<string, { color: string; name: string }> = new Map(),
  precision: LocationPrecision = "exact",
  // Undefined masks: a caller that has not been updated must not
  // publish coordinates by omission.
  censor?: boolean,
  fuzzMiles?: number,
): MappedCapture[] {
  if (!mayShowCoords(precision, censor)) return [];
  return captures
    // At fuzzed precision the pins are the *snapped* points — the map is the
    // sharpest screen there is, so it draws exactly what the server was told
    // and nothing finer.
    .map((c) => ({ c, at: displayCoords(c, precision, censor, fuzzMiles) }))
    .filter((placed): placed is { c: CaptureRecord; at: { latitude: number; longitude: number } } =>
      placed.at !== undefined)
    .map(({ c, at }) => ({
      uuid: c.uuid,
      latitude: at.latitude,
      longitude: at.longitude,
      // The star leads, as it does in the capture list: on a map where most
      // pins are seeded clips with fabricated coordinates, "is this real?" is
      // the first thing worth knowing about a marker.
      label: (c.keep ? "★ " : "") + new Date(c.recordedAt).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
      detail: `${Math.round(c.durationMs / 1000)}s · ${c.syncState}`,
      title: c.name || undefined,
      keep: c.keep,
      color: syncStateColors[c.syncState],
      glow: c.familyUuid ? familyColors.get(c.familyUuid)?.color : undefined,
      familyName: c.familyUuid ? familyColors.get(c.familyUuid)?.name : undefined,
    }));
}


/**
 * A Leaflet map, rendered in a WebView.
 *
 * Esri World Imagery for the satellite layer, with CARTO's labels-only raster
 * on top. Labels matter more here than prettiness —
 * a bare satellite tile of a park is unrecognisable, and the point of the map is
 * to answer "where was this crow" at a glance.
 *
 * Leaflet itself is loaded from a CDN. That means no map without a connection,
 * which is a real limitation in the field — but the tiles need the network
 * anyway, so an offline map would be an empty grid regardless.
 */
export interface Fix {
  latitude: number;
  longitude: number;
  accuracyMeters?: number;
}

/**
 * JSON that is safe to paste inside a `<script>` block.
 *
 * `JSON.stringify` escapes quotes and backslashes but not `<`, so a family
 * named `</script><img src=x onerror=…>` closes the tag and whatever follows
 * runs with the WebView's `postMessage` bridge in reach. The names on this map
 * are typed by the recordist, which puts this on the ordinary path rather than
 * behind an attack — a crow family called "</script>" is a rendering bug that
 * happens to be an injection.
 */
function scriptJson(value: unknown): string {
  return JSON.stringify(value ?? null)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

export function buildMapHtml(
  captures: MappedCapture[],
  focusUuid?: string,
  here?: Fix,
  trees?: TreeStand[],
  scout?: ScoutLayer,
  visits?: ScoutVisit[],
  haloMode: "keep" | "family" = "keep",
  hiddenSpecies: string[] = [],
  hiddenRegions: string[] = [],
  showRail = true,
): string {
  const markers = scriptJson(captures);
  const focus = scriptJson(focusUuid ?? null);
  const me = scriptJson(here ?? null);
  const stands = scriptJson(trees ?? []);
  const scoutData = scriptJson(scout ?? { targets: [], owls: [] });
  const visitData = scriptJson(visits ?? []);
  const halo = scriptJson(haloMode);
  const hidden = scriptJson(hiddenSpecies);
  const hiddenRegionData = scriptJson(hiddenRegions);
  const railOnInit = scriptJson(showRail);
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<!-- Inlined rather than fetched: this used to come from unpkg, which made
     the map shell a CDN dependency in an app built for a park with no
     signal. The tiles below still need a network; the library must not. -->
<style>${LEAFLET_CSS}</style>
<script>${LEAFLET_JS}</script>
<style>
  html, body, #map { height: 100%; margin: 0; background: #10141b; }
  .crow-marker {
    line-height: 36px;
    text-align: center;
  }
  .crow-marker img {
    /* Ben's crow, not the emoji. Its shadow is baked into the PNG now —
       a CSS drop-shadow here made every capture pin its own filtered GPU
       layer, ~150 of them compositing on every pan. */
    vertical-align: middle;
  }
  .crow-marker.pending { filter: grayscale(0.7) brightness(0.85); }
  /* Green means good: the top five wear it, the rest are the muted red of
     "worth a look, not the best on offer". Ben read the first draft's colors
     the other way around, because everyone would. */
  .scout-pin {
    display: grid; place-items: center; width: 28px; height: 28px;
    border-radius: 50%; background: #8c3b3b; color: #fff;
    font: 700 13px system-ui; border: 2px solid #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,.5);
  }
  .scout-pin.top { background: #1b5e20; }
  .scout-pin.done { background: #9aa5b1; opacity: 0.75; }
  .scout-pin.adhoc { background: #0277bd; }
  .community-bird { opacity: 0.72; filter: saturate(0.6); }
  .species-filter {
    background: rgba(255,255,255,.94); border-radius: 10px;
    padding: 8px 12px; font: 13px/1.9 system-ui, sans-serif; color: #222;
    box-shadow: 0 1px 5px rgba(0,0,0,.4); max-height: 42vh; overflow-y: auto;
  }
  .species-filter label { display: block; }
  /* Shrinkable: the checklist covers half the map, and most visits never
     touch it. The header is always there; the rows exist only expanded. */
  .species-filter .filter-head {
    font-weight: 700; cursor: pointer; user-select: none;
  }
  .species-filter.collapsed label { display: none; }
  .settings-panel {
    background: rgba(255,255,255,.96); border-radius: 10px;
    padding: 8px 12px; font: 13px/1.9 system-ui, sans-serif; color: #222;
    box-shadow: 0 1px 5px rgba(0,0,0,.4); max-height: 50vh; overflow-y: auto;
    display: none;
  }
  .settings-panel.open { display: block; }
  .settings-panel label { display: block; }
  .settings-panel input { margin-right: 6px; transform: scale(1.15); }
  .settings-panel .panel-section {
    font-weight: 700; margin-top: 4px;
  }
  .tree-emoji { font-size: 22px; line-height: 34px; position: relative; }
  .tree-emoji.tree-visited { filter: grayscale(0.8); opacity: 0.6; }
  .species-filter input { margin-right: 6px; transform: scale(1.15); }
  .locate-btn { display: grid; place-items: center; width: 40px; height: 40px;
    font-size: 20px; text-decoration: none; background: #fff; }
  /* Clear of the attribution line and Android's gesture bar: checkboxes
     that sit under either collect taps meant for something else, and every
     one of these choices persists. */
  .leaflet-bottom .leaflet-control { margin-bottom: 30px; }
  .settings-panel label, .species-filter label { padding: 3px 0; }
  .popup-mark { display: flex; gap: 12px; margin-top: 6px; }
  .popup-mark a { font-weight: 600; text-decoration: none; }
  /* The family's colour as a halo behind the bird. Crows are near-black on
     imagery that is mostly dark green and grey, so a coloured glow is the only
     thing that separates one group from another at a glance.

     Both layers are explicitly stacked. The glow is positioned and the emoji
     was a bare text node, and a positioned element paints after in-flow content
     whatever the source order — so the halo sat *over* the bird and washed it
     out, which is the opposite of the job. */
  .crow-glow {
    position: absolute;
    left: 50%; top: 50%;
    width: 34px; height: 34px;
    margin: -17px 0 0 -17px;
    border-radius: 50%;
    opacity: 0.85;
    pointer-events: none;
    z-index: 0;
  }
  .crow-bird {
    position: relative;
    z-index: 1;
  }
  /* Distinct from the crows on purpose: a pin plus an accuracy halo reads as
     "you", not as another sighting. */
  .here-dot {
    width: 16px; height: 16px; border-radius: 50%;
    background: #2f6feb; border: 3px solid #fff;
    box-shadow: 0 0 0 1px rgba(0,0,0,.45);
  }
  /* A flashlight beam out of the you-dot: which way the phone faces. The map
     never rotates (north stays up), so the beam carries the whole compass. */
  .heading-beam {
    width: 56px; height: 56px; border-radius: 50%;
    background: conic-gradient(from -26deg,
      rgba(47,111,235,.5) 0deg 52deg, transparent 52deg);
    transform-origin: 50% 50%;
    transition: transform 0.15s linear;
  }
  .leaflet-popup-content-wrapper {
    background: #1c2331; color: #e8eef7; border-radius: 10px;
  }
  .leaflet-popup-tip { background: #1c2331; }
  .leaflet-popup-content { margin: 12px 14px; min-width: 150px; }
  .popup-title { font-weight: 700; font-size: 14px; }
  .popup-detail { color: #8b95a5; font-size: 12px; margin-top: 2px; }
  .sighting-photo { display: block; max-width: 180px; max-height: 140px;
    border-radius: 6px; margin-top: 6px; }
  .photo-overlay { position: fixed; inset: 0; z-index: 10000;
    background: rgba(8, 10, 14, 0.92); display: grid; place-items: center; }
  .photo-overlay img { max-width: 94vw; max-height: 94vh; border-radius: 8px; }
  /* Leaflet ships its own rule for links inside the map container, which is
     more specific than a bare class — hence blue text on a blue button. Match
     that specificity rather than reaching for !important. */
  .leaflet-popup-content a.popup-open,
  .leaflet-popup-content a.popup-open:hover,
  .leaflet-popup-content a.popup-open:visited {
    display: block;
    margin: 10px 0 2px;
    padding: 9px 12px;
    background: #2f6feb;
    color: #ffffff;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    text-align: center;
    text-decoration: none;
  }
  .leaflet-popup-content a.popup-open:active { background: #2757b8; }
  .empty {
    position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; color: #5b6472; font: 14px sans-serif;
    text-align: center; padding: 24px; z-index: 500; pointer-events: none;
  }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var captures = ${markers};
  var focusUuid = ${focus};
  var here = ${me};

  var map = L.map('map', { preferCanvas: true,  attributionControl: true, zoomControl: true });
  // Credits stay, the footprint shrinks: the full line plus the "Leaflet"
  // prefix wraps two rows wide on a phone and sat exactly over the
  // settings button.
  map.attributionControl.setPrefix(false);

  // One checklist governs every marker family: predator species, community
  // crows, and Ben's own captures split by the ★ Keep flag.
  var speciesOn = {};
  var speciesDots = {};
  function markerGroup(name) {
    if (!speciesDots[name]) {
      speciesDots[name] = L.layerGroup();
      speciesOn[name] = hiddenSpecies.indexOf(name) === -1;
      if (speciesOn[name]) { speciesDots[name].addTo(map); }
    }
    return speciesDots[name];
  }
  // One deferred refresh for every gated icon layer (trees, birds): deferred
  // past pan/zoom animation — clearing layers mid-flight is the classic
  // null-_map crash — and shared so the layers cannot fight over timing.
  var hiddenSpecies = ${hidden};
  var gatedRefreshers = [];
  var refreshQueued = false;
  function queueRefresh() {
    if (refreshQueued) { return; }
    refreshQueued = true;
    setTimeout(function () {
      refreshQueued = false;
      // Never rebuild while a popup is open: the open popup's marker lives
      // in a gated group, and clearing that group mid-popup is the tree-tap
      // crash. popupclose re-queues, so the refresh happens moments later.
      if (map._popup && map._popup.isOpen && map._popup.isOpen()) { return; }
      gatedRefreshers.forEach(function (refresh) {
        try { refresh(); } catch (ignored) {}
      });
    }, 120);
  }
  map.on('moveend zoomend popupclose', queueRefresh);
  var iconRefreshHook = queueRefresh;
  function buildSpeciesFilter() {
    if (!Object.keys(speciesDots).length) { return; }
    var filter = L.control({ position: 'bottomright' });
    filter.onAdd = function () {
      var box = document.createElement('div');
      // Collapsed until asked: on a phone the full checklist is half the
      // map, and the header row still says the layer exists.
      box.className = 'species-filter collapsed';
      L.DomEvent.disableClickPropagation(box);
      L.DomEvent.disableScrollPropagation(box);
      var head = document.createElement('div');
      head.className = 'filter-head';
      function headText() {
        var names = Object.keys(speciesDots);
        var on = names.filter(function (n) { return speciesOn[n]; }).length;
        var collapsed = box.className.indexOf('collapsed') !== -1;
        head.textContent = (collapsed ? '▸ ' : '▾ ') + 'Birds ' + on + '/' + names.length;
      }
      head.addEventListener('click', function () {
        box.classList.toggle('collapsed');
        headText();
      });
      box.appendChild(head);
      Object.keys(speciesDots).sort().forEach(function (name) {
        var row = document.createElement('label');
        var check = document.createElement('input');
        check.type = 'checkbox';
        check.checked = speciesOn[name];
        check.addEventListener('change', function () {
          speciesOn[name] = check.checked;
          if (check.checked) { speciesDots[name].addTo(map); }
          else { map.removeLayer(speciesDots[name]); }
          send({ type: 'species-filter', name: name, on: check.checked });
          headText();
          iconRefreshHook();
        });
        row.appendChild(check);
        row.appendChild(document.createTextNode(' ' + name));
        box.appendChild(row);
      });
      headText();
      return box;
    };
    filter.addTo(map);
  }

  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { attribution: '&copy; Esri', maxZoom: 21, maxNativeZoom: 20 }
  ).addTo(map);

  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png',
    { attribution: '&copy; CARTO &middot; OSM', subdomains: 'abcd', maxZoom: 21, maxNativeZoom: 20 }
  ).addTo(map);

  function send(message) {
    if (window.ReactNativeWebView) {
      window.ReactNativeWebView.postMessage(JSON.stringify(message));
    }
  }

  // Every popup and icon below is built by string concatenation, so anything a
  // recordist typed — a family name, most of all — is markup until it is
  // escaped. The colour is escaped too: it lands inside a style attribute, and
  // a quote there is as good as a tag.
  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  window.onerror = function (message, source, line) {
    try {
      send({ type: 'map-error', message: String(message) + ' @' + line });
    } catch (ignored) {}
    return true;
  };

  var stands = ${stands};
  // Visits arrive and change by injection (setVisits/addVisit below), never
  // by page rebuild — reloading a megabyte of map to grey one pin was lag,
  // and the initial list landing a second after open was a whole reload.
  var visits = ${visitData};
  function visitNear(lat, lon) {
    for (var i = 0; i < visits.length; i++) {
      var dy = (visits[i].latitude - lat) * 110540;
      var dx = (visits[i].longitude - lon) * 84000;
      if (dy * dy + dx * dx < 60 * 60) { return visits[i]; }
    }
    return null;
  }
  function streetLink(lat, lon) {
    // Two doors into Google Maps: the pano for looking, directions for going.
    return '<a class="popup-open" href="#" onclick="send({type:\\'street-view\\',lat:'
      + lat + ',lon:' + lon + '});return false;">Street view</a>'
      + ' <a class="popup-open" href="#" onclick="send({type:\\'directions\\',lat:'
      + lat + ',lon:' + lon + '});return false;">Directions</a>';
  }
  function markButtons(kind, lat, lon) {
    var at = kind + "," + lat + "," + lon;
    return '<div class="popup-mark">' +
      '<a href="#" onclick="send({type:\\'scout-visit\\',kind:\\'' + kind +
        '\\',lat:' + lat + ',lon:' + lon +
        ',outcome:\\'crows\\'});return false;">🐦‍⬛ Crows here</a>' +
      '<a href="#" onclick="send({type:\\'scout-visit\\',kind:\\'' + kind +
        '\\',lat:' + lat + ',lon:' + lon +
        ',outcome:\\'nothing\\'});return false;">∅ Nothing</a></div>';
  }
  function visitedLine(visit) {
    return '<div class="popup-detail">scouted ' +
      esc(visit.visitedAt.slice(0, 10)) + ' — ' +
      (visit.outcome === 'crows' ? '🐦‍⬛ crows' : 'nothing') + '</div>';
  }

  // Scouting layer, drawn under the capture pins and never in the bounds —
  // 2,500 trees must not decide what the map frames.
  function bandColor(h) {
    return h >= 30 ? '#7b1fa2' : h >= 25 ? '#c2185b'
         : h >= 21 ? '#e64a19' : '#f9a825';
  }
  function standPopup(s) {
    var visit = visitNear(s.latitude, s.longitude);
    return '<div class="popup-title">' + s.heightM + ' m canopy</div>' +
      '<div class="popup-detail">~' + s.areaM2 + ' m² stand</div>' +
      (visit ? visitedLine(visit)
             : markButtons('tree', s.latitude, s.longitude)) +
      streetLink(s.latitude, s.longitude);
  }
  function standDot(s, group) {
    var c = bandColor(s.heightM);
    var visit = visitNear(s.latitude, s.longitude);
    // Function content throughout: the popup builds when opened, so a
    // fresh visit shows without rebuilding the page, and thousands of
    // markers stop paying for popup strings nobody opened.
    L.circleMarker([s.latitude, s.longitude], {
      radius: Math.max(3, Math.min(10, Math.sqrt(s.areaM2) / 10)),
      color: c, fillColor: c, fillOpacity: visit ? 0.18 : 0.5,
      weight: visit ? 2 : 1
    }).bindPopup(function () { return standPopup(s); }).addTo(group);
  }
  // 45k stands would lag init as one layer: the giants (>= 21 m) are always
  // on; the minor horde exists only zoomed in, in view, capped — the same
  // gating as every icon layer.
  var minorStands = [];
  stands.forEach(function (s) {
    if (s.heightM >= 21) { standDot(s, map); }
    else { minorStands.push(s); }
  });
  if (minorStands.length) {
    var minorGroup = L.layerGroup().addTo(map);
    gatedRefreshers.push(function () {
      minorGroup.clearLayers();
      if (map.getZoom() < 13) { return; }
      var box = map.getBounds().pad(0.1);
      var shown = 0;
      for (var i = 0; i < minorStands.length && shown < 1500; i++) {
        var s = minorStands[i];
        if (!box.contains([s.latitude, s.longitude])) { continue; }
        standDot(s, minorGroup);
        shown += 1;
      }
    });
    queueRefresh();
  }
  if (stands.length) {
    // Close in, the dots bloom into backlit trees — the capture-halo idea
    // applied to canopy, with the tier colour as the light.
    var treeIcons = L.layerGroup().addTo(map);
    var TREE_ZOOM = 14, TREE_CAP = 80;
    gatedRefreshers.push(function () {
      treeIcons.clearLayers();
      if (map.getZoom() < TREE_ZOOM) { return; }
      var box = map.getBounds().pad(0.15);
      var shown = 0;
      for (var i = 0; i < stands.length && shown < TREE_CAP; i++) {
        let s = stands[i];
        if (!box.contains([s.latitude, s.longitude])) { continue; }
        var c = bandColor(s.heightM);
        var dim = visitNear(s.latitude, s.longitude) ? ' tree-visited' : '';
        L.marker([s.latitude, s.longitude], {
          icon: L.divIcon({
            html: '<span class="crow-glow" style="background: radial-gradient(circle, '
              + c + 'e0 0%, ' + c + '66 58%, transparent 74%)"></span>'
              + '<span class="tree-emoji' + dim + '">🌳</span>',
            className: 'crow-marker', iconSize: [34, 34],
            iconAnchor: [17, 17], popupAnchor: [0, -17]
          })
        }).bindPopup(function () { return standPopup(s); }).addTo(treeIcons);
        shown += 1;
      }
    });
    queueRefresh();
  }

  // The compass beam. The app injects window.setHeading(deg) from the
  // phone's magnetometer; the beam only exists once there is both a fix to
  // anchor it and a heading to point it.
  var headingMarker = null;
  window.setHeading = function (deg) {
    if (!here) { return; }
    if (!headingMarker) {
      headingMarker = L.marker([here.latitude, here.longitude], {
        icon: L.divIcon({ className: '', html: '<div class="heading-beam"></div>',
                          iconSize: [56, 56], iconAnchor: [28, 28] }),
        zIndexOffset: 999, interactive: false
      }).addTo(map);
    }
    var element = headingMarker.getElement();
    var beam = element && element.querySelector('.heading-beam');
    if (beam) { beam.style.transform = 'rotate(' + Number(deg) + 'deg)'; }
  };

  // Tap a popup photo for the full-size version, tap anywhere to dismiss.
  // iNat serves size variants by path, so 'small' upgrades to 'large'.
  var activeOverlay = null;
  function closePhoto() {
    if (!activeOverlay) { return; }
    activeOverlay.remove();
    activeOverlay = null;
    send({ type: 'photo-closed' });
  }
  function zoomPhoto(src) {
    var overlay = document.createElement('div');
    overlay.className = 'photo-overlay';
    var img = document.createElement('img');
    img.src = src.replace('/small', '/large');
    overlay.appendChild(img);
    overlay.addEventListener('click', closePhoto);
    document.body.appendChild(overlay);
    activeOverlay = overlay;
    // The app claims Android's back while a photo is up, so back closes
    // the photo instead of leaving the map.
    send({ type: 'photo-open' });
  }
  window.zoomPhoto = zoomPhoto;
  window.closePhoto = closePhoto;

  var scout = ${scoutData};

  // The county filter. Layers published before regions existed carry no
  // slugs; regionVisible treats "no region" as always-on, so an old layer
  // simply has no counties to filter and everything shows.
  var hiddenRegions = ${hiddenRegionData};
  var regionOn = {};
  (scout.regions || []).forEach(function (r) {
    regionOn[r.slug] = hiddenRegions.indexOf(r.slug) === -1;
  });
  function regionVisible(slug) {
    return !slug || regionOn[slug] !== false;
  }
  var railOn = ${railOnInit};
  var railLines = [];
  var targetMarkers = [];
  function applyLayerSettings() {
    railLines.forEach(function (r) {
      var want = railOn && regionVisible(r.region);
      if (want && !map.hasLayer(r.line)) { r.line.addTo(map); }
      if (!want && map.hasLayer(r.line)) { map.removeLayer(r.line); }
    });
    targetMarkers.forEach(function (t) {
      var want = regionVisible(t.region);
      if (want && !map.hasLayer(t.marker)) { t.marker.addTo(map); }
      if (!want && map.hasLayer(t.marker)) { map.removeLayer(t.marker); }
    });
    // Dots and icons re-filter themselves on the queued refresh.
    queueRefresh();
  }

  // TRAX, drawn first so everything else sits on top: reference geometry for
  // getting one's bearings, not a layer to interact with. Canvas polylines,
  // cheap at any count.
  (scout.rail || []).forEach(function (seg) {
    var line = L.polyline(seg.coords, { color: esc(seg.color), weight: 3,
                                        opacity: 0.7, interactive: false });
    railLines.push({ line: line, region: seg.region });
    if (railOn && regionVisible(seg.region)) { line.addTo(map); }
  });

  if (scout.predators && scout.predators.length) {
    // Dots always (canvas, cheap at any count); the pretty image markers are
    // DOM nodes, so they exist only zoomed in, in view, and capped — 342 of
    // them at once is what lagged the phone.
    function sightingPopup(p) {
      return '<div class="popup-title">' + esc(p.species) + '</div>' +
        '<div class="popup-detail">' + (p.community
          ? 'community sighting (iNaturalist) — not one of yours'
          : 'sighted here — crow families notice') +
        (p.date ? '<br>seen ' + esc(p.date) : '') +
        (p.count > 1 ? ' · ' + Number(p.count) + ' birds' : '') +
        (p.by ? ' by ' + esc(p.by) : '') + '</div>' +
        (p.photo
          ? '<img class="sighting-photo" src="' + esc(p.photo) +
            '" loading="lazy" onerror="this.remove()"' +
            ' onclick="zoomPhoto(this.src)">'
          : '') +
        streetLink(p.latitude, p.longitude);
    }
    function rowName(p) {
      return (p.species || 'Other') + (p.community ? ' — community' : '');
    }
    // Groups register up front so the checklist knows every bird, but the
    // dots themselves live in ONE viewport layer, rebuilt per pan end:
    // in view, capped, and only past DOT_ZOOM. Keeping all three thousand
    // in the renderer was the drag jank even after the zoom gate — the
    // canvas hit-tests every path per touch-move, so the map was smooth
    // exactly when the predators were toggled off. Canvas circles carry
    // no DOM, so a few hundred per rebuild is cheap; species and county
    // filters are applied here per refresh instead of by group surgery.
    scout.predators.forEach(function (p) { markerGroup(rowName(p)); });
    var dotLayer = L.layerGroup().addTo(map);
    var DOT_ZOOM = 12, DOT_CAP = 500;
    gatedRefreshers.push(function () {
      dotLayer.clearLayers();
      if (map.getZoom() < DOT_ZOOM) { return; }
      var box = map.getBounds().pad(0.1);
      var shown = 0;
      for (var i = 0; i < scout.predators.length && shown < DOT_CAP; i++) {
        let p = scout.predators[i];
        if (!speciesOn[rowName(p)] || !regionVisible(p.region)) { continue; }
        if (!box.contains([p.latitude, p.longitude])) { continue; }
        L.circleMarker([p.latitude, p.longitude], {
          radius: 4, color: '#4a148c', fillColor: '#4a148c',
          fillOpacity: 0.45, weight: 1
        }).bindPopup(function () { return sightingPopup(p); }).addTo(dotLayer);
        shown += 1;
      }
    });
    var predatorIcons = L.layerGroup().addTo(map);
    var ICON_ZOOM = 13, ICON_CAP = 60;
    // Kept between refreshes and diffed: tearing down and recreating sixty
    // image markers on every pan end was a hitch after every gesture, for
    // a view whose icons mostly had not changed.
    var iconMarkers = {};
    function refreshPredatorIcons() {
      var wanted = {};
      if (map.getZoom() >= ICON_ZOOM) {
        var box = map.getBounds().pad(0.15);
        var shown = 0;
        // An eBird checklist pins every species it saw to one point (the
        // Capitol hotspot stacks six icons), and separate iNat observations
        // land 10-20 m apart — identical pixels at map zoom either way, and
        // whichever draws last hides the rest, which is how a magpie wore
        // the raven's face. So collisions are detected in PIXEL space at the
        // current zoom: any icon landing within an already-placed icon's
        // footprint fans out on an anchor-offset ring. Coordinates stay
        // honest; the refresh reruns per zoom, so the fan relaxes as the
        // real spacing becomes visible.
        var placedPts = [];
        for (var i = 0; i < scout.predators.length && shown < ICON_CAP; i++) {
          var p = scout.predators[i];
          if (!speciesOn[rowName(p)] || !regionVisible(p.region)) { continue; }
          if (!(scout.icons && scout.icons[p.icon])) { continue; }
          if (!box.contains([p.latitude, p.longitude])) { continue; }
          var pt = map.latLngToLayerPoint([p.latitude, p.longitude]);
          var n = 0;
          for (var j = 0; j < placedPts.length; j++) {
            if (Math.abs(placedPts[j].x - pt.x) < 28
                && Math.abs(placedPts[j].y - pt.y) < 28) { n += 1; }
          }
          placedPts.push(pt);
          var dx = 0, dy = 0;
          if (n) {
            var ring = Math.ceil(n / 6);
            var angle = (n - 1) * (Math.PI / 3) + (ring - 1) * 0.5;
            dx = Math.round(24 * ring * Math.cos(angle));
            dy = Math.round(24 * ring * Math.sin(angle));
          }
          wanted[i] = { dx: dx, dy: dy };
          shown += 1;
        }
      }
      Object.keys(iconMarkers).forEach(function (key) {
        var want = wanted[key];
        var have = iconMarkers[key];
        if (want && want.dx === have.dx && want.dy === have.dy) { return; }
        predatorIcons.removeLayer(have.marker);
        delete iconMarkers[key];
      });
      Object.keys(wanted).forEach(function (key) {
        if (iconMarkers[key]) { return; }
        // forEach parameter, so each popup closes over its own row — a var
        // loop here once titled every sighting "Black-billed Magpie".
        var p = scout.predators[key];
        var at = wanted[key];
        var size = p.community ? 24 : 32;
        var marker = L.marker([p.latitude, p.longitude], {
          icon: L.icon({ iconUrl: scout.icons[p.icon], iconSize: [size, size],
                         iconAnchor: [size / 2 - at.dx, size / 2 - at.dy],
                         popupAnchor: [at.dx, at.dy - size / 2],
                         className: p.community ? 'community-bird' : '' })
        }).bindPopup(function () { return sightingPopup(p); });
        marker.addTo(predatorIcons);
        iconMarkers[key] = { marker: marker, dx: at.dx, dy: at.dy };
      });
    }
    gatedRefreshers.push(refreshPredatorIcons);
    queueRefresh();
  } else {
    scout.owls.filter(function (o) {
      return regionVisible(o.region);
    }).forEach(function (o) {
      L.circleMarker([o.latitude, o.longitude], {
        radius: 4, color: '#4a148c', fillColor: '#4a148c', fillOpacity: 0.5,
        weight: 1
      }).bindPopup('<div class="popup-title">Great Horned Owl sighting</div>' +
        '<div class="popup-detail">crow families avoid these</div>').addTo(map);
    });
  }
  function targetIcon(t) {
    var visit = visitNear(t.latitude, t.longitude);
    var cls = visit ? ' done' : (t.rank <= 5 ? ' top' : '');
    return L.divIcon({
      html: '<span class="scout-pin' + cls + '">' + t.rank + '</span>',
      className: '', iconSize: [28, 28], iconAnchor: [14, 14],
      popupAnchor: [0, -14]
    });
  }
  // A fresh visit greys its pin right away, whether it just got marked or
  // the list arrived after the page did.
  function restyleTargets() {
    targetMarkers.forEach(function (tm) { tm.marker.setIcon(targetIcon(tm.t)); });
  }
  window.addVisit = function (visit) {
    visits.push(visit);
    restyleTargets();
    queueRefresh();
  };
  window.setVisits = function (list) {
    visits = list;
    restyleTargets();
    queueRefresh();
  };
  // The app can inject the visit list before this script finishes parsing;
  // the stash catches the early delivery.
  if (window.__pendingVisits) {
    window.setVisits(window.__pendingVisits);
    delete window.__pendingVisits;
  }
  scout.targets.forEach(function (t) {
    var parts = [];
    for (var key in t.signals) {
      parts.push(esc(key) + ' ' + Math.round(t.signals[key] * 100) + '%');
    }
    var marker = L.marker([t.latitude, t.longitude],
                          { icon: targetIcon(t), zIndexOffset: 500 })
      .bindPopup(function () {
        var visitNow = visitNear(t.latitude, t.longitude);
        return '<div class="popup-title">#' + t.rank +
          (t.near ? ' · ' + esc(t.near) : '') + '</div>' +
        '<div class="popup-detail">' + parts.join(' · ') + '</div>' +
        (visitNow ? visitedLine(visitNow)
                  : markButtons('target', t.latitude, t.longitude)) +
        streetLink(t.latitude, t.longitude);
      });
    targetMarkers.push({ marker: marker, region: t.region, t: t });
    if (regionVisible(t.region)) { marker.addTo(map); }
  });

  // Scout-anywhere: long-press drops a circle, the server answers with the
  // best cells of the already-computed score surface inside it. Only alive
  // when a scout layer is up — the circle is a question about the score,
  // and without the layer there is no score to ask about.
  if ((scout.targets || []).length) {
    var AREA_COLOR = '#0277bd';
    var areaRadius = 2000;
    var areaCircle = null;
    var areaSpots = L.layerGroup().addTo(map);
    function areaPopupHtml(status) {
      var chips = [1000, 2000, 4000].map(function (r) {
        return '<a href="#" onclick="setAreaRadius(' + r + ');return false;"'
          + (r === areaRadius
             ? ' style="font-weight:700;text-decoration:underline"' : '')
          + '>' + (r / 1000) + ' km</a>';
      }).join(' &nbsp; ');
      return '<div class="popup-title">Scout this area</div>'
        + '<div class="popup-detail">radius: ' + chips + '</div>'
        + (status ? '<div class="popup-detail">' + status + '</div>' : '')
        + '<a class="popup-open" href="#" onclick="scoutArea();return false;">'
        + '🔭 Find best spots</a>'
        + '<a href="#" onclick="clearScoutArea();return false;" '
        + 'style="display:block;margin-top:6px;font-size:12px;color:#8b95a5">'
        + '✕ clear</a>';
    }
    window.clearScoutArea = function () {
      if (areaCircle) { map.removeLayer(areaCircle); areaCircle = null; }
      areaSpots.clearLayers();
    };
    window.setAreaRadius = function (r) {
      areaRadius = r;
      if (areaCircle) {
        areaCircle.setRadius(r);
        areaCircle.setPopupContent(areaPopupHtml(''));
      }
    };
    window.scoutArea = function () {
      if (!areaCircle) { return; }
      var c = areaCircle.getLatLng();
      areaCircle.setPopupContent(areaPopupHtml('scouting…'));
      send({ type: 'scout-area', lat: c.lat, lon: c.lng, radius: areaRadius });
    };
    window.showSpots = function (spots) {
      areaSpots.clearLayers();
      if (areaCircle) { areaCircle.closePopup(); }
      spots.forEach(function (s) {
        var parts = [];
        for (var key in s.signals) {
          parts.push(esc(key) + ' ' + Math.round(s.signals[key] * 100) + '%');
        }
        L.marker([s.latitude, s.longitude], {
          icon: L.divIcon({
            html: '<span class="scout-pin adhoc">' + s.rank + '</span>',
            className: '', iconSize: [28, 28], iconAnchor: [14, 14],
            popupAnchor: [0, -14]
          }),
          zIndexOffset: 600
        }).bindPopup(function () {
          var visitNow = visitNear(s.latitude, s.longitude);
          return '<div class="popup-title">Spot ' + s.rank
            + (s.near ? ' · ' + esc(s.near) : '') + '</div>'
            + '<div class="popup-detail">' + parts.join(' · ') + '</div>'
            + (visitNow ? visitedLine(visitNow)
                        : markButtons('spot', s.latitude, s.longitude))
            + streetLink(s.latitude, s.longitude);
        }).addTo(areaSpots);
      });
    };
    window.scoutNote = function (note) {
      if (areaCircle) {
        areaCircle.setPopupContent(areaPopupHtml(esc(note)));
        areaCircle.openPopup();
      }
    };
    // Leaflet turns a touch long-press into contextmenu.
    map.on('contextmenu', function (e) {
      window.clearScoutArea();
      areaCircle = L.circle(e.latlng, {
        radius: areaRadius, color: AREA_COLOR, weight: 2,
        dashArray: '6 6', fillColor: AREA_COLOR, fillOpacity: 0.06
      }).addTo(map);
      areaCircle.bindPopup(areaPopupHtml(''), { closeOnClick: false });
      areaCircle.openPopup();
    });
  }

  // The little settings door: extra options that don't deserve a permanent
  // control — today the county filter and the rail lines. Only rendered
  // when the layer actually has something to offer it.
  if ((scout.regions || []).length > 1 || railLines.length) {
    var settings = L.control({ position: 'bottomleft' });
    settings.onAdd = function () {
      var wrap = document.createElement('div');
      L.DomEvent.disableClickPropagation(wrap);
      L.DomEvent.disableScrollPropagation(wrap);
      var panel = document.createElement('div');
      panel.className = 'settings-panel';
      if ((scout.regions || []).length > 1) {
        var counties = document.createElement('div');
        counties.className = 'panel-section';
        counties.textContent = 'Counties';
        panel.appendChild(counties);
        scout.regions.forEach(function (r) {
          var row = document.createElement('label');
          var check = document.createElement('input');
          check.type = 'checkbox';
          check.checked = regionOn[r.slug] !== false;
          check.addEventListener('change', function () {
            regionOn[r.slug] = check.checked;
            applyLayerSettings();
            send({ type: 'region-filter', slug: r.slug, on: check.checked });
          });
          row.appendChild(check);
          row.appendChild(document.createTextNode(' ' + r.name));
          panel.appendChild(row);
        });
      }
      if (railLines.length) {
        var lines = document.createElement('div');
        lines.className = 'panel-section';
        lines.textContent = 'Overlays';
        panel.appendChild(lines);
        var railRow = document.createElement('label');
        var railCheck = document.createElement('input');
        railCheck.type = 'checkbox';
        railCheck.checked = railOn;
        railCheck.addEventListener('change', function () {
          railOn = railCheck.checked;
          applyLayerSettings();
          send({ type: 'rail-toggle', on: railOn });
        });
        railRow.appendChild(railCheck);
        railRow.appendChild(document.createTextNode(' Rail lines'));
        panel.appendChild(railRow);
      }
      var bar = document.createElement('div');
      bar.className = 'leaflet-bar';
      var button = document.createElement('a');
      button.className = 'locate-btn';
      button.href = '#';
      button.textContent = '⚙️';
      button.setAttribute('aria-label', 'Map settings');
      button.addEventListener('click', function (event) {
        event.preventDefault();
        panel.classList.toggle('open');
      });
      bar.appendChild(button);
      wrap.appendChild(panel);
      wrap.appendChild(bar);
      return wrap;
    };
    settings.addTo(map);
  }


  var bounds = [];
  var focused = null;
  captures.forEach(function (capture) {
    // Every one of Ben's captures is backlit; what the light MEANS is the
    // haloMode toggle. 'keep': the corpus's sacred distinction — yellow for
    // real field recordings, slate for seeded and test clips. 'family': each
    // crow glows its family's colour, family-less ones a dim neutral.
    var glowColor = ${halo} === 'family'
      ? esc(capture.glow || '#9aa5b1')
      : (capture.keep ? '#ffd970' : '#8fa8bf');
    var glow = '<span class="crow-glow" style="background: radial-gradient(circle, ' +
        glowColor + 'f2 0%, ' + glowColor + '77 58%, transparent 74%)"></span>';
    var icon = L.divIcon({
      html: glow + '<img class="crow-bird" src="${CROW_ICON_URI}" width="36" height="36">',
      className: 'crow-marker' + (capture.color === '${syncStateColors.synced}' ? '' : ' pending'),
      iconSize: [36, 36],
      iconAnchor: [18, 18],
      popupAnchor: [0, -18]
    });
    var marker = L.marker([capture.latitude, capture.longitude], { icon: icon })
      .addTo(markerGroup(capture.keep
        ? '★ American Crow — kept capture'
        : 'American Crow — capture'));
    if (capture.uuid === focusUuid) { focused = marker; }
    marker.bindPopup(
      '<div class="popup-title">' + esc(capture.title || capture.label) + '</div>' +
      '<div class="popup-detail">' +
        (capture.title ? esc(capture.label) + ' · ' : '') + esc(capture.detail) +
        (capture.familyName ? ' · ' + esc(capture.familyName) : '') + '</div>' +
      '<a class="popup-open" href="#" onclick="send({type:\\'open\\',uuid:\\'' + esc(capture.uuid) + '\\'});return false;">Open capture</a>'
    );
    bounds.push([capture.latitude, capture.longitude]);
  });

  // After the last registrant, so every marker family has its row.
  buildSpeciesFilter();

  var hereDot = null, hereCircle = null;
  if (here) {
    // The halo is the honest part: a fix is a claim with an error bar, and
    // drawing only a dot implies precision the GPS did not promise.
    hereCircle = L.circle([here.latitude, here.longitude], {
      radius: here.accuracyMeters || 0,
      color: '#2f6feb', weight: 1, fillColor: '#2f6feb', fillOpacity: 0.12,
      interactive: false
    }).addTo(map);
    hereDot = L.marker([here.latitude, here.longitude], {
      icon: L.divIcon({ className: 'here-dot', iconSize: [16, 16], iconAnchor: [8, 8] }),
      zIndexOffset: 1000,
      interactive: false
    }).addTo(map);
    bounds.push([here.latitude, here.longitude]);
  }

  // The live GPS stream. The app injects fixes as they arrive; the dot,
  // halo and compass beam glide instead of waiting for a page rebuild.
  window.setPosition = function (lat, lon, acc) {
    if (!here) { here = {}; }
    here.latitude = lat; here.longitude = lon; here.accuracyMeters = acc;
    // First fix plants the dot right here — the page used to be rebuilt
    // for it, which reloaded the whole map seconds after it opened.
    if (!hereCircle) {
      hereCircle = L.circle([lat, lon], {
        radius: acc || 0,
        color: '#2f6feb', weight: 1, fillColor: '#2f6feb', fillOpacity: 0.12,
        interactive: false
      }).addTo(map);
    }
    if (!hereDot) {
      hereDot = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'here-dot', iconSize: [16, 16],
                          iconAnchor: [8, 8] }),
        zIndexOffset: 1000,
        interactive: false
      }).addTo(map);
    }
    hereDot.setLatLng([lat, lon]);
    hereCircle.setLatLng([lat, lon]);
    if (acc) { hereCircle.setRadius(acc); }
    if (headingMarker) { headingMarker.setLatLng([lat, lon]); }
  };

  var locate = L.control({ position: 'topleft' });
  locate.onAdd = function () {
    var button = document.createElement('a');
    button.className = 'locate-btn';
    button.href = '#';
    button.textContent = '📍';
    button.setAttribute('aria-label', 'Center on my location');
    L.DomEvent.disableClickPropagation(button);
    button.addEventListener('click', function (event) {
      event.preventDefault();
      if (here) { map.setView([here.latitude, here.longitude], 16); }
      else { send({ type: 'locate' }); }
    });
    var wrap = document.createElement('div');
    wrap.className = 'leaflet-bar';
    wrap.appendChild(button);
    return wrap;
  };
  locate.addTo(map);

  if (focused) {
    // Arriving from a capture: show that one, close in, with its popup open.
    map.setView(focused.getLatLng(), 18);
    focused.openPopup();
  } else if (bounds.length > 0) {
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 17 });
  } else {
    map.setView([0, 0], 2);
    var empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'No captures with a location yet. Record one with GPS enabled and it will appear here.';
    document.body.appendChild(empty);
  }
</script>
</body>
</html>`;
}
