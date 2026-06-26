from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


WIND_SKILL_DIR = Path("/Users/phoebe/.agents/skills/wind-mcp-skill")
WIND_CLI = WIND_SKILL_DIR / "scripts/cli.mjs"
NODE = Path(
    os.getenv(
        "VIBE_NODE",
        "/Users/phoebe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
    )
)

WIND_INDEXES = "中文简称,最新成交价,涨跌幅,成交额,总市值2,市盈率(TTM),市净率(LF)"
IFIND_INDICATORS = "latest,changeRatio,amount,totalMarketValue,pe_ttm,pb"

COMPANIES: list[dict[str, str]] = [
    {"code": "688981.SH", "ifind": "688981.SH", "name": "中芯国际", "segment": "制造/代工"},
    {"code": "688347.SH", "ifind": "688347.SH", "name": "华虹公司", "segment": "制造/代工"},
    {"code": "688249.SH", "ifind": "688249.SH", "name": "晶合集成", "segment": "制造/代工"},
    {"code": "688396.SH", "ifind": "688396.SH", "name": "华润微", "segment": "制造/代工"},
    {"code": "002371.SZ", "ifind": "002371.SZ", "name": "北方华创", "segment": "半导体设备"},
    {"code": "688012.SH", "ifind": "688012.SH", "name": "中微公司", "segment": "半导体设备"},
    {"code": "688072.SH", "ifind": "688072.SH", "name": "拓荆科技", "segment": "半导体设备"},
    {"code": "688120.SH", "ifind": "688120.SH", "name": "华海清科", "segment": "半导体设备"},
    {"code": "688082.SH", "ifind": "688082.SH", "name": "盛美上海", "segment": "半导体设备"},
    {"code": "688019.SH", "ifind": "688019.SH", "name": "安集科技", "segment": "材料/零部件"},
    {"code": "300666.SZ", "ifind": "300666.SZ", "name": "江丰电子", "segment": "材料/零部件"},
    {"code": "688126.SH", "ifind": "688126.SH", "name": "沪硅产业", "segment": "材料/零部件"},
    {"code": "688234.SH", "ifind": "688234.SH", "name": "天岳先进", "segment": "材料/零部件"},
    {"code": "688256.SH", "ifind": "688256.SH", "name": "寒武纪", "segment": "设计/IP/AI"},
    {"code": "688008.SH", "ifind": "688008.SH", "name": "澜起科技", "segment": "设计/IP/AI"},
    {"code": "603501.SH", "ifind": "603501.SH", "name": "韦尔股份", "segment": "设计/IP/AI"},
    {"code": "688521.SH", "ifind": "688521.SH", "name": "芯原股份", "segment": "设计/IP/AI"},
    {"code": "688099.SH", "ifind": "688099.SH", "name": "晶晨股份", "segment": "设计/IP/AI"},
    {"code": "600584.SH", "ifind": "600584.SH", "name": "长电科技", "segment": "封测/先进封装"},
    {"code": "002156.SZ", "ifind": "002156.SZ", "name": "通富微电", "segment": "封测/先进封装"},
    {"code": "002185.SZ", "ifind": "002185.SZ", "name": "华天科技", "segment": "封测/先进封装"},
    {"code": "688362.SH", "ifind": "688362.SH", "name": "甬矽电子", "segment": "封测/先进封装"},
    {"code": "301269.SZ", "ifind": "301269.SZ", "name": "华大九天", "segment": "EDA/FPGA"},
    {"code": "688206.SH", "ifind": "688206.SH", "name": "概伦电子", "segment": "EDA/FPGA"},
    {"code": "688107.SH", "ifind": "688107.SH", "name": "安路科技", "segment": "EDA/FPGA"},
]

