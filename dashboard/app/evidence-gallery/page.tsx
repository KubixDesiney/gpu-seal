import type { Metadata } from "next";
import { GhostMeterDashboard } from "../dashboard";
import { listEvidenceGallery } from "../lib/evidence-bundles";

export const metadata: Metadata = {
  title: "Evidence gallery — GPU-SEAL",
};

export default function EvidenceGalleryRoute() {
  return <GhostMeterDashboard gallery={listEvidenceGallery()} />;
}
