import { getRecentBillsForFeed } from "@/lib/server-api";

const SITE = "https://sunshineledger.josephbernal.com";

/** RSS feed of recently-active bills.
 *
 *  A transparency site is most useful to people who want to keep watching:
 *  reporters, advocates, anyone following a topic. A feed lets them do that
 *  without polling the site or needing an account -- which matters here,
 *  since accounts are deliberately out of scope at MVP.
 *
 *  Each item carries the plain-language summary rather than the legal
 *  title, because the summary is what makes the bill legible at a glance,
 *  and states that the summaries are AI-written so that caveat travels with
 *  the content instead of being left behind on the site.
 */

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export const revalidate = 3600;

export async function GET() {
  const bills = await getRecentBillsForFeed(50);

  const items = bills
    .map((b) => {
      const url = `${SITE}/bills/${b.entity_id}`;
      const summary = b.what_it_does ?? "No plain-language summary has been generated yet.";
      const jurisdiction = b.jurisdiction_name ?? "Florida";
      return `    <item>
      <title>${escapeXml(`${b.bill_number} — ${jurisdiction}`)}</title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <description>${escapeXml(summary)}</description>
      ${b.last_action_date ? `<pubDate>${new Date(b.last_action_date).toUTCString()}</pubDate>` : ""}
    </item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Sunshine Ledger — recently active bills</title>
    <link>${SITE}</link>
    <atom:link href="${SITE}/feed.xml" rel="self" type="application/rss+xml" />
    <description>Florida state and local legislation, summarised in plain language. Summaries are AI-generated and are not individually reviewed by a person — the linked source is the authority.</description>
    <language>en-us</language>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
