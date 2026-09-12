"""Navigation stack for the player (SPEC.md §5.3).

Pure data structure: no pygame, fully unit-testable.
"""


class NavigationStack:
    """A stack of screen ids representing navigation history.

    ``push`` descends, ``pop`` returns, ``replace`` swaps the top (used for
    auto-advance / ``next`` so that B does not bounce back into a timed
    screen), and ``home`` resets to the package root.
    """

    def __init__(self, root):
        self.root = root
        self._items = [root]

    @property
    def current(self):
        return self._items[-1]

    @property
    def depth(self):
        return len(self._items)

    def push(self, sid):
        self._items.append(sid)
        return sid

    def pop(self):
        """Pop to the previous screen. Returns the new current, or root."""
        if len(self._items) > 1:
            self._items.pop()
        return self.current

    def replace(self, sid):
        """Replace the top of the stack with ``sid``."""
        self._items[-1] = sid
        return sid

    def home(self):
        self._items = [self.root]
        return self.root

    def items(self):
        return list(self._items)
