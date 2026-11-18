import contextlib
import io
import unittest


class QuietTestCase(unittest.TestCase):
    """Swallows the progress lines the code prints, so the test output stays readable."""

    def run(self, result=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return super().run(result)
