# YouTube transcript MCP server

Read-only MCP server for publicly available YouTube captions. No paid transcript API, cookies, audio/video downloads, or proxy service.

## Test status — 2026-10-25

The MCP service deploys successfully on Render Free. HTTP transport, tool discovery, input validation and error reporting work. The live caption test from Render fails with HTTP 403 from the YouTube player endpoint. A successful deployment or health check does not prove transcript retrieval works. Automated video summarization is therefore not working for the test video on this host.

The same code retrieved all 329 caption segments for the test video in a development environment. Local unit tests passed. Cloud IP restrictions are a known limitation of the upstream library.

## Run

Install with `pip install -r requirements.txt`, then run `python server.py`. The server listens on `0.0.0.0` using the PORT environment variable (default 8000). MCP endpoint: `/mcp`; health endpoint: `/health`.

Use `get_youtube_transcript(url, offset=0, limit=120)` and follow next_offset until null. Never substitute video metadata for a complete transcript or invent content after a failed request.

The prototype has network time-outs, bounded memory caching and a limit of 10 new video requests per minute per process. Its tool is public and read-only. Render Free has inactivity sleep and monthly usage limits.
