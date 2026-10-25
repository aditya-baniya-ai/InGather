"""RFC 5545 calendar invite for a confirmed meetup. Contains only what every participant already sees."""

from datetime import timedelta

from app.models import Plan, Proposal
from app.services.clock import as_utc
from app.models import now


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, raw = [], line.encode()
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 sequence
            cut -= 1
        out.append(raw[:cut].decode())
        raw = b" " + raw[cut:]
    out.append(raw.decode())
    return "\r\n".join(out)


def ics(proposal: Proposal, plan: Plan, base_url: str) -> str:
    fmt = "%Y%m%dT%H%M%SZ"
    start = as_utc(proposal.start_at)
    end = as_utc(proposal.end_at) if proposal.end_at else start + timedelta(minutes=90)
    details = proposal.venue_details or {}
    location = ", ".join(x for x in (proposal.venue_label, details.get("address"), plan.city) if x)
    room = f"{base_url.rstrip('/')}/proposals/{proposal.id}/room"
    desc = (f"InGather group meetup at a public place.\nGather Room: {room}\n"
            "Meet only at the public place, arrange your own transport, and tell someone you trust where you'll be.")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//InGather//Meetups//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{proposal.id}-v{proposal.version}@ingather",
        f"DTSTAMP:{now().strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{_esc(proposal.activity_title)}",
        f"LOCATION:{_esc(location)}",
        f"DESCRIPTION:{_esc(desc)}",
        f"URL:{room}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
