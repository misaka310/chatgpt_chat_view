# Send Count Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the dashboard so the main metrics are based on sent message count (`user_messages`) instead of conversation thread count, while keeping the dark dashboard layout and month/day drill-down flow.

**Architecture:** Keep the current single-file dashboard structure and update the data bindings in place. The monthly chart, selected-month summary, monthly table, and daily chart should all read from `monthly.user_messages` or `daily.user_messages`. Codex remains non-primary and hidden from the main experience.

**Tech Stack:** Static HTML, vanilla CSS, vanilla JavaScript, local JSON files loaded by `fetch()`.

---

### Task 1: Update the dashboard main metrics and labels

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Replace the monthly chart title, labels, and values with send-count wording**

- [ ] **Step 2: Replace the selected-month summary cards so the primary stat is `user_messages`**

- [ ] **Step 3: Replace the monthly table columns so the main column is send count, not thread count**

- [ ] **Step 4: Keep the selected-month control and month-row click behavior linked to the same selected month**

- [ ] **Step 5: Save the file and verify the text now uses `送信回数` / `あなたの発言数` instead of `会話スレッド数`**

### Task 2: Update the selected-month daily chart to use daily send count

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Replace the daily chart title, axis labels, notes, and footer labels with send-count wording**

- [ ] **Step 2: Bind the daily bars to `daily.user_messages`**

- [ ] **Step 3: Recalculate total, average, max, and min from `daily.user_messages`**

- [ ] **Step 4: Verify the chart still changes when the selected month changes**

### Task 3: Remove Codex from the main experience and sync docs

**Files:**
- Modify: `dashboard.html`
- Modify: `README.md`

- [ ] **Step 1: Hide or demote the Codex section so it no longer appears as a main-panel feature**

- [ ] **Step 2: Update README copy to say the dashboard is centered on send count / your sent messages**

- [ ] **Step 3: Verify that the README still points to the local HTTP server workflow**

### Task 4: Browser and syntax verification

**Files:**
- Modify: none

- [ ] **Step 1: Run a JavaScript syntax check against the `<script>` block**

- [ ] **Step 2: Open `http://127.0.0.1:8733/dashboard.html` in a browser and verify the monthly chart, summary, and daily chart all reflect `user_messages`**

- [ ] **Step 3: Confirm a known month such as 2026-05 shows `6,010` in the main monthly summary instead of a thread-count value**

- [ ] **Step 4: Confirm the daily chart footer uses daily send counts**
