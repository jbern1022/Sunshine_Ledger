import type { BillLayers as Layers, LayerBlock, LayerKey, LayerVersion, Origin } from "@/lib/types";
import { LAYER_META, LAYER_ORDER, ORIGINS_FOR_LAYER, formatDate, originBadge, reviewLabel } from "@/lib/layers";

/** The three separately labeled layers on a bill page. Pure display --
 *  server-rendered, no interactivity beyond native <details>. */

type Props = {
  layers: Layers;
  hasStaffAnalysis: boolean;
  /** Existing "what it does" summary, shown under Bill Says only as a
   *  labeled fallback -- never presented as the bill's own words. */
  fallbackSummary: string | null;
};

const BADGE_STYLE: Record<Origin, string> = {
  bill_text: "bg-slate-100 text-slate-700",
  legislative_staff: "bg-slate-100 text-slate-700",
  sunshine_ledger_ai: "bg-sunshine-100 text-sunshine-600",
};

function VersionBody({ layer, version }: { layer: LayerKey; version: LayerVersion }) {
  if (version.evidence_state === "insufficient_evidence") {
    return (
      <p className="mt-1 text-sm text-slate-600">
        <span className="font-medium">Insufficient evidence</span> — {version.scope_note}
      </p>
    );
  }
  return (
    <ul className="mt-1 space-y-2 text-sm leading-relaxed text-slate-700">
      {version.items.map((item, i) => (
        <li key={i}>
          {layer === "bill_says" && item.quote ? (
            <blockquote className="border-l-2 border-slate-300 pl-2 italic">&ldquo;{item.quote}&rdquo;</blockquote>
          ) : (
            <span>{item.text}</span>
          )}
          {item.section_ref && <span className="ml-1 text-xs text-slate-500">({item.section_ref})</span>}
          {item.assumptions.length > 0 && (
            <div className="mt-0.5 text-xs text-slate-500">
              Assumptions: {item.assumptions.join("; ")}
            </div>
          )}
          {item.affected_groups.length > 0 && (
            <div className="mt-0.5 text-xs text-slate-500">Affected groups: {item.affected_groups.join(", ")}</div>
          )}
        </li>
      ))}
    </ul>
  );
}

function Block({ layer, origin, block, hasStaffAnalysis }: {
  layer: LayerKey; origin: Origin; block: LayerBlock | undefined; hasStaffAnalysis: boolean;
}) {
  const version = block?.current ?? null;
  const review = version ? reviewLabel(origin, version) : null;
  return (
    <div className="mt-3 rounded border border-slate-200 p-3">
      <h3 className="text-xs font-medium">
        <span className={`rounded px-1.5 py-0.5 ${BADGE_STYLE[origin]}`}>{originBadge(origin, version)}</span>
        {review && (
          <span className={`ml-1.5 ${version?.review_status === "reviewed" ? "text-ledger-900" : "text-slate-500"}`}>
            · {review}
          </span>
        )}
      </h3>
      {!version ? (
        <p className="mt-1 text-sm text-slate-600">
          {origin === "legislative_staff" && !hasStaffAnalysis ? "No staff analysis published." : "Not yet evaluated."}
        </p>
      ) : (
        <>
          <VersionBody layer={layer} version={version} />
          {origin === "bill_text" && version.evidence_state === "supported" && (
            <p className="mt-1 text-[11px] text-slate-500">Quotes checked word for word against the bill text</p>
          )}
          {version.scope_note === "Drawn from the first part of a long bill" && (
            <p className="mt-1 text-[11px] text-slate-500">Drawn from the first part of a long bill</p>
          )}
          {version.sources.length > 0 && (
            <p className="mt-2 text-[11px] text-slate-500">
              Source:{" "}
              {version.sources.map((s, i) => (
                <span key={s.id}>
                  {i > 0 && "; "}
                  {s.url ? (
                    <a href={s.url} className="underline hover:text-slate-700">
                      {origin === "legislative_staff" ? "staff analysis (PDF)" : "bill text"}
                    </a>
                  ) : (
                    origin === "legislative_staff" ? "staff analysis" : "bill text"
                  )}{" "}
                  (retrieved {formatDate(s.retrieved_at)})
                </span>
              ))}
            </p>
          )}
          <p className="mt-1 text-[11px] text-slate-400">
            {version.generated_by.replace(/^llm:/, "Model: ")} · method {version.method_version} · updated{" "}
            {formatDate(version.created_at)}
          </p>
          {block && block.earlier_versions.length > 0 && (
            <details className="mt-1 text-xs text-slate-500">
              <summary className="cursor-pointer underline">
                {block.earlier_versions.length} earlier version{block.earlier_versions.length === 1 ? "" : "s"}
              </summary>
              {block.earlier_versions.map((v) => (
                <div key={v.id} className="mt-2 border-t border-slate-100 pt-1">
                  <div>
                    Version {v.version} · {formatDate(v.created_at)}
                    {v.superseded_at && <> – replaced {formatDate(v.superseded_at)}</>}
                    {reviewLabel(origin, v) && <> · {reviewLabel(origin, v)}</>}
                  </div>
                  <VersionBody layer={layer} version={v} />
                </div>
              ))}
            </details>
          )}
        </>
      )}
    </div>
  );
}

export default function BillLayers({ layers, hasStaffAnalysis, fallbackSummary }: Props) {
  return (
    <>
      {LAYER_ORDER.map((layer) => {
        const meta = LAYER_META[layer];
        const headingId = `layer-${layer}`;
        const says = layer === "bill_says" ? layers.bill_says[0]?.current : undefined;
        const showFallback =
          layer === "bill_says" && fallbackSummary && (!says || says.evidence_state === "insufficient_evidence");
        return (
          <section key={layer} aria-labelledby={headingId} className="mt-5">
            <h2 id={headingId} className="text-sm font-semibold text-ledger-900">{meta.title}</h2>
            <p className="text-xs text-slate-500">{meta.definition}</p>
            {ORIGINS_FOR_LAYER[layer].map((origin) => (
              <Block
                key={origin}
                layer={layer}
                origin={origin}
                block={layers[layer].find((b) => b.origin === origin)}
                hasStaffAnalysis={hasStaffAnalysis}
              />
            ))}
            {showFallback && (
              <div className="mt-2 text-sm text-slate-700">
                <p className="text-xs font-medium text-slate-500">AI summary of the official description</p>
                <p className="mt-0.5">{fallbackSummary}</p>
              </div>
            )}
          </section>
        );
      })}
    </>
  );
}
