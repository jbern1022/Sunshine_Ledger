"use client";

import { useState } from "react";
import { fetchPromiseQueue, reviewPromise, type AdminPromise, type ReviewAction } from "@/lib/api";

/** The reviewer's queue for collected promise statements: flagged first, then
 *  statements the model drafted as commitments. Credentials live in this
 *  page's memory only. Not linked from the site and kept out of search. */
export default function AdminPromisesPage() {
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [items, setItems] = useState<AdminPromise[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  async function load(e?: React.FormEvent) {
    e?.preventDefault();
    try {
      const q = await fetchPromiseQueue(user, pass);
      setItems(q.items);
      setTotal(q.total);
      setError(null);
    } catch (err) {
      setItems(null);
      setError((err as Error).message === "unauthorized" ? "Wrong username or password." : "The queue couldn't be loaded.");
    }
  }

  async function act(id: string, action: ReviewAction) {
    try {
      await reviewPromise(user, pass, id, { action, note: notes[id] || undefined });
      await load();
    } catch {
      setError("The action couldn't be saved.");
    }
  }

  const input = "mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm";
  const btn = "rounded-md border border-slate-300 px-2.5 py-1 text-xs hover:border-slate-500";

  return (
    <article>
      <meta name="robots" content="noindex,nofollow" />
      <h1 className="text-2xl font-bold text-ledger-900">Review promise statements</h1>
      {items === null ? (
        <form onSubmit={load} className="mt-4 max-w-sm space-y-3">
          <label className="block text-sm font-medium text-slate-700">Username
            <input className={input} value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" />
          </label>
          <label className="block text-sm font-medium text-slate-700">Password
            <input className={input} type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="current-password" />
          </label>
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <button type="submit" className="rounded-md bg-sunshine-500 px-3 py-1.5 text-sm font-medium text-ledger-900">Open queue</button>
        </form>
      ) : (
        <>
          <p className="mt-1 text-sm text-slate-600">{total} waiting, highest risk first.</p>
          {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
          {items.length === 0 && <p className="mt-4 text-sm text-slate-600">Nothing to review.</p>}
          <ul className="mt-4 space-y-4">
            {items.map((i) => (
              <li key={i.id} className="rounded-md border border-slate-200 p-3">
                <p className="text-xs text-slate-500">
                  {i.official.name} · {i.official.chamber} district {i.official.district} · {i.review_label}
                  {i.flag_count > 0 ? ` · ${i.flag_count} flag(s)` : ""}
                </p>
                <blockquote className="mt-1 border-l-4 border-sunshine-400 pl-3 text-sm text-slate-900">{i.quote}</blockquote>
                <p className="mt-1 text-xs">
                  <a href={i.source_url} className="text-sunshine-700 underline" rel="noopener noreferrer">Source</a>
                  {" · saved "}{new Date(i.snapshot.fetched_at).toLocaleDateString("en-US")}
                  {i.automated_labels.commitment_type ? ` · automated draft: ${i.automated_labels.commitment_type}` : ""}
                </p>
                {i.open_flags.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-xs text-amber-900">
                    {i.open_flags.map((f, n) => <li key={n}>{f}</li>)}
                  </ul>
                )}
                <label className="mt-2 block text-xs font-medium text-slate-600">Note (kept with the action)
                  <input className={input} value={notes[i.id] ?? ""} onChange={(e) => setNotes({ ...notes, [i.id]: e.target.value })} />
                </label>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <button className={btn} onClick={() => act(i.id, "approve")}>Approve</button>
                  <button className={btn} onClick={() => act(i.id, "reject")}>Reject</button>
                  <button className={btn} onClick={() => act(i.id, "not_a_commitment")}>Not a commitment</button>
                  {i.review_state === "flagged" && <button className={btn} onClick={() => act(i.id, "unflag")}>Dismiss flags</button>}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}
