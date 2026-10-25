"""Read-only YouTube subtitle tool for a private ChatGPT MCP plugin.

Needs publicly available captions. Uses no paid transcript API.
Does not download audio/video or circumvent YouTube access controls.
"""
from __future__ import annotations
import os
import time
from collections import deque
from functools import lru_cache
from threading import Lock
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.transport_security import TransportSecuritySettings
from requests import Session
from starlette.responses import JSONResponse
from starlette.routing import Route
from youtube_transcript_api import YouTubeTranscriptApi
from transcript_core import parse_video_id, make_page, validate_page_arguments

mcp = MCPServer('YouTube Transcript NL')
_fetch_times = deque()
_fetch_lock = Lock()


class FetchRateLimited(Exception):
    pass


class TimeoutSession(Session):
    """Bound each upstream network request; do not retry blocked requests."""
    def request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', (5, 12))
        return super().request(method, url, **kwargs)


def _reserve_fetch():
    # Global per-process limit, independent of spoofable forwarded IP headers.
    # Cached pages do not consume this budget. No background keep-alive traffic.
    now = time.monotonic()
    with _fetch_lock:
        while _fetch_times and now - _fetch_times[0] >= 60:
            _fetch_times.popleft()
        if len(_fetch_times) >= 10:
            raise FetchRateLimited('Maximaal 10 nieuwe video-opvragen per minuut. Probeer over een minuut opnieuw.')
        _fetch_times.append(now)


@lru_cache(maxsize=64)
def _fetch_transcript(video_id: str) -> dict:
    _reserve_fetch()
    with TimeoutSession() as session:
        api = YouTubeTranscriptApi(http_client=session)
        options = list(api.list(video_id))
        if not options:
            raise ValueError('Geen openbare ondertiteling gevonden voor deze video.')
        # Prefer Dutch/English; otherwise use any other accessible caption track.
        options.sort(key=lambda t: (0 if t.language_code.startswith('nl') else (1 if t.language_code.startswith('en') else 2), t.is_generated))
        transcript = options[0].fetch()
    segments = [
        {'start_seconds': round(float(s.start), 1),
         'duration_seconds': round(float(s.duration), 1), 'text': str(s.text).strip()}
        for s in transcript if str(s.text).strip()
    ]
    if not segments:
        raise ValueError('Een ondertitelspoor is gevonden, maar bevat geen tekst.')
    return {'language': transcript.language, 'language_code': transcript.language_code,
            'is_generated': transcript.is_generated, 'segments': segments}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                     idempotentHint=True, openWorldHint=True))
def get_youtube_transcript(url: str, offset: int = 0, limit: int = 120) -> dict:
    """Haal automatisch ondertiteling op voor een gedeelde YouTube-link.

    Gebruik dit wanneer de gebruiker een video deelt of een samenvatting wil.
    Vraag niet meteen de gebruiker om tekst te kopiëren. Lees vervolgstukken
    met next_offset tot het hele transcript verwerkt is. Maak de uiteindelijke
    samenvatting in het Nederlands, ook bij Engelse video. Tijdstempels zijn seconden.
    Dit werkt alleen wanneer openbare captions bereikbaar zijn.
    """
    # Validate before making any upstream request, including pagination arguments.
    try:
        video_id = parse_video_id(url)
        validate_page_arguments(offset, limit)
    except ValueError as exc:
        return {'ok': False, 'error_type': 'InvalidInput', 'message': str(exc)}
    try:
        result = _fetch_transcript(video_id)
    except Exception as exc:
        # These exceptions distinguish unavailable/disabled captions, region or IP blocks.
        # Never manufacture caption text or mislabel a YouTube bot block as 'no captions'.
        error_kind = type(exc).__name__
        return {'ok': False, 'video_id': video_id, 'error_type': error_kind,
                'message': str(exc)[:850],
                'explanation': 'Ondertiteling kan ontbreken of YouTube kan dit verzoek blokkeren. Geen inhoud verzinnen.'}
    page = make_page(result['segments'], offset, limit)
    return {'ok': True, 'video_id': video_id, 'video_url': f'https://www.youtube.com/watch?v={video_id}',
            'language': result['language'], 'language_code': result['language_code'],
            'automatic_captions': result['is_generated'], **page}


async def health(request):
    return JSONResponse({'status': 'ok', 'service': 'youtube-transcript-nl',
                         'note': 'Health does not verify access to YouTube.'})

# v2 MCP SDK's Streamable HTTP transport; no login and no paid API key.
# For private use only. Do not expose unprotected to untrusted users at scale.
_public_hosts = [h.strip() for h in os.environ.get('PUBLIC_HOSTS', '').split(',') if h.strip()]
if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
    _public_hosts.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])
app = mcp.streamable_http_app(
    json_response=True, stateless_http=True, host='0.0.0.0', max_request_body_size=16384,
    transport_security=TransportSecuritySettings(
        allowed_hosts=['127.0.0.1:*', 'localhost:*', *_public_hosts],
        allowed_origins=[f'https://{host}' for host in _public_hosts],
    ),
)
app.router.routes.append(Route('/health', health, methods=['GET']))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8000')))