INDUSTRIES: list[dict[str, str | bool]] = [
    {"slug": "semiconductor", "name": "半导体国产替代", "summary": "制造、设备、材料、设计、封测和 EDA。", "refreshable": True},
    {"slug": "ai-data-center", "name": "AI 算力与数据中心", "summary": "光模块、交换机、液冷、服务器与 IDC。", "refreshable": True},
    {"slug": "innovative-drugs", "name": "创新药出海", "summary": "研发管线、BD 授权、临床读出与商业化。", "refreshable": True},
    {"slug": "embodied-ai", "name": "人形机器人与具身智能", "summary": "核心零部件、整机与场景落地。", "refreshable": True},
    {"slug": "low-altitude", "name": "低空经济", "summary": "飞行器、空域和基础设施。", "refreshable": True},
    {"slug": "commercial-space", "name": "商业航天与卫星互联网", "summary": "火箭、卫星与地面站。", "refreshable": True},
    {"slug": "defense", "name": "国防军工与无人化装备", "summary": "装备升级与无人系统。", "refreshable": True},
    {"slug": "power-storage", "name": "新能源发电电网储能", "summary": "电力系统与新型储能。", "refreshable": True},
    {"slug": "smart-auto", "name": "新能源车与智能汽车", "summary": "三电、智能化与零部件。", "refreshable": True},
    {"slug": "synthetic-bio", "name": "生物制造与合成生物", "summary": "平台能力与规模化成本。", "refreshable": True},
    {"slug": "metals", "name": "资源与电力金属", "summary": "供需平衡、成本曲线与价格弹性。", "refreshable": True},
    {"slug": "silver-economy", "name": "银发经济与医疗器械服务", "summary": "医疗服务、器械渗透与人口结构。", "refreshable": True},
    {"slug": "machine-tools", "name": "高端制造母机", "summary": "工业母机与核心零部件。", "refreshable": True},
]

