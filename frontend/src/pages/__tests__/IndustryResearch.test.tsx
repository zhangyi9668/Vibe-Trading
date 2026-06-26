import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { IndustryResearch } from "@/pages/IndustryResearch";

vi.mock("@/lib/api", () => ({
  api: { getIndustries: vi.fn().mockResolvedValue({ industries: Array.from({ length: 13 }, (_, index) => ({ slug: `industry-${index}`, name: `行业 ${index}`, summary: "研究框架", refreshable: index < 3 })) }) },
}));

it("renders every industry as an entry card without a search control", async () => {
  render(<MemoryRouter><IndustryResearch /></MemoryRouter>);

  expect(await screen.findByText("行业 12")).toBeInTheDocument();
  expect(screen.getAllByRole("link")).toHaveLength(13);
  expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
});
