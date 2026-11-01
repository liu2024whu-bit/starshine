from __future__ import annotations

import pytest

from starshine_geo._markdown import inline_code


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ordinary", "`ordinary`"),
        ("地块 café 🌟", "`地块 café 🌟`"),
        ("", '`""`'),
        ("a|b", "`a|b`"),
        ("a\\|b", "`a\\|b`"),
        ("x` *not code* `y", "``x` *not code* `y``"),
        ("`", "`` ` ``"),
        ("``x`y```", "```` ``x`y``` ````"),
        (" x ", "`  x  `"),
        (" x", "` x`"),
        ("x ", "`x `"),
        ("   ", "`   `"),
        ("x`\n\n# Forged heading\n\n`y", "``x`  # Forged heading  `y``"),
        ("a\r\nb\rc\nd\u2028e\u2029f", "`a b c d e f`"),
        ("a\x00b\t\x1bc\x7f", "`a b  c `"),
        ("<b>& [link](https://example.invalid)", "`<b>& [link](https://example.invalid)`"),
    ],
)
def test_inline_code_exact_raw_representation(value: str, expected: str) -> None:
    assert inline_code(value, quote_strings=False) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "`null`"),
        (True, "`true`"),
        (3, "`3`"),
        ("", '`""`'),
        ("x`\n|y", '``"x`\\n|y"``'),
        ({"z": "`", "a": [1, False]}, '``{"a":[1,false],"z":"`"}``'),
    ],
)
def test_inline_code_preserves_json_spelling(value: object, expected: str) -> None:
    assert inline_code(value) == expected


def test_plain_text_keeps_diagnostics_literal_without_changing_normal_prose() -> None:
    from starshine_geo._markdown import plain_text

    assert plain_text("Feature 0 is invalid: non-null geometry required.") == (
        "Feature 0 is invalid: non-null geometry required."
    )
    assert plain_text("<b>&amp;</b> `x` **y** [z](url) ~a~ |\n\n# h") == (
        r"&lt;b&gt;&amp;amp;&lt;/b&gt; \`x\` \*\*y\*\* \[z\](url) \~a\~ \|  \# h"
    )
