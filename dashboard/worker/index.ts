/** Cloudflare Worker entry point for the vinext-starter template. */
import type { D1Database, ExecutionContext, Fetcher } from "@cloudflare/workers-types";
import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

interface Env {
  ASSETS: Fetcher;
  DB?: D1Database;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

type ApplicationAssets = {
  fetch(request: Request): Promise<Response>;
};

function applicationAssets(env: Env): ApplicationAssets {
  return {
    fetch: (request) => env.ASSETS.fetch(
      request as unknown as Parameters<Fetcher["fetch"]>[0],
    ) as unknown as Promise<Response>,
  };
}

function isStaticAsset(pathname: string): boolean {
  return pathname.startsWith("/assets/") || pathname.startsWith("/_next/static/") || pathname === "/favicon.png" || pathname === "/og.png";
}

// Image security config. SVG sources with .svg extension auto-skip the
// optimization endpoint on the client side (served directly, no proxy).
// To route SVGs through the optimizer (with security headers), set
// dangerouslyAllowSVG: true in next.config.js and uncomment below:
// const imageConfig: ImageConfig = { dangerouslyAllowSVG: true };

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      return handleImageOptimization(request, {
        fetchAsset: (path) => applicationAssets(env).fetch(
          new Request(new URL(path, request.url)),
        ),
        transformImage: async (body, { width, format, quality }) => {
          const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
          return result.response();
        },
      }, allowedWidths);
    }

    if (isStaticAsset(url.pathname)) {
      return applicationAssets(env).fetch(request);
    }

    return handler.fetch(request, { ...env, ASSETS: applicationAssets(env) }, ctx);
  },
};

export default worker;
