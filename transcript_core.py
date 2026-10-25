"""Small, dependency-light helpers for the YouTube transcript MCP server."""
from __future__ import annotations
import re
from urllib.parse import parse_qs, urlparse

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be", "www.youtube-nocookie.com", "youtube-nocookie.com"}


def parse_video_id(url_or_id: str) -> str:
    """Parse a YouTube URL or bare video ID without following arbitrary URLs."""
    if not isinstance(url_or_id, str) or len(url_or_id) > 2048:
        raise ValueError('Geef een YouTube-link van maximaal 2048 tekens op.')
    value = url_or_id.strip()
    if VIDEO_ID.fullmatch(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port:
        raise ValueError('Geef een geldige openbare HTTPS-YouTube-link op.')
    host = parsed.hostname or ''
    parts = [p for p in parsed.path.split('/') if p]
    if host in {'youtu.be', 'www.youtu.be'}:
        candidate = parts[0] if len(parts) == 1 else ''
    elif parts and parts[0] in {'shorts', 'live', 'embed', 'v'}:
        candidate = parts[1] if len(parts) == 2 else ''
    elif parsed.path.rstrip('/') == '/watch':
        candidate = parse_qs(parsed.query).get('v', [''])[0]
    else:
        candidate = ''
    if not VIDEO_ID.fullmatch(candidate):
        raise ValueError('De YouTube-link bevat geen herkenbare video-ID.')
    return candidate


def validate_page_arguments(offset: int, limit: int) -> None:
    if type(offset) is not int or type(limit) is not int or offset < 0 or not (1 <= limit <= 200):
        raise ValueError('offset moet >= 0 zijn en limit tussen 1 en 200.')


def make_page(segments: list[dict], offset: int, limit: int) -> dict:
    validate_page_arguments(offset, limit)
    page = segments[offset: offset + limit]
    next_offset = offset + len(page) if offset + len(page) < len(segments) else None
    return {'segments': page, 'total_segments': len(segments), 'next_offset': next_offset}
