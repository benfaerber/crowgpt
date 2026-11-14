// The promo site's one script: /geo says roughly where the visitor is.
//
// Everything else on crowgpt.org is a static file, served without this ever
// running. The Scan page asks /geo so it can send an approximate location with
// an upload, which rules out look-alike species from other continents.
//
// The answer is Cloudflare's own estimate from the visitor's address
// (request.cf), city-level at best. Nothing is looked up elsewhere, nothing is
// stored, and the address itself is never returned.
export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== "/geo") {
      return env.ASSETS.fetch(request);
    }
    const cf = request.cf ?? {};
    const latitude = Number.parseFloat(cf.latitude);
    const longitude = Number.parseFloat(cf.longitude);
    const known = Number.isFinite(latitude) && Number.isFinite(longitude);
    return Response.json(
      {
        latitude: known ? latitude : null,
        longitude: known ? longitude : null,
        city: cf.city ?? null,
        region: cf.region ?? null,
        country: cf.country ?? null,
      },
      { headers: { "Cache-Control": "private, no-store" } },
    );
  },
};
