---
id: "c09-demo-app-create-an-empty-streamlit-page-2026-11-07"
status: "backlog"
priority: "critical"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: null
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
- [ ] Committed and pushed.

## Help
- https://docs.streamlit.io/get-started
