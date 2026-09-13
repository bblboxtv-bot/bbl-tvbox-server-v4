from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def prefer_private_render_postgres(url: str) -> str:
    try:
        p = urlsplit(url)
        host = p.hostname or ""
        suffix = ".virginia-postgres.render.com"
        if not host.endswith(suffix):
            return url
        private_host = host[: -len(suffix)]
        netloc = p.netloc.replace(host, private_host)
        query = urlencode([
            (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() != "sslmode"
        ])
        return urlunsplit((p.scheme, netloc, p.path, query, p.fragment))
    except Exception:
        return url
