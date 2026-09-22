import { defineNitroConfig } from "nitro/config";

// The API is a separate service (FastAPI on Render) — see docs/architecture/DEPLOYMENT.md.
// Nitro compiles the rule below into a CDN-level rewrite in the Vercel build output, so the
// browser only ever talks to the Vercel origin and the frontend keeps requesting the
// relative path /api/... in every environment.
//
// API_ORIGIN is resolved at BUILD time, not runtime: the origin is baked into the generated
// route table. It is not a secret — it is a public hostname visible in any network trace.

function resolveApiOrigin(): string | undefined {
  // Vercel sets VERCEL=1 during its builds; NITRO_PRESET covers a hand-pinned build.
  const targetsVercel = process.env.VERCEL === "1" || process.env.NITRO_PRESET === "vercel";
  const raw = process.env.API_ORIGIN?.trim();

  if (!raw) {
    if (targetsVercel) {
      throw new Error(
        "API_ORIGIN is required for a Vercel build. Without it Nitro emits no /api/** " +
          "rewrite, every API request falls through to the SSR catch-all, and the app " +
          "serves HTML where the UI expects JSON. Set API_ORIGIN to the Render origin, " +
          "e.g. https://bw-observatory-api.onrender.com",
      );
    }
    // Local `npm run build`: no rewrite needed. `vite dev` never loads this file at all
    // (Nitro only runs when command === "build"), so local development is unaffected.
    return undefined;
  }

  // Strip trailing slashes so `https://host/` + `/api/**` cannot become `https://host//api/**`.
  const origin = raw.replace(/\/+$/, "");

  // Nitro only turns a proxy rule into a Vercel rewrite when `proxy.to` is an absolute
  // http(s) URL — see `canUseVercelRewrite` in nitro/dist/_presets.mjs. A value that fails
  // that test is dropped SILENTLY, producing a build that looks clean and serves HTML to
  // the data layer. Fail loudly here instead of shipping that.
  if (!/^https?:\/\/[^/]+$/.test(origin)) {
    throw new Error(
      `API_ORIGIN must be a bare absolute http(s) origin with no path — got: ${raw}`,
    );
  }
  return origin;
}

const apiOrigin = resolveApiOrigin();

export default defineNitroConfig({
  routeRules: apiOrigin ? { "/api/**": { proxy: `${apiOrigin}/api/**` } } : {},
});
