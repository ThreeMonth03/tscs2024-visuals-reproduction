FROM python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-figures.txt requirements-notebook.txt /tmp/requirements/
RUN python -m pip install --no-cache-dir -r /tmp/requirements/requirements-notebook.txt \
    && rm -rf /tmp/requirements \
    && useradd --create-home --uid 1000 --user-group jovyan

ENV HOME=/home/jovyan \
    USER=jovyan \
    NB_USER=jovyan \
    NB_UID=1000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    REPRO_FONT=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc

WORKDIR /home/jovyan
# Copy public runtime inputs and documentation; no Git history, local runs or raw data.
COPY --chown=1000:1000 run.py manifest.json environment.json requirements*.txt README.md LICENSE RIGHTS.md CITATION.cff ./
COPY --chown=1000:1000 docs/ ./docs/
COPY --chown=1000:1000 .github/workflows/ ./.github/workflows/
COPY --chown=1000:1000 helpers/ ./helpers/
COPY --chown=1000:1000 aggregates/ ./aggregates/
COPY --chown=1000:1000 ci/ ./ci/
COPY --chown=1000:1000 references/ ./references/
COPY --chown=1000:1000 reference_data/ ./reference_data/
COPY --chown=1000:1000 notebooks/ ./notebooks/
RUN mkdir -p /home/jovyan/data/official && chown -R 1000:1000 /home/jovyan/data
USER 1000
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--no-browser"]