INDUSTRY_COMPANIES: dict[str, list[dict[str, str]]] = {
    "semiconductor": COMPANIES,
    "ai-data-center": [
        {"code": "300308.SZ", "ifind": "300308.SZ", "name": "中际旭创", "segment": "光模块"},
        {"code": "000977.SZ", "ifind": "000977.SZ", "name": "浪潮信息", "segment": "服务器"},
        {"code": "000938.SZ", "ifind": "000938.SZ", "name": "紫光股份", "segment": "交换机"},
    ],
    "innovative-drugs": [
        {"code": "600276.SH", "ifind": "600276.SH", "name": "恒瑞医药", "segment": "创新药"},
        {"code": "300760.SZ", "ifind": "300760.SZ", "name": "迈瑞医疗", "segment": "医疗器械"},
        {"code": "688180.SH", "ifind": "688180.SH", "name": "君实生物", "segment": "创新药"},
    ],
    "embodied-ai": [
        {"code": "688017.SH", "ifind": "688017.SH", "name": "绿的谐波", "segment": "精密传动"},
        {"code": "003021.SZ", "ifind": "003021.SZ", "name": "兆威机电", "segment": "执行器"},
        {"code": "603728.SH", "ifind": "603728.SH", "name": "鸣志电器", "segment": "电机"},
        {"code": "300124.SZ", "ifind": "300124.SZ", "name": "汇川技术", "segment": "控制器/伺服"},
        {"code": "601689.SH", "ifind": "601689.SH", "name": "拓普集团", "segment": "结构件"},
    ],
    "low-altitude": [
        {"code": "300012.SZ", "ifind": "300012.SZ", "name": "华测检测", "segment": "检测认证"},
        {"code": "002967.SZ", "ifind": "002967.SZ", "name": "广电计量", "segment": "检测认证"},
        {"code": "002179.SZ", "ifind": "002179.SZ", "name": "中航光电", "segment": "机载配套"},
        {"code": "688522.SH", "ifind": "688522.SH", "name": "纳睿雷达", "segment": "低空感知"},
        {"code": "000099.SZ", "ifind": "000099.SZ", "name": "中信海直", "segment": "通航运营"},
    ],
    "commercial-space": [
        {"code": "300627.SZ", "ifind": "300627.SZ", "name": "华测导航", "segment": "北斗应用"},
        {"code": "688375.SH", "ifind": "688375.SH", "name": "国博电子", "segment": "星载射频"},
        {"code": "688333.SH", "ifind": "688333.SH", "name": "铂力特", "segment": "航天制造"},
        {"code": "001270.SZ", "ifind": "001270.SZ", "name": "铖昌科技", "segment": "星载芯片"},
        {"code": "600118.SH", "ifind": "600118.SH", "name": "中国卫星", "segment": "卫星制造"},
    ],
    "defense": [
        {"code": "600760.SH", "ifind": "600760.SH", "name": "中航沈飞", "segment": "航空整机"},
        {"code": "600893.SH", "ifind": "600893.SH", "name": "航发动力", "segment": "航空发动机"},
        {"code": "000768.SZ", "ifind": "000768.SZ", "name": "中航西飞", "segment": "航空整机"},
        {"code": "688297.SH", "ifind": "688297.SH", "name": "中无人机", "segment": "无人机"},
        {"code": "002025.SZ", "ifind": "002025.SZ", "name": "航天电器", "segment": "军工电子"},
    ],
    "power-storage": [
        {"code": "300274.SZ", "ifind": "300274.SZ", "name": "阳光电源", "segment": "光伏逆变器"},
        {"code": "300750.SZ", "ifind": "300750.SZ", "name": "宁德时代", "segment": "储能电池"},
        {"code": "600406.SH", "ifind": "600406.SH", "name": "国电南瑞", "segment": "电网自动化"},
        {"code": "605117.SH", "ifind": "605117.SH", "name": "德业股份", "segment": "储能逆变器"},
        {"code": "300827.SZ", "ifind": "300827.SZ", "name": "上能电气", "segment": "储能变流器"},
    ],
    "smart-auto": [
        {"code": "002594.SZ", "ifind": "002594.SZ", "name": "比亚迪", "segment": "整车/三电"},
        {"code": "300750.SZ", "ifind": "300750.SZ", "name": "宁德时代", "segment": "动力电池"},
        {"code": "601127.SH", "ifind": "601127.SH", "name": "赛力斯", "segment": "智能汽车"},
        {"code": "002920.SZ", "ifind": "002920.SZ", "name": "德赛西威", "segment": "智能座舱"},
        {"code": "601689.SH", "ifind": "601689.SH", "name": "拓普集团", "segment": "智能汽车零部件"},
    ],
    "synthetic-bio": [
        {"code": "688065.SH", "ifind": "688065.SH", "name": "凯赛生物", "segment": "生物基材料"},
        {"code": "688639.SH", "ifind": "688639.SH", "name": "华恒生物", "segment": "生物发酵"},
        {"code": "600873.SH", "ifind": "600873.SH", "name": "梅花生物", "segment": "氨基酸"},
        {"code": "301301.SZ", "ifind": "301301.SZ", "name": "川宁生物", "segment": "合成生物"},
        {"code": "600789.SH", "ifind": "600789.SH", "name": "鲁抗医药", "segment": "生物制造"},
    ],
    "metals": [
        {"code": "601899.SH", "ifind": "601899.SH", "name": "紫金矿业", "segment": "铜金资源"},
        {"code": "603993.SH", "ifind": "603993.SH", "name": "洛阳钼业", "segment": "铜钴资源"},
        {"code": "601600.SH", "ifind": "601600.SH", "name": "中国铝业", "segment": "铝"},
        {"code": "000792.SZ", "ifind": "000792.SZ", "name": "盐湖股份", "segment": "锂钾"},
        {"code": "600111.SH", "ifind": "600111.SH", "name": "北方稀土", "segment": "稀土"},
    ],
    "silver-economy": [
        {"code": "300760.SZ", "ifind": "300760.SZ", "name": "迈瑞医疗", "segment": "医疗器械"},
        {"code": "002223.SZ", "ifind": "002223.SZ", "name": "鱼跃医疗", "segment": "家用器械"},
        {"code": "300015.SZ", "ifind": "300015.SZ", "name": "爱尔眼科", "segment": "医疗服务"},
        {"code": "600763.SH", "ifind": "600763.SH", "name": "通策医疗", "segment": "医疗服务"},
        {"code": "301087.SZ", "ifind": "301087.SZ", "name": "可孚医疗", "segment": "家用器械"},
    ],
    "machine-tools": [
        {"code": "601882.SH", "ifind": "601882.SH", "name": "海天精工", "segment": "高端整机"},
        {"code": "688305.SH", "ifind": "688305.SH", "name": "科德数控", "segment": "五轴机床"},
        {"code": "688059.SH", "ifind": "688059.SH", "name": "华锐精密", "segment": "刀具耗材"},
        {"code": "300124.SZ", "ifind": "300124.SZ", "name": "汇川技术", "segment": "工控伺服"},
        {"code": "300161.SZ", "ifind": "300161.SZ", "name": "华中数控", "segment": "数控系统"},
    ],
}

REPORT_FOLDERS = {
    "semiconductor": "半导体国产替代框架", "ai-data-center": "AI算力与数据中心框架", "innovative-drugs": "创新药出海框架", "embodied-ai": "人形机器人与具身智能框架", "low-altitude": "低空经济框架", "commercial-space": "商业航天与卫星互联网框架", "defense": "国防军工与无人化装备框架", "power-storage": "新能源发电电网储能框架", "smart-auto": "新能源车与智能汽车框架", "synthetic-bio": "生物制造与合成生物框架", "metals": "资源与电力金属框架", "silver-economy": "银发经济与医疗器械服务框架", "machine-tools": "高端制造母机框架",
}

_DOTENV_LOADED = False
_AGENT_DIR = Path(__file__).resolve().parents[2]
_SOURCE_DIR = _AGENT_DIR.parent
_WORKSPACE_DIR = _SOURCE_DIR.parent


