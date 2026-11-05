# One image for both Cloud Run pieces: the API service (the CMD below) and the
# batch job (`python -m karimi_normalise.job`, set at deploy time).
# Built by Cloud Build in an EU region (deploy/cloudbuild.yaml).
#
# Every model is downloaded at BUILD time and baked in, so at run time nothing
# is fetched and no text leaves the container. ~4 GB: a cold start takes tens
# of seconds, which is why large volumes go through the job, not a request.

FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=0 KARIMI_DICT=/app/dictionary KARIMI_QUALITY=/app/dictionary/quality.json

COPY pyproject.toml ./
COPY karimi ./karimi
COPY karimi_normalise ./karimi_normalise
# CPU torch: no GPU on Cloud Run here, and the CUDA build is several GB larger.
RUN pip install --no-cache-dir --timeout 120 --retries 10 \
        --extra-index-url https://download.pytorch.org/whl/cpu ".[all,api]"

# Pinned models: spaCy comes with the package (pyproject), opus-mt as in
# translate.py, the embedding as in the dictionary's manifest.
RUN python -c "from karimi_normalise import translate as t; [t._model(m) for m in set(t.MODEL_FOR.values())]" \
 && python -c "from karimi import embed; embed.load_model()"
ENV HF_HUB_OFFLINE=1

# The dictionary is not in git (it is made from the adverts): Cloud Build copies
# it from the EU bucket into the build context before this step.
COPY dictionary ./dictionary

CMD ["sh", "-c", "uvicorn karimi_normalise.api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
