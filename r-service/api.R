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

#* E-value sensitivity analysis (VanderWeele & Ding 2017).
#*
#* Quantifies how strong an unmeasured confounder would have to be
#* (on the risk-ratio scale, with both treatment and outcome) to
#* fully explain away the observed effect. Higher E-value = more
#* robust causal claim.
#*
#* Body shape:
#*   rel_effect: number             — point estimate of relative effect
#*                                    (e.g. -0.38 for -38 %)
#*   rel_effect_lower: number?      — lower 95 % CI bound (signed, optional)
#*
#* Returns: e_value (point), e_value_ci (lower bound on the CI side closest
#* to the null), interpretation string.
#*
#* @post /sensitivity
function(req) {
  body <- jsonlite::fromJSON(req$postBody, simplifyVector = FALSE)

  rel <- as.numeric(body$rel_effect)
  if (is.na(rel) || rel <= -1) {
    stop("rel_effect must be a finite number > -1 (it is a fractional change)")
  }

  # Convert relative effect to a risk ratio: RR = post / pre = 1 + rel_effect.
  rr_point <- 1 + rel

  evalue_from_rr <- function(rr) {
    if (rr < 1) rr <- 1 / rr
    rr + sqrt(rr * (rr - 1))
  }

  ev_point <- evalue_from_rr(rr_point)

  # E-value for the CI bound closest to the null (RR = 1). This is the
  # standard VanderWeele convention — gives the "even at the optimistic
  # edge of the CI, a confounder of strength X would explain it away".
  ev_ci <- NA_real_
  if (!is.null(body$rel_effect_lower)) {
    lower <- as.numeric(body$rel_effect_lower)
    if (!is.na(lower) && lower > -1) {
      rr_lower <- 1 + lower
      # The CI bound closest to RR = 1 is the relevant one for sensitivity.
      if ((rr_lower - 1) * (rr_point - 1) > 0) {
        ev_ci <- evalue_from_rr(rr_lower)
      } else {
        # CI crosses the null — sensitivity collapses to 1.
        ev_ci <- 1
      }
    }
  }

  interpretation <- if (ev_point < 1.5) {
    "fragile: weak unmeasured confounding would suffice to explain the effect away"
  } else if (ev_point < 2.5) {
    "moderate robustness: a confounder would need an RR ~2 with both treatment and outcome"
  } else if (ev_point < 4) {
    "robust: an unmeasured confounder would need a substantial association on both sides"
  } else {
    "very robust: explaining this away would require an implausibly strong confounder"
  }

  list(
    e_value           = ev_point,
    e_value_ci_bound  = ev_ci,
    rel_effect        = rel,
    rr_point          = rr_point,
    interpretation    = interpretation
  )
}

#* Two-proportion power analysis via stats::power.prop.test.
#*
#* Pass exactly three of {n, p1, p2, power}; the missing one is solved.
#* sig_level defaults to 0.05 (two-sided).
#*
#* Body shape:
#*   n: integer?           — sample size per group
#*   p1: number?           — baseline proportion (0..1)
#*   p2: number?           — alternative proportion (0..1)
#*   power: number?        — desired power (0..1)
#*   sig_level: number?    — alpha, default 0.05
#*
#* Returns the solved value plus all inputs.
#*
#* @post /power
function(req) {
  body <- jsonlite::fromJSON(req$postBody, simplifyVector = FALSE)
  n         <- if (!is.null(body$n))         as.numeric(body$n)         else NULL
  p1        <- if (!is.null(body$p1))        as.numeric(body$p1)        else NULL
  p2        <- if (!is.null(body$p2))        as.numeric(body$p2)        else NULL
  power     <- if (!is.null(body$power))     as.numeric(body$power)     else NULL
  sig_level <- if (!is.null(body$sig_level)) as.numeric(body$sig_level) else 0.05

  given <- sum(!is.null(n), !is.null(p1), !is.null(p2), !is.null(power))
  if (given != 3) {
    stop(sprintf("pass exactly three of n, p1, p2, power (got %d)", given))
  }

  res <- stats::power.prop.test(
    n = n, p1 = p1, p2 = p2, power = power, sig.level = sig_level,
    alternative = "two.sided"
  )

  rel <- if (!is.null(res$p1) && !is.null(res$p2) && res$p1 > 0) {
    (res$p2 - res$p1) / res$p1
  } else {
    NA_real_
  }

  list(
    n              = res$n,
    p1             = res$p1,
    p2             = res$p2,
    power          = res$power,
    sig_level      = res$sig.level,
    rel_effect     = rel,
    method         = "power.prop.test (two-sided)"
  )
}
