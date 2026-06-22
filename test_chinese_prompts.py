"""
test_chinese_prompts.py — 中文自然語言整合測試

用真實 Gemini API (不 mock LLM) + Mock MCP (不碰 Blender)，
驗證 Orchestrator 對各種中文 prompt 的 tool call 解析是否正確。

測試依據：
- Gemini 2.5 Flash 原生支援中文多語言 tool calling (2026年6月確認)
- JSON structured output 搭配 system prompt 可強制輸出特定 schema
- 根據實際 Poly Haven 資料庫確認的可行資產清單
"""
import asyncio
import json
import os
import sys
import io
from pydantic import BaseModel, Field
from typing import List, Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

if not os.environ.get("GEMINI_API_KEY"):
    print("ERROR: GEMINI_API_KEY not set in .env — cannot run live LLM tests.")
    sys.exit(1)

from google import genai
from google.genai.types import GenerateContentConfig
from agents.orchestrator import SceneAssemblerOrchestrator


class MockMCP:
    """No-op MCP: records tool calls, never touches Blender."""
    async def call_tool(self, name: str, arguments: dict):
        class R:
            content = [type('C', (), {'text': f'OK:{name}'})()]
            is_error = False
        return R()


# --- Pydantic Schema: Developer API compatible (no additionalProperties) ---
class ToolCall(BaseModel):
    tool: str = Field(description="Tool name: hdri_setup | asset_fetcher | material_setup | auto_layout")
    environment_type: Optional[str] = Field(default=None, description="For hdri_setup")
    asset_query: Optional[str] = Field(default=None, description="For asset_fetcher")
    material_type: Optional[str] = Field(default=None, description="For material_setup")

class TaskPlan(BaseModel):
    tasks: List[ToolCall] = Field(description="Ordered list of tool calls to assemble the scene")


class RealGeminiLLM:
    """Real Gemini client using the same config as cli.py."""
    def __init__(self):
        self.client = genai.Client()
        self.model = "gemini-2.5-flash"
        self.config = GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TaskPlan,
        )

    async def generate_task_plan(self, prompt: str, system_prompt: str) -> str:
        full = f"{system_prompt}\n\nUser Request: {prompt}"
        
        # --- 2026 SOTA: Socket Stall Mitigation ---
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=full,
                    config=self.config,
                ),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            raise Exception("Gemini API Timeout (Socket Stall prevented)")
        # Unwrap {"tasks": [...]} and reconstruct args dict from flat fields
        parsed = json.loads(response.text)
        raw_tasks = parsed.get("tasks", []) if isinstance(parsed, dict) else parsed
        tasks = []
        for t in raw_tasks:
            args = {}
            if t.get("environment_type"): args["environment_type"] = t["environment_type"]
            if t.get("asset_query"):      args["asset_query"]      = t["asset_query"]
            if t.get("material_type"):   args["material_type"]    = t["material_type"]
            tasks.append({"tool": t["tool"], "args": args})
        return json.dumps(tasks)

    async def repair_code(self, original, error, context) -> str:
        return await self.generate_task_plan(error, context)


# ── 測試案例 ──────────────────────────────────────────────────────────────────
# 格式: (prompt, 必須包含的 tool, 關鍵詞 hint, 描述)
CHINESE_TEST_CASES = [
    # --- 基礎場景 ---
    (
        "幫我設定一個傍晚的客廳場景，放一張咖啡桌。",
        ["hdri_setup", "asset_fetcher", "auto_layout"],
        {"hdri_setup": "evening", "asset_fetcher": "table"},
        "基礎：傍晚客廳 + 咖啡桌"
    ),
    # --- 複雜自然場景 ---
    (
        "一個黎明的海邊，沙地上有一把木椅和一個木桶。",
        ["hdri_setup", "material_setup", "asset_fetcher", "auto_layout"],
        {"hdri_setup": "beach", "material_setup": "sand"},
        "複雜：黎明海邊 + 沙地 + 多物件"
    ),
    # --- 模糊描述 ---
    (
        "給我一個廢墟感覺的場景。",
        ["hdri_setup"],
        {},
        "模糊：廢墟氣氛（只需要 HDRI）"
    ),
    # --- 多物件並行 ---
    (
        "森林裡有一塊大石頭、一把斧頭、一個燈籠。",
        ["hdri_setup", "asset_fetcher", "auto_layout"],
        {"hdri_setup": "forest"},
        "多物件：森林 + 三種道具"
    ),
    # --- 精細需求 ---
    (
        "下雪的夜晚，戶外廣場，有一張長凳。",
        ["hdri_setup", "asset_fetcher", "auto_layout"],
        {"asset_fetcher": "bench"},
        "精細：雪地夜晚 + 長凳"
    ),
]


async def run_test(llm, mcp, prompt, expected_tools, hints, desc):
    """執行單一測試案例並回傳結果字典。"""
    agent = SceneAssemblerOrchestrator(mcp, llm)
    result = await agent.run(prompt)

    actual_tools = [a["tool"] for a in result.actions_taken]
    actual_args  = {a["tool"]: a for a in result.actions_taken}

    # 必要 tool 是否都出現？
    missing = [t for t in expected_tools if t not in actual_tools]

    # 關鍵 hint 是否在對應工具的 args 中？
    hint_ok = []
    for tool, kw in hints.items():
        tool_actions = [a for a in result.actions_taken if a["tool"] == tool]
        # Check the 'args' dict stored in each action (added in orchestrator fix)
        matched = any(
            kw.lower() in json.dumps(a.get("args", {})).lower()
            for a in tool_actions
        )
        hint_ok.append((tool, kw, matched))

    return {
        "desc": desc,
        "prompt": prompt,
        "actual": actual_tools,
        "expected": expected_tools,
        "missing": missing,
        "hints": hint_ok,
        "pass": len(missing) == 0,
    }


async def main():
    llm = RealGeminiLLM()
    mcp = MockMCP()

    print("=" * 70)
    print("  中文 Prompt 整合測試  (Real Gemini API + Mock MCP)")
    print("=" * 70)

    passed = 0
    for prompt, tools, hints, desc in CHINESE_TEST_CASES:
        print(f"\n📌 {desc}")
        print(f"   Prompt: {prompt}")

        r = await run_test(llm, mcp, prompt, tools, hints, desc)
        print(f"   工具軌跡: {r['actual']}")

        if r["pass"]:
            print(f"   ✅ PASS — 所有必要工具都被呼叫")
            passed += 1
        else:
            print(f"   ❌ FAIL — 缺少: {r['missing']}")

        for tool, kw, ok in r["hints"]:
            sym = "✅" if ok else "⚠️"
            print(f"   {sym} hint [{tool}] 包含關鍵詞 '{kw}': {'是' if ok else '否'}")

    print(f"\n{'=' * 70}")
    print(f"  測試結果: {passed}/{len(CHINESE_TEST_CASES)} PASSED")
    print(f"{'=' * 70}")

    if passed < len(CHINESE_TEST_CASES):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
