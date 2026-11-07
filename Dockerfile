# SMART Weight Check demo: the Streamlit decision inbox on the synthetic quickstart data.
#
#   docker build -t smart-weight-check .
#   docker run -d --name smart-weight-check -p 8501:8501 --restart unless-stopped smart-weight-check
#
# or `docker compose up -d`, then open http://<server>:8501.
# Behind a reverse proxy, forward WebSockets too (the app talks over /_stcore/stream);
# to serve it under a sub-path, add --server.baseUrlPath=<path> to CMD.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The app's run-time dependencies, pinned to the versions it was tested with
# (pyproject.toml dependencies plus the "app" extra, without matplotlib, which only notes/ uses).
# The project itself is not pip-installed: the app puts src/ on sys.path, and the dataset
# package finds configs/ relative to src/.
RUN pip install \
      numpy==2.5.4 pandas==3.1.1 pyarrow==26.0.1 duckdb==2.0.0 PyYAML==6.0.3 pytz==2026.6 tabulate==0.10.0 \
      streamlit==1.67.0 altair==6.3.0

RUN useradd --create-home --uid 1000 app \
 && mkdir /srv/smart-weight-check && chown app:app /srv/smart-weight-check
WORKDIR /srv/smart-weight-check

# Only what the app reads at run time; .streamlit/ holds the theme and must sit in the working directory.
COPY configs/ configs/
COPY src/ src/
COPY baselines/ baselines/
COPY data/quickstart/public/ data/quickstart/public/
COPY .streamlit/ .streamlit/
COPY app/ app/

USER app
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"]

CMD ["streamlit", "run", "app/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
