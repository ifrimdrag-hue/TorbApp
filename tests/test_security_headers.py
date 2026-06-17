"""Regression test: security headers must be present on every response."""


def test_security_headers_present(client):
    rv = client.get('/healthz')
    assert rv.headers.get('X-Content-Type-Options') == 'nosniff'
    assert rv.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert rv.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    assert 'max-age=' in rv.headers.get('Strict-Transport-Security', '')
    csp = rv.headers.get('Content-Security-Policy', '')
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
