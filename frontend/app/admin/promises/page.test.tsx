import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({ fetchPromiseQueue: vi.fn(), reviewPromise: vi.fn() }));
import * as api from "@/lib/api";
import AdminPromisesPage from "./page";

const item = {
  id: "p1", quote: "I will cut property taxes for every homeowner.", source_url: "https://jane.example/", review_state: "flagged",
  review_label: "Flagged - under review", flag_count: 2, open_flags: ["Not what the page says"],
  automated_labels: { commitment_type: "commitment" }, official: { name: "Jane Smith", chamber: "house", district: 3 },
  snapshot: { fetched_at: "2026-11-10T12:00:00Z", content_hash: "a".repeat(64) },
};

async function signIn() {
  const user = userEvent.setup();
  render(<AdminPromisesPage />);
  await user.type(screen.getByLabelText("Username"), "joe");
  await user.type(screen.getByLabelText("Password"), "secret");
  await user.click(screen.getByRole("button", { name: "Open queue" }));
  return user;
}

describe("AdminPromisesPage", () => {
  beforeEach(() => vi.resetAllMocks());

  it("opens the queue with the credentials typed and shows the statement, its flags and the draft label", async () => {
    vi.mocked(api.fetchPromiseQueue).mockResolvedValue({ total: 1, items: [item] });
    await signIn();
    expect(api.fetchPromiseQueue).toHaveBeenCalledWith("joe", "secret");
    expect(await screen.findByText("I will cut property taxes for every homeowner.")).toBeInTheDocument();
    expect(screen.getByText("Not what the page says")).toBeInTheDocument();
    expect(screen.getByText(/automated draft: commitment/)).toBeInTheDocument();
    expect(screen.getByText(/1 waiting, highest risk first/)).toBeInTheDocument();
  });

  it("says a wrong password is wrong and stays on the form", async () => {
    vi.mocked(api.fetchPromiseQueue).mockRejectedValue(new Error("unauthorized"));
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong username or password.");
    expect(screen.getByRole("button", { name: "Open queue" })).toBeInTheDocument();
  });

  it("records an action with the note and reloads the queue", async () => {
    vi.mocked(api.fetchPromiseQueue).mockResolvedValueOnce({ total: 1, items: [item] }).mockResolvedValueOnce({ total: 0, items: [] });
    vi.mocked(api.reviewPromise).mockResolvedValue(undefined);
    const user = await signIn();
    await user.type(await screen.findByLabelText(/note/i), "Guest post");
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(api.reviewPromise).toHaveBeenCalledWith("joe", "secret", "p1", { action: "reject", note: "Guest post" }));
    expect(await screen.findByText("Nothing to review.")).toBeInTheDocument();
  });
});
