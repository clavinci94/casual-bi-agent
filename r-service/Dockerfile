# r2u provides apt-installable R packages with native arm64 + amd64 binaries.
# Avoids source compilation entirely — install seconds, not minutes — and
# avoids the PPM "linux binaries are amd64-only" issue.
FROM rocker/r2u:noble

# Most CRAN packages are mirrored as apt packages prefixed with r-cran-.
# If the r2u mirror is temporarily unavailable, fall back to CRAN source for
# CausalImpact so the image build does not fail on a stale apt index.
RUN set -eux; \
    for attempt in 1 2 3; do \
        apt-get -o Acquire::Retries=3 update; \
        if apt-cache show r-cran-causalimpact >/dev/null 2>&1; then \
            break; \
        fi; \
        if [ "$attempt" = "3" ]; then \
            break; \
        fi; \
        rm -rf /var/lib/apt/lists/*; \
        sleep $((attempt * 10)); \
    done; \
    apt-get install -y --no-install-recommends \
        build-essential \
        gfortran \
        r-cran-plumber \
        r-cran-jsonlite \
        r-cran-zoo; \
    if apt-cache show r-cran-causalimpact >/dev/null 2>&1; then \
        apt-get install -y --no-install-recommends r-cran-causalimpact; \
    else \
        R -e "install.packages('CausalImpact', repos='https://cloud.r-project.org')"; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    R -e "stopifnot(all(c('plumber','jsonlite','zoo','CausalImpact') %in% rownames(installed.packages())))"

WORKDIR /app
EXPOSE 8765

# api.R is mounted as a volume in dev so iterating doesn't require a rebuild.
CMD ["Rscript", "-e", "pr <- plumber::pr('/app/api.R'); plumber::pr_run(pr, host='0.0.0.0', port=8765)"]
