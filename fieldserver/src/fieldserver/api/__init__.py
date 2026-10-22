"""The HTTP surface, one module per thing it is for.

They were a single thousand-line factory, which is fine while it is being
written and unreadable by the time somebody wants to change one route. Each
module here exposes `register(app, deps)` and closes over the stores exactly as
before — the split was a cut, not a rewrite, which is why the bodies read the
same and the tests did not move.

`Deps` is the only new idea: the stores and the four auth helpers, handed over
once, so a route module never reaches for a global.
"""

from . import (analysis, captures, corpus, dictations, fleet, gallery, generate,
               identity, labels, listening, logs, promo, public, scout, training,
               trees)

#: In the order a request is most likely to arrive.
SECTIONS = (public, identity, captures, analysis, dictations, labels, logs, fleet,
            training, listening, gallery, generate, promo, corpus, trees, scout)


def register_all(app, deps) -> None:
    for section in SECTIONS:
        section.register(app, deps)
