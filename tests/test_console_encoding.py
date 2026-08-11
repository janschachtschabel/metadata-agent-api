"""
The progress output must not be able to kill an upload.

The services report their progress with emoji ('👤 Author VCARD: …'). A Windows
console defaults to cp1252, which cannot encode them, so `print` raises
UnicodeEncodeError — in the middle of a half-finished upload, for an author name
as ordinary as 'Philipp Lang'. Docker and Vercel run UTF-8 and never saw it.
"""

from src import ensure_utf8_output


class _Reconfigurable:
    def __init__(self):
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)


def test_streams_are_switched_to_utf8():
    stream = _Reconfigurable()

    ensure_utf8_output(stream)

    assert stream.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_every_given_stream_is_covered():
    out, err = _Reconfigurable(), _Reconfigurable()

    ensure_utf8_output(out, err)

    assert out.calls and err.calls


def test_a_stream_without_reconfigure_is_left_alone():
    """pytest's capture replaces stdout with an object that has no reconfigure."""
    ensure_utf8_output(object())