def _ensure_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        load_dotenv = None
    for candidate in (
        Path.home() / ".vibe-trading" / ".env",
        _AGENT_DIR / ".env",
        _SOURCE_DIR / ".env",
        _WORKSPACE_DIR / ".env",
        Path.cwd() / ".env",
    ):
        if not candidate.exists():
            continue
        if load_dotenv is not None:
            load_dotenv(dotenv_path=candidate, override=False)
        else:
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key:
                    os.environ.setdefault(key, value.strip().strip('"').strip("'"))
    _DOTENV_LOADED = True


def parse_number(value: Any) -> float | None:
    if value in (None, "", "--", "nan"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except ValueError:
        return None


class SemiconductorQuoteService:
    def __init__(self, companies: list[dict[str, str]] | None = None) -> None:
        _ensure_dotenv()
        self.companies = companies or COMPANIES

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "wind_cli": WIND_CLI.exists(),
            "ifind_configured": self.ifind_configured(),
        }

    def industries(self) -> list[dict[str, str | bool]]:
        return INDUSTRIES

    def fetch_industry(self, slug: str) -> dict[str, Any]:
        if slug not in INDUSTRY_COMPANIES:
            raise ValueError("该行业暂未接入可刷新数据")
        payload = SemiconductorQuoteService(companies=INDUSTRY_COMPANIES[slug]).fetch_all()
        return {"industry": slug, **payload}

    def report(self, slug: str) -> dict[str, str]:
        folder = REPORT_FOLDERS.get(slug)
        if not folder:
            raise ValueError("未找到行业研究报告")
        root = Path(__file__).resolve().parents[4] / "行业研究框架" / folder
        reports = sorted(root.glob("*框架统一版.md"))
        if not reports:
            raise ValueError("行业研究报告文件不存在")
        return {"industry": slug, "content": reports[0].read_text(encoding="utf-8")}

    def ifind_configured(self) -> bool:
        return bool(os.getenv("IFIND_ACCESS_TOKEN") or os.getenv("IFIND_REFRESH_TOKEN"))

    def source_order(self) -> list[str]:
        return ["ifind", "wind"] if self.ifind_configured() else ["wind", "ifind"]

    def call_wind(self, company: dict[str, str]) -> dict[str, Any]:
        if not WIND_CLI.exists() or not NODE.exists():
            raise RuntimeError("Wind CLI 或 Node 运行时不存在")
        params = {"windcode": company["code"], "indexes": WIND_INDEXES}
        result = subprocess.run(
            [
                str(NODE),
                str(WIND_CLI),
                "call",
                "stock_data",
                "get_stock_price_indicators",
                json.dumps(params, ensure_ascii=False),
            ],
            cwd=WIND_SKILL_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stdout or result.stderr).strip()[:300])
        outer = json.loads(result.stdout)
        if outer.get("isError"):
            raise RuntimeError(str(outer)[:300])
        inner = json.loads(outer["content"][0]["text"])
        if inner.get("error"):
            raise RuntimeError(str(inner["error"])[:300])
        data = inner.get("data") or {}
        columns = [item["name"] for item in data.get("columns", [])]
        rows = data.get("rows") or []
        if not rows:
            raise RuntimeError("Wind 返回空数据")
        row = dict(zip(columns, rows[0]))
        return {
            "code": company["code"],
            "name": row.get("中文简称") or company["name"],
            "segment": company["segment"],
            "price": parse_number(row.get("最新成交价")),
            "change_pct": parse_number(row.get("涨跌幅")),
            "amount": parse_number(row.get("成交额")),
            "market_cap": parse_number(row.get("总市值2")),
            "pe_ttm": parse_number(row.get("市盈率(TTM)")),
            "pb": parse_number(row.get("市净率(LF)")),
            "source": "Wind",
            "error": None,
        }

    def get_ifind_token(self, force_refresh: bool = False) -> str:
        access_token = os.getenv("IFIND_ACCESS_TOKEN")
        if access_token and not force_refresh:
            return access_token
        refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError("iFinD Token 未配置")
        base = os.getenv("IFIND_BASE_URL", "https://quantapi.51ifind.com/api/v1").rstrip("/")
        request = urllib.request.Request(
            f"{base}/get_access_token",
            method="POST",
            headers={"Content-Type": "application/json", "refresh_token": refresh_token},
            data=b"{}",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        token = (payload.get("data") or {}).get("access_token")
        if not token:
            raise RuntimeError("iFinD 无法取得 access_token")
        os.environ["IFIND_ACCESS_TOKEN"] = str(token)
        return str(token)

    def _ifind_post(self, body: dict[str, Any]) -> dict[str, Any]:
        base = os.getenv("IFIND_BASE_URL", "https://quantapi.51ifind.com/api/v1").rstrip("/")
        data = json.dumps(body).encode("utf-8")
        token = self.get_ifind_token()
        request = urllib.request.Request(
            f"{base}/real_time_quotation",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "access_token": token,
                "ifindlang": "cn",
            },
            data=data,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            token = self.get_ifind_token(force_refresh=True)
            retry = urllib.request.Request(
                f"{base}/real_time_quotation",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "access_token": token,
                    "ifindlang": "cn",
                },
                data=data,
            )
            with urllib.request.urlopen(retry, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))

    def _ifind_payload_to_row(self, company: dict[str, str], row: dict[str, Any]) -> dict[str, Any]:
        table = row.get("table")
        if isinstance(table, dict):
            normalized = dict(row)
            for key, value in table.items():
                normalized[key] = value[0] if isinstance(value, list) and value else value
            row = normalized
        return {
            "code": company["code"],
            "name": company["name"],
            "segment": company["segment"],
            "price": parse_number(row.get("latest")),
            "change_pct": parse_number(row.get("changeRatio")),
            "amount": parse_number(row.get("amount")),
            "market_cap": parse_number(row.get("totalMarketValue")),
            "pe_ttm": parse_number(row.get("pe_ttm")),
            "pb": parse_number(row.get("pb")),
            "source": "iFinD",
            "error": None,
        }

    def call_ifind(self, company: dict[str, str]) -> dict[str, Any]:
        payload = self._ifind_post({"codes": company["ifind"], "indicators": IFIND_INDICATORS})
        if payload.get("errorcode") not in (0, "0", None):
            raise RuntimeError(payload.get("errmsg") or "iFinD 返回错误")
        tables = payload.get("tables") or []
        if not tables:
            raise RuntimeError("iFinD 返回空数据")
        return self._ifind_payload_to_row(company, tables[0])

    def call_ifind_batch(self, companies: list[dict[str, str]]) -> list[dict[str, Any]]:
        payload = self._ifind_post(
            {
                "codes": ",".join(company["ifind"] for company in companies),
                "indicators": IFIND_INDICATORS,
            }
        )
        if payload.get("errorcode") not in (0, "0", None):
            raise RuntimeError(payload.get("errmsg") or "iFinD 返回错误")
        tables = payload.get("tables") or []
        if not tables:
            raise RuntimeError("iFinD 返回空数据")
        by_code = {
            str(row.get("thscode") or row.get("code") or row.get("stockcode") or ""): row
            for row in tables
            if isinstance(row, dict)
        }
        rows = []
        for index, company in enumerate(companies):
            row = by_code.get(company["ifind"]) or (tables[index] if index < len(tables) else None)
            if not isinstance(row, dict):
                raise RuntimeError(f"iFinD 缺少 {company['code']} 数据")
            rows.append(self._ifind_payload_to_row(company, row))
        return rows

    def fetch_company(self, company: dict[str, str]) -> dict[str, Any]:
        errors = []
        callers = {"ifind": self.call_ifind, "wind": self.call_wind}
        labels = {"ifind": "iFinD", "wind": "Wind"}
        for source in self.source_order():
            try:
                return callers[source](company)
            except Exception as exc:
                errors.append(f"{labels[source]}: {exc}")
        return {
            "code": company["code"],
            "name": company["name"],
            "segment": company["segment"],
            "price": None,
            "change_pct": None,
            "amount": None,
            "market_cap": None,
            "pe_ttm": None,
            "pb": None,
            "source": "不可用",
            "error": " | ".join(errors),
        }

    def fetch_all(self, max_workers: int = 4) -> dict[str, Any]:
        if self.ifind_configured():
            try:
                rows = self.call_ifind_batch(self.companies)
                return {
                    "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "success_count": sum(1 for row in rows if not row["error"]),
                    "error_count": sum(1 for row in rows if row["error"]),
                    "rows": rows,
                }
            except Exception:
                pass
        rows = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch_company, item): item for item in self.companies}
            for future in as_completed(futures):
                rows.append(future.result())
        order = {item["code"]: index for index, item in enumerate(self.companies)}
        rows.sort(key=lambda row: order[row["code"]])
        return {
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "success_count": sum(1 for row in rows if not row["error"]),
            "error_count": sum(1 for row in rows if row["error"]),
            "rows": rows,
        }
