"""The brand.json of the package: the software's, without any station's data."""

import json
import re

from radiotomate.brand import brand_path, label


def test_the_packaged_brand_names_no_address(monkeypatch):
    # A station mounts its own (BUTTON_BRAND), and sets its addresses in the
    # console, Réglages → Station: ADR 0007.
    monkeypatch.delenv("BUTTON_BRAND", raising=False)
    text = brand_path().read_text(encoding="utf-8")
    assert re.findall(r"[a-z]+://[^\"]*", text, re.IGNORECASE) == []
    data = json.loads(text)
    assert not data.get("apps")
    assert "infra" not in data
    assert label("automate", "interfaceName", data) == "BUTTON"
