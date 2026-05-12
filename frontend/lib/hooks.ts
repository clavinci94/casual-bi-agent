"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { api, ApiError } from "./api";

type Fn<T> = () => Promise<T>;

function makeHook<T>(key: string, fetcher: Fn<T>, opts?: SWRConfiguration<T>) {
  return useSWR<T, ApiError>(key, fetcher, opts);
}

export const useRecommendations = (
  status: "pending" | "approved" | "rejected" | "all" = "pending",
  excludeTriggers: string[] = [],
) =>
  makeHook(`recommendations:${status}:${excludeTriggers.join(",")}`, () =>
    api.listRecommendations(status, 50, excludeTriggers),
  );

export const useRecommendation = (id: string | null) =>
  useSWR(id ? `recommendation:${id}` : null, () =>
    api.getRecommendation(id as string),
  );

export const useRuns = (limit = 50, excludeTriggers: string[] = []) =>
  makeHook(`runs:${limit}:${excludeTriggers.join(",")}`, () =>
    api.listRuns(limit, excludeTriggers),
  );

export const useRun = (id: string | null) =>
  useSWR(id ? `run:${id}` : null, () => api.getRun(id as string));

export const useKpiList = () => makeHook("kpis", () => api.listKpis());

export const useKpiQuery = (
  view: string | null,
  params: { start: string; end: string; group_by?: string[] },
) =>
  useSWR(
    view ? ["kpi-query", view, params] : null,
    () => api.queryKpi(view as string, params),
  );

export const useInsights = (limit = 50, excludeTriggers: string[] = []) =>
  makeHook(`insights:${limit}:${excludeTriggers.join(",")}`, () =>
    api.listInsights(limit, excludeTriggers),
  );

export const useReadiness = () => makeHook("readyz", () => api.readiness());
