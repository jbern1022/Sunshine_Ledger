import { describe, it, expect } from "vitest";
import { buildBrowseQuery, parseBrowseParams } from "./browse-params";

const p = (s: string) => new URLSearchParams(s);

describe("parseBrowseParams", () => {
  it("reads every filter and the page", () => {
    expect(parseBrowseParams(p("q=hb+1389&jurisdiction=FL&status=Passed&session=2026&tag=housing&page=3"))).toEqual({
      q: "hb 1389", jurisdiction: "FL", status: "Passed", session: "2026", tag: "housing", page: 3,
    });
  });

  it("defaults to the unfiltered first page and ignores a bad page", () => {
    expect(parseBrowseParams(p("page=abc"))).toEqual({
      q: "", jurisdiction: "", status: "", session: "", tag: "", page: 1,
    });
    expect(parseBrowseParams(p("page=-4")).page).toBe(1);
  });
});

describe("buildBrowseQuery", () => {
  it("sets a filter and returns to page 1", () => {
    expect(buildBrowseQuery(p("jurisdiction=FL&page=4"), { status: "Passed" })).toBe("jurisdiction=FL&status=Passed");
  });

  it("clears a filter set to the empty string", () => {
    expect(buildBrowseQuery(p("tag=housing&status=Passed"), { tag: "" })).toBe("status=Passed");
  });

  it("sets the page without touching filters, and omits page 1", () => {
    expect(buildBrowseQuery(p("tag=housing"), { page: 2 })).toBe("tag=housing&page=2");
    expect(buildBrowseQuery(p("tag=housing&page=2"), { page: 1 })).toBe("tag=housing");
  });

  it("keeps params it doesn't own", () => {
    expect(buildBrowseQuery(p("sponsor=abc&sponsorName=Jane+Doe&geo=Miami"), { q: "tax" })).toBe(
      "sponsor=abc&sponsorName=Jane+Doe&geo=Miami&q=tax",
    );
  });

  it("drops the auto-detected marker when the jurisdiction is chosen by hand", () => {
    expect(buildBrowseQuery(p("jurisdiction=Miami&auto=1"), { jurisdiction: "" })).toBe("");
  });
});
