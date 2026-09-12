"""Player package: manifest interpreter for the R36S daily content player.

Pure logic lives in :mod:`stack`, :mod:`screens` and :mod:`input`; pygame is
confined to :mod:`render`, :mod:`audio`, :mod:`theme` and :class:`app.Player`.
Import :mod:`app.player.app` explicitly to use the pygame-dependent pieces.
"""
