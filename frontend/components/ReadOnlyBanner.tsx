import { t } from "@/lib/i18n";

/** Shown on the pilot-light standby (Todoist 6j59gqHcC3fFqR5p), whose API
 *  answers every write with 503 (backend app/read_only.py). Set at build time
 *  with NEXT_PUBLIC_READ_ONLY=true on the standby only. */
export const READ_ONLY = process.env.NEXT_PUBLIC_READ_ONLY === "true";

export default function ReadOnlyBanner({ enabled = READ_ONLY }: { enabled?: boolean }) {
  if (!enabled) return null;
  return (
    <div role="status" className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900">
      {t("readOnly.banner")}
    </div>
  );
}
