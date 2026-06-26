export interface ReportTable {
  headers: string[];
  rows: string[][];
}

export interface IndustryReportDashboard {
  date: string | null;
  conclusion: string;
  allocation: ReportTable;
  review: ReportTable;
  chain: ReportTable;
  companies: ReportTable;
  opportunities: ReportTable;
  triggers: { falsify: string[]; add: string[]; reduce: string[] };
}

function emptyTable(): ReportTable {
  return { headers: [], rows: [] };
}

function cleanCell(cell: string): string {
  return cell.trim().replace(/\*\*/g, "");
}

function parseTable(section: string): ReportTable {
  const lines = section.split("\n");
  const start = lines.findIndex((line, index) => line.trim().startsWith("|") && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1]?.trim() ?? ""));
  if (start < 0) return emptyTable();
  const toCells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map(cleanCell);
  const headers = toCells(lines[start]);
  const rows: string[][] = [];
  for (let index = start + 2; index < lines.length && lines[index].trim().startsWith("|"); index += 1) rows.push(toCells(lines[index]));
  return { headers, rows };
}

function section(report: string, name: string): string {
  const headings = [...report.matchAll(/^##\s+(.+)$/gm)];
  const start = headings.find((match) => match[1].includes(name));
  if (!start?.index) return "";
  const next = headings.find((match) => match.index! > start.index!);
  return report.slice(start.index + start[0].length, next?.index).trim();
}

function introduction(content: string): string {
  return content.split(/\n\s*\n/).find((part) => part.trim() && !part.trim().startsWith("|") && !part.trim().startsWith("最终组合结构"))?.trim() ?? "";
}

function listAfter(content: string, label: string): string[] {
  const start = content.indexOf(label);
  if (start < 0) return [];
  const next = content.slice(start + label.length).search(/\n(?:证伪条件|加仓触发器|降仓触发器)：/);
  const block = content.slice(start + label.length, next < 0 ? undefined : start + label.length + next);
  return [...block.matchAll(/^\s*\d+\.\s+(.+)$/gm)].map((match) => match[1].trim());
}

export function analyzeIndustryReport(report: string): IndustryReportDashboard {
  const conclusionSection = section(report, "核心结论");
  const triggerSection = section(report, "证伪条件与加减仓触发器");
  return {
    date: report.match(/日期：\s*(\d{4}-\d{2}-\d{2})/)?.[1] ?? null,
    conclusion: introduction(conclusionSection),
    allocation: parseTable(conclusionSection),
    review: parseTable(section(report, "Vibe Trading团队审查")),
    chain: parseTable(section(report, "产业链分层")),
    companies: parseTable(section(report, "公司映射与梯队")),
    opportunities: parseTable(section(report, "投资机会排序与组合")),
    triggers: {
      falsify: listAfter(triggerSection, "证伪条件："),
      add: listAfter(triggerSection, "加仓触发器："),
      reduce: listAfter(triggerSection, "降仓触发器："),
    },
  };
}
