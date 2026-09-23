"""Host-kind detection for cloud notebook runtimes.

The single source of truth for telling a Kaggle notebook from a Colab
notebook from a bare GCE VM from everything else ("other"), so that a
§9.7 allocation-model classification never has to guess whether it is
looking at the researcher's own workstation.

This is a direct port of the detection ``lab/cloud-runner/bootstrap.sh``
already performs (see its "environment manifest" step) -- deliberately kept
as the one implementation both call, rather than a second detector that
could drift from it. If the heuristic below ever changes, update
``bootstrap.sh`` in the same commit.

Kaggle is checked before Colab on purpose: confirmed live on a Kaggle T4x2
notebook that Kaggle's own kernel images carry both a leftover
``COLAB_RELEASE_TAG`` and a ``/content`` directory from a shared upstream
base image, even though the host is genuinely Kaggle. Only
``KAGGLE_KERNEL_RUN_TYPE`` / ``KAGGLE_URL_BASE`` (confirmed set on Kaggle,
empty on Colab) and ``COLAB_GPU`` / ``COLAB_RELEASE_TAG`` (confirmed empty on
Kaggle) are exclusive enough to trust.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

__all__ = ["KNOWN_CLOUD_HOSTS", "detect_host_kind"]

#: Host kinds ``detect_host_kind`` can positively identify as *not* the
#: researcher's own hardware. Anything else comes back as ``"other"`` --
#: which includes a genuine local workstation, but also any rented instance
#: this heuristic does not yet recognise, so ``"other"`` must never be read
#: as "confirmed local."
KNOWN_CLOUD_HOSTS = frozenset({"kaggle", "colab", "gce"})

_GCE_DMI_PRODUCT_NAME_PATH = Path("/sys/class/dmi/id/product_name")


def detect_host_kind(
    env: Mapping[str, str] | None = None,
    *,
    dmi_product_name_path: Path | None = None,
) -> str:
    """Return ``"kaggle"``, ``"colab"``, ``"gce"``, or ``"other"``.

    Mirrors ``lab/cloud-runner/bootstrap.sh`` exactly: the DMI/env-var checks
    only run on Linux (Colab and Kaggle are always Linux notebook hosts), so a
    macOS or Windows development machine falls straight through to
    ``"other"`` regardless of what environment variables happen to be set.
    """
    if not sys.platform.startswith("linux"):
        return "other"

    if env is None:
        env = os.environ
    if dmi_product_name_path is None:
        dmi_product_name_path = _GCE_DMI_PRODUCT_NAME_PATH

    if env.get("KAGGLE_KERNEL_RUN_TYPE") or env.get("KAGGLE_URL_BASE"):
        return "kaggle"
    if env.get("COLAB_GPU") or env.get("COLAB_RELEASE_TAG"):
        return "colab"

    try:
        if dmi_product_name_path.is_file():
            product_name = dmi_product_name_path.read_text(
                encoding="utf-8", errors="ignore"
            )
            if "google compute engine" in product_name.lower():
                return "gce"
    except OSError:
        pass

    return "other"
