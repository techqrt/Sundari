from dataclasses import dataclass

from sunndari_apps.common.dataclasses.request.get_all import GetAll


@dataclass
class GetAllArtistsRequest(GetAll):
    """The usual paged-list parameters plus filters that can be combined, e.g. approval_status=approved with
    registration=unpaid finds the approved artists whose registration payment is still pending."""
    approval_status: str = None
    registration: str = None
    accepting: bool = None
