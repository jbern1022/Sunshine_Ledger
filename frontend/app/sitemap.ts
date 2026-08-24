import type { MetadataRoute } from "next";
import { getAllBillsForSitemap, getAllPeopleForSitemap } from "@/lib/server-api";

const SITE = "https://sunshineledger.josephbernal.com";

/** Sitemap covering every bill.
 *
 *  Bills only became addressable recently, and an address search engines
 *  don't know about doesn't help anyone find legislation. Static pages are
 *  listed too, but the ~2,400 bill pages are the point.
 *
 *  Degrades to the static pages if the API is unreachable — a partial
 *  sitemap is better than a build failure or an empty one.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticPages: MetadataRoute.Sitemap = [
    { url: SITE, changeFrequency: "daily", priority: 1 },
    { url: `${SITE}/people`, changeFrequency: "daily", priority: 0.7 },
    { url: `${SITE}/map`, changeFrequency: "weekly", priority: 0.6 },
    { url: `${SITE}/methodology`, changeFrequency: "monthly", priority: 0.5 },
    { url: `${SITE}/privacy`, changeFrequency: "monthly", priority: 0.3 },
  ];

  const [bills, peopleIds] = await Promise.all([getAllBillsForSitemap(), getAllPeopleForSitemap()]);

  return [
    ...staticPages,
    ...bills.map((b) => ({
      url: `${SITE}/bills/${b.entity_id}`,
      lastModified: b.last_action_date ? new Date(b.last_action_date) : undefined,
      changeFrequency: "weekly" as const,
      priority: 0.8,
    })),
    ...peopleIds.map((id) => ({
      url: `${SITE}/people/${id}`,
      changeFrequency: "weekly" as const,
      priority: 0.6,
    })),
  ];
}
