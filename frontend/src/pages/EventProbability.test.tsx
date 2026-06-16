import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EventProbability } from "@/pages/EventProbability";
import type {
  ProbabilityOverview,
  ProbabilityRefreshState,
} from "@/lib/api";

const overview = {
  as_of: "2026-06-14T00:00:00Z",
  events: [
    {
      question: "Who will win the 2028 Democratic presidential nomination?",
      question_zh: "谁会赢得 2028 年民主党总统提名？",
      topic: "political_elections",
      outcomes: [],
      prices: [],
      prob_yes: null,
      pick_label: null,
      change_24h: null,
      change_7d: null,
      volume_24h: 4200000,
      liquidity: 1600000,
      end_date: "2028-08-20",
      slug: "democratic-nomination-2028",
      series_ticker: null,
      token_id_yes: null,
      event_id: "polymarket-parent-dem-2028",
      source: "polymarket",
      source_category: "Politics",
      results: [
        {
          label: "Candidate E",
          label_zh: "候选人 E",
          probability: 0.27,
          change_24h: 0.02,
          volume_24h: 500000,
          token_id: "winner-e",
        },
        {
          label: "Candidate B",
          label_zh: "候选人 B",
          probability: 0.31,
          change_24h: -0.01,
          volume_24h: 900000,
          token_id: "winner-b",
        },
        {
          label: "Candidate F",
          label_zh: "候选人 F",
          probability: 0.06,
          change_24h: -0.03,
          volume_24h: 100000,
          token_id: "winner-f",
        },
        {
          label: "Candidate A",
          label_zh: "候选人 A",
          probability: 0.38,
          change_24h: 0.04,
          volume_24h: 1200000,
          token_id: "winner-a",
        },
        {
          label: "Candidate C",
          label_zh: "候选人 C",
          probability: 0.19,
          change_24h: 0,
          volume_24h: 750000,
          token_id: "winner-c",
        },
        {
          label: "Candidate D",
          label_zh: "候选人 D",
          probability: 0.12,
          change_24h: -0.02,
          volume_24h: 600000,
          token_id: null,
        },
      ],
    },
    {
      question: "Will the Fed cut rates?",
      question_zh: "美联储会降息吗？",
      topic: "monetary_policy",
      outcomes: ["Yes", "No"],
      prices: [0.62, 0.38],
      prob_yes: 0.62,
      pick_label: "Yes",
      change_24h: 0.03,
      change_7d: 0.04,
      volume_24h: 120000,
      liquidity: 400000,
      end_date: "2026-09-18",
      slug: "fed-cut",
      series_ticker: null,
      token_id_yes: "fed-yes",
      event_id: null,
      source: "polymarket",
      source_category: "Economy",
      results: [],
    },
    {
      question: "Will CPI cool this month?",
      question_zh: "CPI 本月会回落吗？",
      topic: "macro_economy",
      outcomes: ["Yes", "No"],
      prices: [0.55, 0.45],
      prob_yes: 0.55,
      pick_label: null,
      change_24h: -0.02,
      change_7d: -0.01,
      volume_24h: 90000,
      liquidity: 100000,
      end_date: null,
      slug: "cpi-cool",
      series_ticker: "KXCPI",
      token_id_yes: null,
      event_id: null,
      source: "kalshi",
      source_category: "Economics",
      results: [],
    },
    {
      question: "OpenAI release this quarter?",
      question_zh: null,
      topic: "ai_technology",
      outcomes: ["Yes", "No"],
      prices: [0.44, 0.56],
      prob_yes: 0.44,
      pick_label: null,
      change_24h: 0.0,
      change_7d: 0.0,
      volume_24h: 5000,
      liquidity: 9000,
      end_date: null,
      slug: "openai-release",
      series_ticker: null,
      token_id_yes: null,
      event_id: null,
      source: "kalshi",
      source_category: "Science and Technology",
      results: [],
    },
  ],
  sources: [],
  translation_cache_size: 2,
  refresh: {
    status: "idle",
    kind: null,
    stage: null,
    progress_current: 0,
    progress_total: 0,
    started_at: null,
    finished_at: null,
    error: null,
    translation: { new_translations: 0, cache_hits: 0, pending: 0 },
  },
} as ProbabilityOverview;

