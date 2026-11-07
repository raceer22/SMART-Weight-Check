---
id: "c09-demo-app-create-an-empty-streamlit-page-2026-11-07"
status: "done"
priority: "critical"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T12:50:00.000Z"
completedAt: "2026-11-07T12:50:00.000Z"
labels: ["app", "beginner", "python"]
order: "b0V"
---
# C09 · Demo app: create an empty Streamlit page

**Time:** ~20 min  ·  **Do first:** S03

**Why:** Streamlit turns a Python script into a web page, which makes it the fastest way to a demo.

## Steps
1. Create `app/app.py` with:
   ```python
   import streamlit as st
   st.title('SMART Weight View (synthetic data)')
   st.write('Hello team!')
   ```
2. Run `streamlit run app/app.py`.
3. A browser tab opens showing the title.

## Done when
- [x] The page opens in the browser.
- [x] Committed and pushed.

## Help
- https://docs.streamlit.io/get-started

## Result
- `app/app.py` grew into the full demo (C10–C14 plus the weight check). Committed with Epics 1–4 and pushed to GitHub.
