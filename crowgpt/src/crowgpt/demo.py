"""The listening pages — six instruments, re-exported from crowgpt.pages.

This was one 2,300-line file, 73% of it template literals, holding six page
classes that never referenced each other. Each now lives in
`crowgpt/pages/<name>.py` beside its own template; the shared helpers and the
one stylesheet are `pages/base.py`. This module stays as the import path —
the experiments, the tests, pool.py and trainer.py all say `crowgpt.demo`,
and a numbered experiment is a historical record that must keep running
unedited. The underscored names are re-exported deliberately: trainer.py and
the tests reach for them by this spelling.
"""

from crowgpt.pages.base import (  # noqa: F401
    DEMO_SR,
    MIN_GRADEABLE_SECONDS,
    PEAKS,
    _check_gradeable,
    _CSS,
    _peaks,
    _wav_data_uri,
)
from crowgpt.pages.abx import ABXPage, _ABX_TEMPLATE  # noqa: F401
from crowgpt.pages.calltype import CallTypePage, _CALLTYPE_TEMPLATE  # noqa: F401
from crowgpt.pages.compare import ComparePage, _COMPARE_TEMPLATE  # noqa: F401
from crowgpt.pages.demo_page import DemoPage, _TEMPLATE  # noqa: F401
from crowgpt.pages.pair import PairPage, _PAIR_TEMPLATE, _by_pairing  # noqa: F401
from crowgpt.pages.rating import (  # noqa: F401
    RatingPage,
    _RATING_DEFAULT_INSTRUCTIONS,
    _RATING_TEMPLATE,
)
