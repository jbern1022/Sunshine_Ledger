import { parseChangeMarkers } from "@/lib/changeMarkers";

/** Bill text with its inline `[deleted: …]` / `[added: …]` markers shown as
 *  struck and underlined wording. Each change also carries a visually
 *  hidden "removed"/"added" label (and a tooltip), so the meaning doesn't
 *  rely on colour or text decoration alone. */
export default function MarkedText({ text }: { text: string }) {
  return (
    <>
      {parseChangeMarkers(text).map((segment, i) => {
        if (segment.kind === "deleted") {
          return (
            <del key={i} title="removed" className="text-red-700 decoration-red-400">
              <span className="sr-only">[removed: </span>
              {segment.text}
              <span className="sr-only">]</span>
            </del>
          );
        }
        if (segment.kind === "added") {
          return (
            <ins key={i} title="added" className="bg-emerald-50 text-emerald-900 decoration-emerald-500">
              <span className="sr-only">[added: </span>
              {segment.text}
              <span className="sr-only">]</span>
            </ins>
          );
        }
        return <span key={i}>{segment.text}</span>;
      })}
    </>
  );
}
