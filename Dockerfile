ARG DEPENDENCY_IMAGE=edgartools-warehouse-deps:local
FROM ${DEPENDENCY_IMAGE}

WORKDIR /app

COPY edgar /app/edgar
COPY edgar_warehouse /app/edgar_warehouse

ENTRYPOINT ["python", "-m", "edgar_warehouse"]
CMD ["--help"]
