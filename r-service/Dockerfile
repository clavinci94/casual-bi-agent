# r2u provides apt-installable R packages with native arm64 + amd64 binaries.
# Avoids source compilation entirely — install seconds, not minutes — and
# avoids the PPM "linux binaries are amd64-only" issue.
FROM rocker/r2u:noble

# Most CRAN packages are mirrored as apt packages prefixed with r-cran-.
RUN apt-get update && apt-get install -y --no-install-recommends \
        r-cran-plumber \
        r-cran-jsonlite \
        r-cran-zoo \
        r-cran-causalimpact \
    && rm -rf /var/lib/apt/lists/* \
    && R -e "stopifnot(all(c('plumber','jsonlite','zoo','CausalImpact') %in% rownames(installed.packages())))"

WORKDIR /app
EXPOSE 8765

# api.R is mounted as a volume in dev so iterating doesn't require a rebuild.
CMD ["Rscript", "-e", "pr <- plumber::pr('/app/api.R'); plumber::pr_run(pr, host='0.0.0.0', port=8765)"]
