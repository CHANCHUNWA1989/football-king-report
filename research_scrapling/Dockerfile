# One-shot research qualification; intentionally not a production web service.
# Base image observed in successful research CI artifact 15253129826.
FROM python:3.12-slim@sha256:5b5fe805d367f8f5a359ded6ab2652b7f9a206453ee6ee789c0045ba6ec15016
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# V6.0 research remediation candidate: signed configured Debian repositories only.
# Keep the base digest and Python pins; OS package resolution is time-dependent.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends \
    && apt-get check \
    && rm -rf /var/lib/apt/lists/*
# Exact versions observed in that Docker build; version pins, not wheel hash verification.
RUN pip install --no-cache-dir \
    'anyio==4.16.0' \
    'apify_fingerprint_datapoints==0.16.0' \
    'browserforge==1.2.4' \
    'certifi==2026.11.20' \
    'cffi==2.1.1' \
    'click==8.5.1' \
    'cssselect==1.6.0' \
    'curl_cffi==0.17.0' \
    'frostwork==0.2.2' \
    'greenlet==3.5.6' \
    'idna==3.20' \
    'lxml==6.2.0' \
    'msgspec==0.22.0' \
    'orjson==3.13.0' \
    'patchright==1.58.2' \
    'playwright==1.58.0' \
    'Protego==0.7.0' \
    'pycparser==3.12' \
    'pyee==13.0.1' \
    'scrapling[fetchers]==0.4.6' \
    'tld==0.13.2' \
    'typing_extensions==4.16.0' \
    'w3lib==2.6.0' \
    && pip check \
    && pip freeze \
    && useradd --system --uid 10001 --create-home researcher \
    && mkdir /evidence && chown 10001 /evidence
COPY research_scrapling/ /app/research_scrapling/
USER 10001
ENTRYPOINT ["python","/app/research_scrapling/run_qualification.py"]
CMD ["--output","/evidence"]
