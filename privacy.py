"""Data Cleaner Studio — honest data-location wording (v1.4, wave 2).

One place for every "where does my data live?" sentence in the app.
The old wording ("Data never leaves this computer.") was true for the
desktop .exe, but it is FALSE on the hosted app: in Supabase/cloud
mode the user's files are uploaded to their private cloud account.
Local mode keeps the old wording verbatim.

Rules:
  - data_location_line(cloud=None) -> the footer sentence. Local mode:
    "Data never leaves this computer." Cloud mode: "Your files are
    stored in your private cloud account."
  - tutorial_load_line(cloud=None) -> the trailing sentence of the
    tutorial's "Load a file" step. Local mode keeps the original
    sentence verbatim; cloud mode says the file is uploaded to the
    user's private cloud account.
  - Pass cloud=True/False explicitly when the caller already knows
    the mode; otherwise the mode is detected the same way the rest
    of the app does (auth.get_auth_backend() == "supabase"), with a
    lazy import so this module never creates an import cycle and
    never fails when auth is unavailable — detection failure means
    local mode, the safe wording for a report footer.
"""

from __future__ import annotations

LOCAL_LINE = "Data never leaves this computer."
CLOUD_LINE = "Your files are stored in your private cloud account."

LOCAL_LOAD_SENTENCE = ("Your file stays on this computer — "
                       "nothing is uploaded anywhere.")
CLOUD_LOAD_SENTENCE = ("Your file is uploaded to your private "
                       "cloud account.")

__all__ = [
    "LOCAL_LINE", "CLOUD_LINE",
    "LOCAL_LOAD_SENTENCE", "CLOUD_LOAD_SENTENCE",
    "is_cloud_mode", "data_location_line", "tutorial_load_line",
]


def is_cloud_mode() -> bool:
    """True when the app runs against the Supabase/cloud backend.

    Same check the rest of the app uses (auth.get_auth_backend() ==
    "supabase"). The auth import is lazy so importing this module
    can never create a cycle; any failure to detect means local.
    """
    try:
        import auth
        return auth.get_auth_backend() == "supabase"
    except Exception:  # noqa: BLE001 - undetectable backend = local wording
        return False


def data_location_line(cloud: bool | None = None) -> str:
    """The data-location sentence for report/PDF/PPTX/share footers.

    cloud=True -> the cloud wording; cloud=False -> the local wording
    verbatim; cloud=None (default) -> auto-detect the backend.
    """
    if cloud is None:
        cloud = is_cloud_mode()
    return CLOUD_LINE if cloud else LOCAL_LINE


def tutorial_load_line(cloud: bool | None = None) -> str:
    """The trailing sentence of the tutorial's "Load a file" step.

    cloud=True -> the cloud wording; cloud=False -> the original
    sentence verbatim; cloud=None (default) -> auto-detect.
    """
    if cloud is None:
        cloud = is_cloud_mode()
    return CLOUD_LOAD_SENTENCE if cloud else LOCAL_LOAD_SENTENCE
