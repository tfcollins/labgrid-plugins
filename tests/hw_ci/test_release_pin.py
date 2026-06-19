import re
from pathlib import Path


def test_recommended_pin_value():
    from adi_lg_plugins.hw_ci._release import RECOMMENDED_PIN

    assert RECOMMENDED_PIN == "v3.5"
    assert re.fullmatch(r"v\d+(\.\d+)*", RECOMMENDED_PIN)


def test_conf_substitution_reads_release_without_import():
    # conf.py must derive |hw_ci_pin| by regex-parsing _release.py (no package import).
    conf = Path("docs/source/conf.py").read_text(encoding="utf-8")
    assert "hw_ci_pin" in conf
    assert "_release.py" in conf
    assert "import adi_lg_plugins" not in conf
