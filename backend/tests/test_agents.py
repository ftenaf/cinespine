"""
TDD Test Suite for Slice 4: Gemini Multimodal Script Extractor & ClickHouse MCP Tools.

Evidence:
- references/domain/documents.md ('Facing and lined pages')
- references/constraints/safety.md ('PII anonymization', 'Read-only query enforcement')
"""
import pytest
from backend.app.agents.multimodal import GeminiScriptLiningExtractor, ExtractedScriptPage
from backend.app.agents.mcp_server import ClickHouseMCPServer, GeminiDiscrepancyAssistant
from backend.app.spine.writer import SpineWriter
from backend.app.reconciliation.engine import ReconciliationEngine


class TestGeminiScriptLiningExtractor:
    def test_parse_structured_script_page_mock(self):
        extractor = GeminiScriptLiningExtractor(api_key=None)  # Uses mock extractor for unit tests
        
        sample_page_json = """
        {
            "scene": "64A",
            "slates": ["21/1"],
            "takes": [
                {"take_id": "1", "camera_rolls": ["A120", "B039"], "is_starred": false},
                {"take_id": "2PK", "camera_rolls": ["A120", "B039"], "is_starred": false},
                {"take_id": "3", "camera_rolls": ["A120", "B039"], "is_starred": true}
            ],
            "lining_notes": "Actor stumbled on line 4, reset from mark B",
            "page_number": 42
        }
        """
        result: ExtractedScriptPage = extractor.validate_and_normalize(sample_page_json)

        assert result.scene == "64A"
        assert len(result.takes) == 3
        assert result.takes[2].take_id == "3"
        assert result.takes[2].is_starred is True
        assert result.takes[1].is_pickup is True

    def test_pii_sanitization_removes_personal_contact_info(self):
        extractor = GeminiScriptLiningExtractor(api_key=None)
        raw_text_with_pii = "Script Supervisor: Jane Doe (Tel: +34 600 123 456, email: jane@filmmaking.com)\nScene 64A Slate 21/1 Take 3"
        
        sanitized = extractor.sanitize_pii(raw_text_with_pii)
        assert "+34 600 123 456" not in sanitized
        assert "jane@filmmaking.com" not in sanitized
        assert "[REDACTED_PHONE]" in sanitized
        assert "[REDACTED_EMAIL]" in sanitized


class TestClickHouseMCPServerAndAssistant:
    def setup_method(self):
        self.spine = SpineWriter()
        self.reconciler = ReconciliationEngine()
        self.mcp = ClickHouseMCPServer(spine_writer=self.spine, reconciler=self.reconciler)
        self.assistant = GeminiDiscrepancyAssistant(mcp_server=self.mcp)

    def test_mcp_query_discrepancies(self):
        # Seed an event on the spine
        self.spine.append_event({
            "event_id": "evt-101",
            "production_id": "PROD_01",
            "shoot_day": "31",
            "axis": "belief",
            "department": "script",
            "doc_type": "script_lined",
            "entity_type": "take",
            "payload": {"slate": "27/7", "take_id": "3", "is_starred": True},
        })
        self.spine.append_event({
            "event_id": "evt-102",
            "production_id": "PROD_01",
            "shoot_day": "31",
            "axis": "belief",
            "department": "camera",
            "doc_type": "camera_csv",
            "entity_type": "take",
            "payload": {"slate": "27/7", "take_id": "3", "is_starred": False},
        })

        discrepancies = self.mcp.query_production_discrepancies(production_id="PROD_01", shoot_day="31")
        assert len(discrepancies) == 1
        assert discrepancies[0]["discrepancy_type"] == "CIRCLED_TAKE_MISMATCH"

    def test_assistant_explains_take_witnesses(self):
        # Seed take witnesses
        self.spine.append_event({
            "event_id": "evt-201",
            "production_id": "PROD_01",
            "shoot_day": "31",
            "axis": "belief",
            "department": "camera",
            "doc_type": "camera_csv",
            "entity_type": "take",
            "payload": {"slate": "27/7", "take_id": "1", "camera_roll": "A120"},
        })
        self.spine.append_event({
            "event_id": "evt-202",
            "production_id": "PROD_01",
            "shoot_day": "31",
            "axis": "belief",
            "department": "sound",
            "doc_type": "sound_ale",
            "entity_type": "take",
            "payload": {"slate": "27/7", "take_id": "1", "sound_roll": "SR01"},
        })

        explanation = self.assistant.explain_take(
            production_id="PROD_01", shoot_day="31", slate="27/7", take_id="1"
        )
        assert "27/7 Take 1" in explanation
        assert "Camera" in explanation
        assert "Sound" in explanation
