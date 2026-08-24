import type { MetadataRoute } from "next";

/** Crawling is welcome — the whole point is that legislation be findable.
 *  The admin flag-review endpoints live on the API host, not here, and are
 *  auth-gated regardless. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: "https://sunshineledger.josephbernal.com/sitemap.xml",
  };
}
