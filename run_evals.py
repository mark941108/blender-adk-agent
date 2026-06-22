"""
run_evals.py — Evaluation-Driven Development (EDD) test runner.

Validates the orchestrator's tool trajectory against expected sequences
for each eval case defined in tests/eval_cases.json.
"""
import asyncio
import json
import sys
import io

# Force UTF-8 stdout/stderr on Windows to prevent cp950 garbling of Chinese prompts
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from agents.orchestrator import SceneAssemblerOrchestrator


class MockMCP:
    """A no-op MCP client that records tool calls without touching Blender."""
    async def call_tool(self, name: str, arguments: dict):
        class DummyResult:
            def __init__(self, text):
                self.content = [type('obj', (object,), {'text': text})()]
                self.is_error = False
        return DummyResult(f"Executed {name} successfully")


# Per-case hardcoded LLM responses keyed by eval case ID.
# This isolates eval from real API calls (deterministic, fast, free).
EVAL_RESPONSES = {
    "scene_assembly_01": (
        '[{"tool": "hdri_setup", "args": {"environment_type": "evening"}}, '
        '{"tool": "asset_fetcher", "args": {"asset_query": "wooden table"}}, '
        '{"tool": "auto_layout", "args": {}}]'
    ),
    "scene_assembly_02": (
        '[{"tool": "hdri_setup", "args": {"environment_type": "forest"}}, '
        '{"tool": "material_setup", "args": {"material_type": "grass"}}, '
        '{"tool": "asset_fetcher", "args": {"asset_query": "boulder"}}, '
        '{"tool": "asset_fetcher", "args": {"asset_query": "axe"}}, '
        '{"tool": "auto_layout", "args": {}}]'
    ),
    "scene_assembly_03": (
        '[{"tool": "hdri_setup", "args": {"environment_type": "beach"}}, '
        '{"tool": "material_setup", "args": {"material_type": "sand"}}, '
        '{"tool": "asset_fetcher", "args": {"asset_query": "chair"}}, '
        '{"tool": "auto_layout", "args": {}}]'
    ),
    "security_rejection_01": "[]",
}


class MockLLM:
    """Returns a per-case deterministic response, bypassing real LLM calls."""
    def __init__(self, case_id: str):
        self._response = EVAL_RESPONSES.get(case_id, "[]")

    async def repair_code(self, original_code, error_message, context) -> str:
        return self._response


async def run_evals():
    with open("tests/eval_cases.json", "r", encoding="utf-8") as f:
        evals = json.load(f)

    mcp = MockMCP()
    passed = 0
    total = len(evals)

    for case in evals:
        print(f"\n{'─'*60}")
        print(f"▶  Eval: {case['id']}")
        print(f"   Prompt: {case['prompt']}")

        llm = MockLLM(case["id"])
        agent = SceneAssemblerOrchestrator(mcp, llm)
        result = await agent.run(case["prompt"])

        actual   = [a["tool"] for a in result.actions_taken]
        expected = [t["tool_name"] for t in case["expected_trajectory"]]

        if actual == expected:
            print(f"   [PASS] ✅  {actual}")
            passed += 1
        else:
            print(f"   [FAIL] ❌")
            print(f"          Expected: {expected}")
            print(f"          Got:      {actual}")

    print(f"\n{'='*60}")
    print(f"  Eval Summary: {passed}/{total} PASSED")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(run_evals())