let statusQueue: ProbabilityRefreshState[] = [];

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getEventProbabilityOverview: vi.fn<() => Promise<ProbabilityOverview>>(),
    startEventProbabilityRefresh: vi.fn<
      (kind: "quick" | "full") => Promise<ProbabilityRefreshState>
    >(),
    getEventProbabilityRefreshStatus: vi.fn<() => Promise<ProbabilityRefreshState>>(),
    getEventProbabilityHistory: vi.fn<
      (tokenId: string) => Promise<Array<{ t: number; p: number }>>
    >(),
  },
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

vi.mock("@/components/charts/ProbabilityTrend", () => ({
  ProbabilityTrend: ({
    series,
  }: {
    series: Array<{ label: string; token_id: string }>;
  }) => <div data-testid="probability-trend">{JSON.stringify(series)}</div>,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <EventProbability />
    </MemoryRouter>,
  );
}

describe("EventProbability", () => {
  beforeEach(() => {
    statusQueue = [];
    apiMock.getEventProbabilityOverview.mockResolvedValue(overview);
    apiMock.startEventProbabilityRefresh.mockImplementation(async () => ({
      status: "queued",
      kind: "quick",
      stage: "fetching_polymarket",
      progress_current: 0,
      progress_total: 0,
      started_at: null,
      finished_at: null,
      error: null,
      translation: { new_translations: 0, cache_hits: 0, pending: 0 },
    }));
    apiMock.getEventProbabilityRefreshStatus.mockImplementation(async () => {
      return (
        statusQueue.shift() ?? {
          status: "done",
          kind: "quick",
          stage: "saving",
          progress_current: 0,
          progress_total: 0,
          started_at: null,
          finished_at: null,
          error: null,
          translation: { new_translations: 0, cache_hits: 0, pending: 0 },
        }
      );
    });
    apiMock.getEventProbabilityHistory.mockResolvedValue([
      { t: 1, p: 0.62 },
      { t: 2, p: 0.64 },
    ]);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    cleanup();
  });

  it("renders the highest-volume default topic with chinese titles", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "货币政策" }),
    ).toBeTruthy();
    expect(screen.getByText("美联储会降息吗？")).toBeTruthy();
    expect(screen.getByText("Will the Fed cut rates?")).toBeTruthy();
    expect(screen.queryByText("CPI 本月会回落吗？")).toBeNull();
    expect(screen.queryByText("OpenAI release this quarter?")).toBeNull();
  });

  it("switches topics with the top tab buttons", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("美联储会降息吗？");

    await user.click(screen.getByRole("button", { name: "宏观经济" }));
    expect(screen.getByText("CPI 本月会回落吗？")).toBeTruthy();
    expect(screen.queryByText("美联储会降息吗？")).toBeNull();

    await user.click(screen.getByRole("button", { name: "AI 科技" }));
    expect(screen.getByText("OpenAI release this quarter?")).toBeTruthy();
  });

  it("renders one grouped polymarket parent card with the top five results by volume", async () => {
    const { container } = renderPage();
    const user = userEvent.setup();
    await screen.findByText("美联储会降息吗？");

    await user.click(screen.getByRole("button", { name: "政治选举" }));

    expect(
      screen.getAllByText("谁会赢得 2028 年民主党总统提名？"),
    ).toHaveLength(1);
    expect(
      screen.getByText("Who will win the 2028 Democratic presidential nomination?"),
    ).toBeTruthy();
    expect(container.querySelectorAll("article")).toHaveLength(1);

    const text = container.textContent ?? "";
    const orderedLabels = ["候选人 A", "候选人 B", "候选人 C", "候选人 D", "候选人 E"];
    for (const label of orderedLabels) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(text.indexOf("候选人 A")).toBeLessThan(text.indexOf("候选人 B"));
    expect(text.indexOf("候选人 B")).toBeLessThan(text.indexOf("候选人 C"));
    expect(text.indexOf("候选人 C")).toBeLessThan(text.indexOf("候选人 D"));
    expect(text.indexOf("候选人 D")).toBeLessThan(text.indexOf("候选人 E"));
    expect(screen.queryByText("候选人 F")).toBeNull();

    for (const label of ["Candidate A", "Candidate B", "Candidate C", "Candidate D", "Candidate E"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(screen.queryByText("Candidate F")).toBeNull();

    for (const value of ["38.0%", "31.0%", "19.0%", "12.0%", "27.0%"]) {
      expect(screen.getByText(value)).toBeTruthy();
    }
    for (const value of ["+4.0%", "-1.0%", "0.0%", "-2.0%", "+2.0%"]) {
      expect(screen.getByText(value)).toBeTruthy();
    }
    for (const value of ["120万", "90万", "75万", "60万", "50万"]) {
      expect(screen.getByText(value)).toBeTruthy();
    }
  });

  it("passes grouped polymarket result series to the trend chart", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("美联储会降息吗？");

    await user.click(screen.getByRole("button", { name: "政治选举" }));

    const series = JSON.parse(screen.getByTestId("probability-trend").textContent ?? "[]");
    expect(series).toEqual([
      { label: "候选人 A", token_id: "winner-a" },
      { label: "候选人 B", token_id: "winner-b" },
      { label: "候选人 C", token_id: "winner-c" },
      { label: "候选人 E", token_id: "winner-e" },
    ]);
    expect(screen.getByText("候选人 D")).toBeTruthy();
    expect(JSON.stringify(series)).not.toContain("候选人 D");
  });

  it("filters the selected topic by keyword, source and absolute change", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("美联储会降息吗？");

    await user.type(screen.getByLabelText("搜索"), "Fed");
    expect(screen.getByText("美联储会降息吗？")).toBeTruthy();

    await user.selectOptions(screen.getByLabelText("来源"), "kalshi");
    expect(screen.queryByText("美联储会降息吗？")).toBeNull();

    await user.selectOptions(screen.getByLabelText("来源"), "all");
    await user.selectOptions(screen.getByLabelText("最小 24h 波动"), "0.02");
    expect(screen.getByText("美联储会降息吗？")).toBeTruthy();
  });

  it(
    "starts quick refresh and polls while keeping cached rows visible",
    async () => {
    statusQueue = [
      {
        status: "running",
        kind: "quick",
        stage: "fetching_kalshi",
        progress_current: 2,
        progress_total: 30,
        started_at: null,
        finished_at: null,
        error: null,
        translation: { new_translations: 0, cache_hits: 0, pending: 0 },
      },
      {
        status: "done",
        kind: "quick",
        stage: "saving",
        progress_current: 0,
        progress_total: 0,
        started_at: null,
        finished_at: null,
        error: null,
        translation: { new_translations: 0, cache_hits: 0, pending: 0 },
      },
    ];

    renderPage();
    await screen.findByText("美联储会降息吗？");
    vi.useFakeTimers();
      await act(async () => {
        screen.getByRole("button", { name: "快速刷新" }).click();
      });
      expect(apiMock.startEventProbabilityRefresh).toHaveBeenCalledWith("quick");
      expect(screen.getByText("美联储会降息吗？")).toBeTruthy();
      await act(async () => {});
      expect(screen.getByText("快速刷新进行中")).toBeTruthy();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1600);
      });
      expect(apiMock.getEventProbabilityRefreshStatus).toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1600);
      });
      expect(apiMock.getEventProbabilityOverview).toHaveBeenCalledTimes(2);
    },
    10000,
  );

  it("passes ungrouped polymarket as a single trend series without a toggle", async () => {
    renderPage();
    await screen.findByText("美联储会降息吗？");

    const series = JSON.parse(screen.getByTestId("probability-trend").textContent ?? "[]");
    expect(series).toEqual([{ label: "Yes", token_id: "fed-yes" }]);
    expect(screen.queryByRole("button", { name: "查看趋势" })).toBeNull();
  });

  it("renders footer disclaimer", async () => {
    renderPage();
    expect(await screen.findByText("风险温度计，不构成交易信号")).toBeTruthy();
  });
});
