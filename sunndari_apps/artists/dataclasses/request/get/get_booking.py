from dataclasses import dataclass


@dataclass
class GetArtistBookingRequest:
    booking_id: int
    values: str = ''
