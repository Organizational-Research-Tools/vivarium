# Scientific-Python sandbox for the paper_replication pack (M2 §7, M7 WS6).
#
# The per-agent tool-execution sandbox: the agent writes Python to its bind-mounted
# scratch and runs it via `docker exec`. Read-only data is mounted at /visible;
# scratch is writable. Credentials never enter here (the gateway is host-side).
#
# Pinned by digest in the run manifest. Trimmed vs the old platform image: no Node,
# no Claude CLI, no SUMO/X11 — tool use is host-owned, not SDK-in-container.
FROM python:3.11-slim

RUN pip install --no-cache-dir \
    "numpy>=1.26" \
    "pandas>=2.1" \
    "scipy>=1.11" \
    "statsmodels>=0.14" \
    "scikit-learn>=1.3"

WORKDIR /work
