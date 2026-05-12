from seo_bhishma.models.link_sniper import BacklinkCheckRequest, BacklinkCheckResult


def test_backlink_check_request_model():
    req = BacklinkCheckRequest(
        backlink_url="https://example.com/blog",
        target_url="https://target.com",
        expected_anchor="click here",
    )
    assert req.backlink_url == "https://example.com/blog"
    assert req.expected_anchor == "click here"


def test_backlink_check_result_model():
    result = BacklinkCheckResult(
        backlink_url="https://example.com/blog",
        target_url="https://target.com",
        status="Live",
        anchor_status="Present",
        link_exists="Yes",
        actual_anchor_text="click here",
    )
    d = result.model_dump()
    assert d["status"] == "Live"
    assert d["actual_anchor_text"] == "click here"


def test_backlink_check_result_optional_anchor():
    result = BacklinkCheckResult(
        backlink_url="https://example.com",
        target_url="https://target.com",
        status="Not Live",
        anchor_status="N/A",
        link_exists="No",
    )
    assert result.actual_anchor_text is None
