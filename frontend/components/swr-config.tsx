"use client";

import { SWRConfig } from "swr";

export function SwrProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: false,
        dedupingInterval: 5000,
        errorRetryCount: 1,
      }}
    >
      {children}
    </SWRConfig>
  );
}
