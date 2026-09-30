import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TextComparison from "./TextComparison";
import * as api from "@/lib/api";
import type { TextVersions } from "@/lib/types";

vi.mock("@/lib/api", () => ({ fetchFiledText: vi.fn() }));

const versions: TextVersions = {
  filed: { version_type: "Introduced", version_date: "2026-01-09", url: "https://fl/filed.pdf", characters: 70 },
  current: { version_type: "Enrolled", version_date: "2026-03-13", url: "https://fl/er.pdf", characters: 70 },
};
const FILED = "Section 1. The fine may not exceed $1,000. Section 2. This act takes effect July 1, 2026.";
const CURRENT = "Section 1. The fine may not exceed $5,000. Section 2. This act takes effect July 1, 2026.";

describe("TextComparison", () => {
  beforeEach(() => vi.mocked(api.fetchFiledText).mockReset());

  it("stays collapsed, naming both versions, until asked", () => {
    render(<TextComparison entityId="b1" versions={versions} currentText={CURRENT} />);
    expect(screen.getByText("Filed: Introduced, 2026-01-09 · Current: Enrolled, 2026-03-13")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare the filed and current text" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(api.fetchFiledText).not.toHaveBeenCalled();
  });

  it("loads the filed text on demand and marks what changed", async () => {
    vi.mocked(api.fetchFiledText).mockResolvedValue({ ...versions.filed, text: FILED });
    const { container } = render(<TextComparison entityId="b1" versions={versions} currentText={CURRENT} />);

    await userEvent.click(screen.getByRole("button", { name: "Compare the filed and current text" }));

    expect(await screen.findByText(/of the wording changed/)).toBeInTheDocument();
    expect(api.fetchFiledText).toHaveBeenCalledWith("b1");
    expect(container.querySelector("del")?.textContent).toBe("1");
    expect(container.querySelector("ins")?.textContent).toBe("5");
    expect(screen.getAllByRole("link", { name: "filed version ↗" })[0]).toHaveAttribute("href", "https://fl/filed.pdf");
  });

  it("shows a rewrite side by side", async () => {
    vi.mocked(api.fetchFiledText).mockResolvedValue({ ...versions.filed, text: "Alpha beta gamma. Delta epsilon." });
    render(<TextComparison entityId="b1" versions={versions} currentText="Completely different words. Nothing shared." />);

    await userEvent.click(screen.getByRole("button", { name: "Compare the filed and current text" }));

    expect(await screen.findByText(/Substantially rewritten/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "As filed" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current" })).toBeInTheDocument();
  });

  it("links the official texts instead of comparing very large bills", () => {
    const big = { ...versions, current: { ...versions.current, characters: 1_600_000 } };
    render(<TextComparison entityId="b1" versions={big} currentText={CURRENT} />);
    expect(screen.queryByRole("button", { name: /compare/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Too long to compare here/)).toBeInTheDocument();
  });

  it("says so when the filed text can't be loaded", async () => {
    vi.mocked(api.fetchFiledText).mockRejectedValueOnce(new Error("500"));
    const user = userEvent.setup();
    render(<TextComparison entityId="b1" versions={versions} currentText={CURRENT} />);
    await user.click(screen.getByRole("button", { name: "Compare the filed and current text" }));
    expect(await screen.findByText(/Couldn't load the filed text/)).toBeInTheDocument();
  });
});
