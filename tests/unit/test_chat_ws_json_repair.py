"""Unit tests for chat_ws JSON repair helpers."""

import json
import pytest

from renpy_mcp.utils.json_repair import _extract_json_block, _repair_json_text


class TestExtractJsonBlock:
    def test_extracts_plain_object(self):
        text = '{"a": 1}'
        assert _extract_json_block(text) == '{"a": 1}'

    def test_extracts_object_with_prefix_text(self):
        text = 'Here is the JSON:\n{"a": 1}'
        assert _extract_json_block(text) == '{"a": 1}'

    def test_extracts_object_with_suffix_text(self):
        text = '{"a": 1}\nHope this helps!'
        assert _extract_json_block(text) == '{"a": 1}'

    def test_extracts_nested_object(self):
        text = 'Some text{"outer": {"inner": 1}}more text'
        assert _extract_json_block(text) == '{"outer": {"inner": 1}}'

    def test_extracts_array(self):
        text = 'prefix [1, 2, 3] suffix'
        assert _extract_json_block(text) == '[1, 2, 3]'

    def test_returns_none_when_no_json(self):
        assert _extract_json_block("just text") is None

    def test_returns_none_on_mismatched_braces(self):
        assert _extract_json_block('{"a": 1]') is None

    def test_skips_strings_inside_json(self):
        text = '{"msg": "} not a close"}'
        assert _extract_json_block(text) == '{"msg": "} not a close"}'


class TestRepairJsonText:
    def test_removes_trailing_comma_in_object(self):
        raw = '{"a": 1,}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"a": 1}

    def test_removes_trailing_comma_in_array(self):
        raw = '[1, 2, 3,]'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == [1, 2, 3]

    def test_removes_trailing_comma_in_nested_object(self):
        raw = '{"outer": {"inner": 1,},}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"outer": {"inner": 1}}

    def test_removes_trailing_comma_in_nested_array(self):
        raw = '{"items": [1, 2,]}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"items": [1, 2]}

    def test_preserves_commas_inside_strings(self):
        raw = '{"text": "Hello, world!",}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"text": "Hello, world!"}

    def test_preserves_commas_in_middle(self):
        raw = '{"a": 1, "b": 2,}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"a": 1, "b": 2}

    def test_extracts_and_repairs_from_mixed_text(self):
        raw = 'Sure! Here is the JSON:\n```json\n{"a": 1,}\n```\nLet me know if you need more!'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"a": 1}

    def test_removes_single_line_comments(self):
        raw = '{\n  "a": 1, // this is a comment\n  "b": 2\n}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"a": 1, "b": 2}

    def test_preserves_slashes_inside_strings(self):
        raw = '{"url": "http://example.com",}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"url": "http://example.com"}

    def test_handles_escaped_quotes(self):
        raw = '{"quote": "She said \\"hello\\",",}'
        repaired = _repair_json_text(raw)
        assert json.loads(repaired) == {"quote": 'She said "hello",'}
