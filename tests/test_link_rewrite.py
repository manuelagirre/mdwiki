from mdwiki.link_rewrite import rewrite_internal_href


def test_md_suffix_stripped():
    assert rewrite_internal_href("../features/Foo.md") == "../features/Foo"


def test_index_md_folds_to_trailing_slash():
    assert rewrite_internal_href("../features/index.md") == "../features/"


def test_bare_index_md_folds_to_dot_slash():
    assert rewrite_internal_href("index.md") == "./"


def test_fragment_preserved():
    assert rewrite_internal_href("../features/Foo.md#some-heading") == "../features/Foo#some-heading"


def test_pure_fragment_link_untouched():
    assert rewrite_internal_href("#some-heading") == "#some-heading"


def test_external_scheme_untouched():
    assert rewrite_internal_href("https://example.com/x.md") == "https://example.com/x.md"


def test_mailto_untouched():
    assert rewrite_internal_href("mailto:a@example.com") == "mailto:a@example.com"


def test_non_md_target_untouched():
    assert rewrite_internal_href("../screenshots/foo.png") == "../screenshots/foo.png"


def test_empty_href_untouched():
    assert rewrite_internal_href("") == ""
