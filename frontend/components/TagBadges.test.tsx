import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import TagBadges from "./TagBadges";
import type { TagOut } from "@/lib/types";

const housing: TagOut = { bill_tag_id: "bt1", slug: "housing", label: "Housing", tag_source: "legiscan", active: true };
const taxes: TagOut = { bill_tag_id: "bt2", slug: "taxes_budget", label: "Taxes/Budget", tag_source: "ollama", active: true };

describe("TagBadges", () => {
  it("renders nothing when there are no tags", () => {
    const { container } = render(<TagBadges tags={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a badge per tag, linking to the filtered browse page", () => {
    render(<TagBadges tags={[housing]} />);
    const link = screen.getByRole("link", { name: "Housing" });
    expect(link).toHaveAttribute("href", "/?tag=housing");
  });

  it("renders multiple badges", () => {
    render(<TagBadges tags={[housing, taxes]} />);
    expect(screen.getByRole("link", { name: "Housing" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Taxes/Budget" })).toBeInTheDocument();
  });
});
