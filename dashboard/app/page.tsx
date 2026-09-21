import { GhostMeterDashboard } from "./dashboard";
import { mutationCounts } from "./lib/mutation-battery";
import { getMutationSummary } from "./lib/mutation-battery-source";

export default function Home() {
  return <GhostMeterDashboard mutationCounts={mutationCounts(getMutationSummary())} />;
}
