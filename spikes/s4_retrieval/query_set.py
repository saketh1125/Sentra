"""
Sentra P0 / Spike S4 — hand-labelled retrieval ground truth.

These are questions a developer would plausibly ask when reading an unfamiliar
repository, with the file and line range that genuinely answers each one.

AUTHORING RULE: every entry below was written by reading the chunk inventory
produced by spike S1 for the pinned `requests` checkout, so the expected
location is verified to exist and to be the right answer -- it is not guessed.

This set is EVALUATION data for the retrieval layer. It must never be used to
tune thresholds (see data-strategy rule: freeze thresholds before measuring).
Chunk boundaries shift between pinned commits, so `expected_line` is validated
against the live chunk index at measurement time and entries that no longer
resolve are reported rather than silently dropped.
"""

from __future__ import annotations

# (question, expected_file, expected_line, note)
QUERIES: list[tuple[str, str, str, int, str]] = [
    (
        "How do I check whether a response status indicates success?",
        "src/requests/models.py", "Response.ok", 861,
        "Response.ok property",
    ),
    (
        "How is the HTTP basic authentication header value built?",
        "src/requests/auth.py", "_basic_auth_str", 34,
        "encodes username:password to base64",
    ),
    (
        "How does requests decide whether a proxy should be bypassed?",
        "src/requests/utils.py", "should_bypass_proxies", 810,
        "proxy bypass decision logic",
    ),
    (
        "Where is a redirect target parsed and validated?",
        "src/requests/sessions.py", "SessionRedirectMixin.get_redirect_target", 134,
        "redirect target resolution",
    ),
    (
        "How are cookies from a jar merged into a request?",
        "src/requests/cookies.py", "merge_cookies", 604,
        "cookie merging",
    ),
    (
        "How is TLS certificate verification performed for a connection?",
        "src/requests/adapters.py", "HTTPAdapter.cert_verify", 307,
        "cert verification + CA bundle handling",
    ),
    (
        "What is the default User-Agent string?",
        "src/requests/utils.py", "default_user_agent", 942,
        "default UA string",
    ),
    (
        "How is JSON decoded from a response body?",
        "src/requests/models.py", "Response.json", 1091,
        "JSON response decoding",
    ),
    (
        "How are files encoded into a multipart request body?",
        "src/requests/models.py", "RequestEncodingMixin._encode_files", 182,
        "multipart encoding",
    ),
    (
        "How is the Content-Length header computed for a prepared request?",
        "src/requests/models.py", "PreparedRequest.prepare_content_length", 654,
        "content length calculation",
    ),
    (
        "What data structure provides case-insensitive header lookups?",
        "src/requests/structures.py", "CaseInsensitiveDict", 20,
        "case-insensitive dict",
    ),
    (
        "How is an HTTP digest authentication challenge answered?",
        "src/requests/auth.py", "HTTPDigestAuth.handle_401", 273,
        "digest auth 401 handling",
    ),
    (
        "How do I mount a custom adapter for a URL prefix on a session?",
        "src/requests/sessions.py", "Session.mount", 888,
        "adapter mounting",
    ),
    (
        "How are query parameters encoded into a URL path?",
        "src/requests/models.py", "RequestEncodingMixin.path_url", 111,
        "URL path/query encoding",
    ),
    (
        "How is the text encoding of a response guessed from its headers?",
        "src/requests/utils.py", "get_encoding_from_headers", 569,
        "encoding detection from headers",
    ),
    (
        "How is HTTP basic auth decoded when a server sends a 401?",
        "src/requests/auth.py", "HTTPBasicAuth.__call__", 111,
        "basic auth handling of 401",
    ),
    (
        "Where are response header links parsed from?",
        "src/requests/utils.py", "parse_header_links", 965,
        "Link header parsing",
    ),
    (
        "How is a zipped archive extracted to a destination directory?",
        "src/requests/utils.py", "extract_zipped_paths", 290,
        "safe zip extraction",
    ),
    (
        "How are request and response hooks dispatched?",
        "src/requests/hooks.py", "dispatch_hook", 32,
        "hook dispatch",
    ),
    (
        "How does a stream of response content get decoded incrementally?",
        "src/requests/models.py", "Response.iter_content", 914,
        "iter_content generator",
    ),
    (
        "How is the connection pool created and configured?",
        "src/requests/adapters.py", "HTTPAdapter.init_poolmanager", 239,
        "urllib3 pool manager setup",
    ),
    (
        "How are proxies selected from the configuration?",
        "src/requests/utils.py", "select_proxy", 885,
        "proxy selection",
    ),
    (
        "How is a Session object constructed and configured?",
        "src/requests/sessions.py", "Session.__init__", 442,
        "Session constructor",
    ),
    (
        "How are HTTP exceptions such as ConnectionError defined?",
        "src/requests/exceptions.py", "ConnectionError", 70,
        "exception hierarchy",
    ),
]

TARGET_REPO = "requests"


def queries_for(repo_name: str) -> list[tuple[str, str, str, int, str]]:
    if repo_name != TARGET_REPO:
        return []
    return QUERIES