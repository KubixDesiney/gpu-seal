# Finding 003 — AWS Free Plan blocks the Linux provider run

**Date:** 2026-08-03  
**Region checked:** `eu-west-3`  
**Requested workload:** one `g4dn.xlarge` for at most 60 minutes

## Observation

The account-level Service Quota for **Running On-Demand G and VT instances**
was applied at `4`. The EC2 launch console nevertheless marked `g4dn.xlarge`
as unavailable because it is not eligible under the AWS Free Plan and requires
an account-plan upgrade.

## Boundary and cost result

No instance was launched. No EBS volume, public IP, or other test resource was
created by this attempt, and there is no AWS measurement bundle to report.
This is an account-plan eligibility gate, not a provider measurement result.

## Decision

Remain on the Free Plan. The AWS provider run is paused until an explicit,
separate decision is made to convert the account to the Paid Plan. Colab or
the researcher-owned RTX 3050 may continue to support development and control
validation, but those runs must not be presented as AWS/provider evidence.

