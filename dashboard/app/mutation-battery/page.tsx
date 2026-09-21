import type { Metadata } from "next";
import { GhostMeterDashboard } from "../dashboard";
import { mutationCounts } from "../lib/mutation-battery";
import { getMutationSummary } from "../lib/mutation-battery-source";

export const metadata: Metadata = {
  title: "Mutation battery — GPU-SEAL",
};

export default function MutationBatteryRoute() {
  const summary = getMutationSummary();
  return (
    <GhostMeterDashboard
      mutationCounts={mutationCounts(summary)}
      mutationBattery={summary}
    />
  );
}
