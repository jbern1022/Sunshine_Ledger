import { CHANGE_TYPE_NAMES, changeLabel } from "@/lib/accountability";
import { escapeXml, SITE } from "@/lib/rss";
import { getCorrections } from "@/lib/server-api";

/** RSS feed of the corrections log (correction-process spec, step 5).
 *
 *  Same entries as /corrections: Material and Critical, newest first.
 *  Readers who relied on something we published can follow what changed
 *  without checking back. When the log can't be loaded the feed fails
 *  (503) rather than serving an empty list, which would read as "no
 *  corrections". */

export const revalidate = 600;

export async function GET() {
  const entries = await getCorrections();
  if (entries === null) {
    return new Response("The corrections log couldn't be loaded just now.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Retry-After": "600" },
    });
  }

  const items = entries
    .map((c) => {
      const url = `${SITE}/bills/${c.bill_entity_id}#correction-${c.id}`;
      const record = `${c.bill_number ?? "Record"}${c.bill_name ? ` — ${c.bill_name}` : ""}`;
      const ai =
        c.origin === "sunshine_ledger_ai"
          ? ` The changed text was AI-generated${c.was_reviewed ? " and had been reviewed by a person" : ", not reviewed by a person"}.`
          : "";
      const description = `${CHANGE_TYPE_NAMES[c.change_type]} (${c.severity}). ${c.explanation}${ai}`;
      return `    <item>
      <title>${escapeXml(`${changeLabel(c)}: ${record}`)}</title>
      <link>${escapeXml(url)}</link>
      <guid isPermaLink="false">${escapeXml(`${SITE}/corrections#${c.id}`)}</guid>
      <description>${escapeXml(description)}</description>
      <pubDate>${new Date(c.decided_at).toUTCString()}</pubDate>
    </item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Sunshine Ledger — corrections</title>
    <link>${SITE}/corrections</link>
    <atom:link href="${SITE}/corrections/feed.xml" rel="self" type="application/rss+xml" />
    <description>Every material or critical correction, update, clarification and retraction Sunshine Ledger has made, newest first. Each links to the record, which keeps the earlier version and the reason.</description>
    <language>en-us</language>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=600",
    },
  });
}
