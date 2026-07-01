from xml.etree import ElementTree as ET

import pytest

from adi_lg_plugins.hw_ci.boot_junit import render_boot_junit


def test_pass_has_no_failure_element():
    xml = render_boot_junit(
        place="mini2", part="adrv9002", carrier="zcu102", mode="uri", status="pass", seconds=42
    )
    root = ET.fromstring(xml)
    suite = root.find("testsuite")
    assert suite.attrib["tests"] == "1"
    assert suite.attrib["failures"] == "0"
    case = suite.find("testcase")
    assert case.attrib["name"] == "uri:adrv9002@mini2"
    assert case.attrib["classname"] == "lab-infra.zcu102"
    assert case.find("failure") is None


def test_fail_has_failure_element_with_message():
    xml = render_boot_junit(
        place="jtagbox",
        part="adrv9371",
        carrier="zc706",
        mode="reserve",
        status="fail",
        seconds=7,
        message="adi-lg request exit 20",
    )
    root = ET.fromstring(xml)
    suite = root.find("testsuite")
    assert suite.attrib["failures"] == "1"
    failure = suite.find("testcase/failure")
    assert failure is not None
    assert "exit 20" in failure.attrib["message"]


def test_message_with_xml_metacharacters_is_escaped():
    xml = render_boot_junit(
        place="p", part="x", carrier="c", mode="uri", status="fail", seconds=1, message="a < b & c"
    )
    # Must parse without error -> proves the metacharacters were escaped.
    root = ET.fromstring(xml)
    assert root.find("testsuite/testcase/failure").attrib["message"] == "a < b & c"


def test_skip_has_skipped_element():
    xml = render_boot_junit(
        place="mini2",
        part="adrv9002",
        carrier="zcu102",
        mode="uri",
        status="skip",
        seconds=3,
        message="adi-lg request exit 11",
    )
    root = ET.fromstring(xml)
    suite = root.find("testsuite")
    assert suite.attrib["skipped"] == "1"
    assert suite.attrib["failures"] == "0"
    assert suite.find("testcase/skipped") is not None


def test_unknown_status_raises():
    with pytest.raises(ValueError):
        render_boot_junit(place="p", part="x", carrier="c", mode="uri", status="bogus", seconds=1)
