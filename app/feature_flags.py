"""App-wide feature flags, flipped programmatically (no UI / env).

SHOW_TESTING gates the "Testare" sidebar entry AND the /testare page (route
returns 404 when off, so the page can't be reached by URL in production).
Flip to False when the dev testing round is over.
"""

SHOW_TESTING = True
