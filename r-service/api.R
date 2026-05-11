# Plumber API exposing CausalImpact as the causal-inference layer of the
# Causal BI Agent. Stateless: callers pass in time series + periods, we run
# the analysis, return summary stats.

library(plumber)
library(CausalImpact)
library(jsonlite)
library(zoo)

#* Health check
#* @get /health
function() {
  list(status = "ok", service = "causal-bi-r", version = "0.1.0")
}

#* Run CausalImpact on a target series with optional control series.
#*
#* Body shape:
#*   y: numeric[]            — target daily values
#*   dates: string[]         — ISO dates parallel to y
#*   pre_period: [string, string]   — [start, end] of pre-period (inclusive)
#*   post_period: [string, string]  — [start, end] of post-period (inclusive)
#*   X: named list of numeric[]?    — optional control series, e.g.
#*                                    {"desktop": [..], "tablet": [..]}
#*
#* Returns summary stats incl. relative effect with 95% CI and p-value.
#*
#* @post /causal-impact
function(req) {
  body <- jsonlite::fromJSON(req$postBody, simplifyVector = FALSE)

  y <- unlist(body$y)
  dates <- as.Date(unlist(body$dates))
  pre_period <- as.Date(unlist(body$pre_period))
  post_period <- as.Date(unlist(body$post_period))

  if (length(y) != length(dates)) {
    stop(sprintf("len(y)=%d must equal len(dates)=%d", length(y), length(dates)))
  }

  # Build the data matrix: y first column, then any controls.
  cols <- list(y = y)
  if (!is.null(body$X) && length(body$X) > 0) {
    for (name in names(body$X)) {
      x <- unlist(body$X[[name]])
      if (length(x) != length(y)) {
        stop(sprintf("control '%s' length %d != y length %d",
                     name, length(x), length(y)))
      }
      cols[[name]] <- x
    }
  }
  data <- zoo::zoo(do.call(cbind, cols), order.by = dates)

  impact <- CausalImpact::CausalImpact(
    data,
    pre.period = pre_period,
    post.period = post_period
  )

  s <- impact$summary
  # `s` is a data frame with rows "Average" and "Cumulative".
  avg <- s["Average", ]

  list(
    summary = list(
      avg_actual         = unname(avg$Actual),
      avg_predicted      = unname(avg$Pred),
      avg_pred_lower     = unname(avg$Pred.lower),
      avg_pred_upper     = unname(avg$Pred.upper),
      abs_effect         = unname(avg$AbsEffect),
      abs_effect_lower   = unname(avg$AbsEffect.lower),
      abs_effect_upper   = unname(avg$AbsEffect.upper),
      rel_effect         = unname(avg$RelEffect),
      rel_effect_lower   = unname(avg$RelEffect.lower),
      rel_effect_upper   = unname(avg$RelEffect.upper),
      p_value            = unname(avg$p),
      is_significant     = unname(avg$p) < 0.05
    ),
    pre_period  = as.character(pre_period),
    post_period = as.character(post_period),
    n_observations = length(y),
    has_controls = !is.null(body$X) && length(body$X) > 0
  )
}
