FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg unixodbc \
    && curl -fsSL -o /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY edgar /app/edgar
COPY edgar_warehouse /app/edgar_warehouse

RUN pip install --upgrade pip

RUN pip install --no-compile \
        "pyarrow>=17.0.0" \
        "pandas>=2.0.0" \
        "numpy" \
        "duckdb>=1.0.0" \
        "lxml" \
        "pytz"

RUN pip install --no-compile \
        "aiobotocore" \
        "aiohttp" \
        "adlfs>=2024.4.0" \
        "fsspec>=2023.1.0" \
        "s3fs>=2023.1.0" \
        "httpx>=0.25.0" \
        "zstandard>=0.20.0"

RUN pip install --no-compile ".[s3,azure,mdm]"

ENTRYPOINT ["edgar-warehouse"]
CMD ["--help"]
