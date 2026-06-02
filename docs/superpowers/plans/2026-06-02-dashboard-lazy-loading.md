# Dashboard Lazy Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single massive dashboard HTML payload with a lightweight shell plus separate JSON files for summary and deferred detail views.

**Architecture:** `analyze_chat_export.py` will keep producing the existing CSV and `parsed_summary.json` outputs, but `write_outputs()` will additionally emit `dashboard_summary.json`, `dashboard_conversations.json`, `dashboard_daily.json`, `dashboard_categories.json`, and `dashboard_codex_match.json`. `dashboard.html` will fetch only the summary file on load, render the initial dashboard from that payload, and load each heavier section only when the user requests it. Conversation rows will render in pages so the DOM never receives the entire list at once.

**Tech Stack:** Python 3 standard library, static HTML/CSS/vanilla JavaScript, `unittest`.

---

### Task 1: Lock in the new artifact contract with tests

**Files:**
- Modify: `tests/test_analyze_chat_export.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dedup_and_outputs(self) -> None:
    # ... existing checks ...
    self.assertTrue((output_dir / "dashboard_summary.json").exists())
    self.assertTrue((output_dir / "dashboard_conversations.json").exists())
    self.assertTrue((output_dir / "dashboard_daily.json").exists())
    self.assertTrue((output_dir / "dashboard_categories.json").exists())
    self.assertTrue((output_dir / "dashboard_codex_match.json").exists())
    self.assertNotIn('<script id="data" type="application/json">', dashboard_html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_analyze_chat_export.AnalyzeChatExportTest.test_dedup_and_outputs`
Expected: FAIL because the new dashboard artifact files do not exist yet.

- [ ] **Step 3: Write minimal implementation**

No code yet. This task only locks in the regression test.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_analyze_chat_export.AnalyzeChatExportTest.test_dedup_and_outputs`
Expected: PASS after the implementation is complete.

### Task 2: Emit split dashboard JSON artifacts

**Files:**
- Modify: `analyze_chat_export.py`

- [ ] **Step 1: Write the failing test**

Use the artifact assertions from Task 1 and add content checks:

```python
summary_payload = json.loads((output_dir / "dashboard_summary.json").read_text(encoding="utf-8"))
self.assertIn("meta", summary_payload)
self.assertIn("monthly", summary_payload)
conversations_payload = json.loads((output_dir / "dashboard_conversations.json").read_text(encoding="utf-8"))
self.assertIn("items", conversations_payload)
self.assertEqual(conversations_payload["total"], 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_analyze_chat_export.AnalyzeChatExportTest.test_dedup_and_outputs`
Expected: FAIL until `write_outputs()` writes the new JSON files.

- [ ] **Step 3: Write minimal implementation**

```python
def write_dashboard_json_outputs(output_dir: Path, parsed: dict) -> None:
    summary_payload = {
        "meta": parsed["meta"],
        "monthly": parsed["monthly"],
    }
    (output_dir / "dashboard_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Write conversations, daily, categories, and codex match payloads similarly.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_analyze_chat_export.AnalyzeChatExportTest.test_dedup_and_outputs`
Expected: PASS.

### Task 3: Replace embedded HTML payload with fetch-based shell

**Files:**
- Modify: `analyze_chat_export.py`

- [ ] **Step 1: Write the failing test**

Add dashboard HTML assertions:

```python
dashboard_html = (output_dir / "dashboard.html").read_text(encoding="utf-8")
self.assertIn("dashboard_summary.json", dashboard_html)
self.assertIn("会話一覧を読み込む", dashboard_html)
self.assertIn("Codex照合を読み込む", dashboard_html)
self.assertNotIn('<script id="data" type="application/json">', dashboard_html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_analyze_chat_export.AnalyzeChatExportTest.test_dedup_and_outputs`
Expected: FAIL until `build_dashboard_html()` stops embedding `parsed`.

- [ ] **Step 3: Write minimal implementation**

```python
def build_dashboard_html() -> str:
    return """
    <!doctype html>
    <html lang="ja">
      ...
      <button data-load="conversations">会話一覧を読み込む</button>
      <button data-load="codex">Codex照合を読み込む</button>
      <script src="dashboard.js"></script>
    </html>
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_analyze_chat_export.AnalyzeChatExportTest.test_dedup_and_outputs`
Expected: PASS.

### Task 4: Update docs and ignore rules

**Files:**
- Modify: `README.md`
- Modify: `docs/dashboard_guide.md`
- Modify: `docs/README_ja.md`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing docs check**

No automated docs test exists; validate by inspection after implementation.

- [ ] **Step 2: Run test to verify it fails**

Not applicable.

- [ ] **Step 3: Write minimal implementation**

Document the new generated files, the need to open the dashboard through a local HTTP server, and the new load-on-demand sections. Ignore the new generated JSON files in `.gitignore`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_analyze_chat_export`
Expected: PASS.

