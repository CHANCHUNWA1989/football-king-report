# One-shot research qualification; intentionally not a production web service.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN pip install --no-cache-dir 'scrapling[fetchers]==0.4.6' \
    && useradd --system --uid 10001 --create-home researcher \
    && mkdir /evidence && chown 10001 /evidence
COPY research_scrapling/ /app/research_scrapling/
USER 10001
ENTRYPOINT ["python","/app/research_scrapling/run_qualification.py"]
CMD ["--output","/evidence"]
