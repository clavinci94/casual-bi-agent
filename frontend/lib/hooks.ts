"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { api, ApiError } from "./api";

type Fn<T> = () => Promise<T>;

function makeHook<T>(key: string, fetcher: Fn<T>, opts?: SWRConfiguration<T>) {
  return useSWR<T, ApiError>(key, fetcher, opts);
}

export const useRecommendations = (
  status: "pending" | "approved" | "rejected" | "all" = "pending",
) =>
  makeHook(`recommendations:${status}`, () => api.listRecommendations(status));

export const useRecommendation = (id: string | null) =>
  useSWR(id ? `recommendation:${id}` : null, () =>
    api.getRecommendation(id as string),
  );

export const useRuns = (limit = 50) =>
  makeHook(`runs:${limit}`, () => api.listRuns(limit));

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

export const useInsights = (limit = 50) =>
  makeHook(`insights:${limit}`, () => api.listInsights(limit));

export const useReadiness = () => makeHook("readyz", () => api.readiness());
