import Link from "next/link";
import type { TagOut } from "@/lib/types";

/** Topic badges for a bill (Roadmap Phase 2: bill topic tagging). Only
 *  active tags are ever passed in here -- the API already filters hidden
 *  ones out, so this component has no active/hidden logic of its own.
 *
 *  Each badge links to the browse page pre-filtered to that topic, the same
 *  discovery pattern as clicking a status or jurisdiction elsewhere in the
 *  app. Works from both a client component (BillCard) and a server
 *  component (the bill detail page) since it's pure display.
 */
export default function TagBadges({ tags }: { tags: TagOut[] }) {
  if (tags.length === 0) return null;

  return (
    <ul className="mt-2 flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <li key={tag.bill_tag_id}>
          <Link
            href={`/?tag=${encodeURIComponent(tag.slug)}`}
            className="inline-block rounded-full bg-ledger-700/10 px-2.5 py-0.5 text-[11px] font-medium text-ledger-700 hover:bg-ledger-700/20"
          >
            {tag.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}
