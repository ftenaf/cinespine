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
from backend.app.script.llm_router import DEFAULT_FLASH_MODEL


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

    def test_no_pinned_model_and_no_end_of_life_sdk(self):
        """
        This class used to pin "gemini-1.5-flash" and build its client with
        google.generativeai, which is end of life. A pinned id 404s the day its
        version is retired, and the constructor swallows the failure, so the
        breakage would be silent.
        """
        import inspect

        from backend.app.agents import multimodal
        from backend.app.script.llm_router import get_optimal_gemini_model

        source = inspect.getsource(multimodal)
        assert "google.generativeai" not in source, "the end-of-life SDK is back"
        assert "gemini-1.5" not in source, "a pinned model id is back"

        extractor = GeminiScriptLiningExtractor(api_key=None)
        assert extractor.model_name == get_optimal_gemini_model("", "simple")

    def test_reports_whether_a_model_can_actually_be_called(self):
        """Validation works with no key; extraction does not. Say which."""
        assert GeminiScriptLiningExtractor(api_key=None).is_available is False

    def test_an_explicit_model_name_still_wins(self):
        extractor = GeminiScriptLiningExtractor(api_key=None, model_name="gemini-3.5-flash")
        assert extractor.model_name == "gemini-3.5-flash"

    def test_a_bad_key_degrades_instead_of_raising(self):
        """A construction failure must not take down the caller."""
        extractor = GeminiScriptLiningExtractor(api_key="not-a-real-key")
        assert isinstance(extractor.is_available, bool)

    def test_validation_still_works_without_any_model(self):
        """The half the parsers actually use must not need a client."""
        extractor = GeminiScriptLiningExtractor(api_key=None)
        page = extractor.validate_and_normalize(
            '{"scene": "12A", "slates": ["3/1"], "takes": [{"take_id": "2", "camera_rolls": ["B039"]}]}'
        )
        assert page.scene == "12A"
        assert page.takes[0].camera_rolls == ["B039"]

    # ---------------------------------------------------------------- #
    # extract_page
    # ---------------------------------------------------------------- #

    @staticmethod
    def _extractor_with_model(monkeypatch, behaviour):
        """A GeminiScriptLiningExtractor whose model follows `behaviour(model)`."""
        from backend.app.agents.multimodal import GeminiScriptLiningExtractor

        calls = []

        class _Models:
            def generate_content(self, model, contents, config):
                calls.append((model, contents, config))
                outcome = behaviour(model)
                if isinstance(outcome, Exception):
                    raise outcome
                return type("R", (), {"text": outcome})()

        class _Client:
            def __init__(self, **kwargs):
                self.models = _Models()

        import google.genai as genai
        monkeypatch.setattr(genai, "Client", _Client)
        return GeminiScriptLiningExtractor(api_key="test-key"), calls

    PAGE_JSON = (
        '{"scene": "64A", "slates": ["21/1"], "page_number": 42, "takes": ['
        '{"take_id": "3*", "camera_rolls": ["A120", "B039"]},'
        '{"take_id": "FALSE", "camera_rolls": ["A120"], "notes": "reset from mark B"}]}'
    )

    def test_extract_page_reads_and_normalizes(self, monkeypatch):
        extractor, calls = self._extractor_with_model(monkeypatch, lambda m: self.PAGE_JSON)
        page = extractor.extract_page(b"fake-png-bytes", "image/png")

        assert page.scene == "64A"
        assert page.slates == ["21/1"]
        starred = [t for t in page.takes if t.is_starred]
        assert [t.take_id for t in starred] == ["3"], "the circled take must survive"
        assert starred[0].camera_rolls == ["A120", "B039"], "leading zeros are preserved"
        assert any(t.is_false_start for t in page.takes), "a false start is a fact, not noise"
        assert len(calls) == 1

    def test_extract_page_sends_the_document_inline(self, monkeypatch):
        extractor, calls = self._extractor_with_model(monkeypatch, lambda m: self.PAGE_JSON)
        extractor.extract_page(b"%PDF-1.4 fake", "application/pdf")

        _model, contents, config = calls[0]
        part = contents[0]
        assert part.inline_data.mime_type == "application/pdf"
        assert part.inline_data.data == b"%PDF-1.4 fake"
        assert config["response_mime_type"] == "application/json"
        assert config["temperature"] == 0.0, "transcription must not be creative"

    def test_extract_page_prefers_the_callers_page_number(self, monkeypatch):
        """The printed number can be misread; the file position cannot."""
        extractor, _ = self._extractor_with_model(monkeypatch, lambda m: self.PAGE_JSON)
        page = extractor.extract_page(b"img", "image/png", page_number=7)
        assert page.page_number == 7

    def test_extract_page_falls_through_to_the_next_model(self, monkeypatch):
        def behaviour(model):
            if model == DEFAULT_FLASH_MODEL:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return self.PAGE_JSON

        extractor, calls = self._extractor_with_model(monkeypatch, behaviour)
        page = extractor.extract_page(b"img", "image/png")
        assert page.scene == "64A"
        assert len(calls) >= 2

    def test_extract_page_raises_when_no_model_can_read_it(self, monkeypatch):
        """
        An empty page is a real answer -- a page that carried no takes. Returning
        one on failure would make an outage look like a blank page.
        """
        extractor, _ = self._extractor_with_model(
            monkeypatch, lambda m: RuntimeError("503 UNAVAILABLE")
        )
        with pytest.raises(RuntimeError, match="No Gemini model could read"):
            extractor.extract_page(b"img", "image/png")

    def test_extract_page_raises_on_an_empty_model_response(self, monkeypatch):
        extractor, _ = self._extractor_with_model(monkeypatch, lambda m: "")
        with pytest.raises(RuntimeError, match="No Gemini model could read"):
            extractor.extract_page(b"img", "image/png")

    def test_extract_page_without_a_key_says_so(self):
        from backend.app.agents.multimodal import GeminiScriptLiningExtractor

        with pytest.raises(RuntimeError, match="No Gemini client"):
            GeminiScriptLiningExtractor(api_key=None).extract_page(b"img", "image/png")

    def test_extract_page_rejects_input_it_cannot_send(self, monkeypatch):
        from backend.app.agents.multimodal import MAX_DOCUMENT_BYTES

        extractor, calls = self._extractor_with_model(monkeypatch, lambda m: self.PAGE_JSON)

        with pytest.raises(ValueError, match="No document bytes"):
            extractor.extract_page(b"", "image/png")
        with pytest.raises(ValueError, match="Unsupported mime type"):
            extractor.extract_page(b"img", "text/plain")
        with pytest.raises(ValueError, match="over the"):
            extractor.extract_page(b"x" * (MAX_DOCUMENT_BYTES + 1), "image/png")

        assert calls == [], "a rejected document must not reach the model"

    def test_extract_page_redacts_contact_details_it_read(self, monkeypatch):
        """
        Lining pages carry the script supervisor's name and contact in the
        header. Sanitisation is applied to what the model returns, not only to
        text handed in by hand.
        """
        page_json = (
            '{"scene": "64A", "takes": [], "lining_notes": '
            '"Script Supervisor ana.ruiz@example.com tel +34 600 123 456"}'
        )
        extractor, _ = self._extractor_with_model(monkeypatch, lambda m: page_json)
        page = extractor.extract_page(b"img", "image/png")

        assert "ana.ruiz@example.com" not in page.lining_notes
        assert "600 123 456" not in page.lining_notes
        assert "[REDACTED_EMAIL]" in page.lining_notes

    @pytest.mark.parametrize("raw, slate, take", [
        ("21/1:4", "21/1", "4"),
        ("21/1:2PK", "21/1", "2PK"),
        ("3", None, "3"),
        ("2PK", None, "2PK"),
        ("", None, ""),
        (":", None, ":"),
        ("21/1:", None, "21/1:"),
    ])
    def test_slate_prefixed_takes_are_split(self, raw, slate, take):
        from backend.app.agents.multimodal import split_slate_take

        assert split_slate_take(raw) == (slate, take)

    def test_a_composite_reference_does_not_survive_as_a_take_id(self):
        """
        Observed against the live model: asked for "the take", it returned the
        whole lining annotation `21/1:1`. That normalises to a take id of
        `21/1:1`, is reported valid, and matches no take in any other document.
        """
        extractor = GeminiScriptLiningExtractor(api_key=None)
        page = extractor.validate_and_normalize(
            '{"scene": "64A", "slates": [], "takes": ['
            '{"take_id": "21/1:1", "camera_rolls": ["A120"]},'
            '{"take_id": "21/1:2PK", "camera_rolls": ["B039"]}]}'
        )
        assert [t.take_id for t in page.takes] == ["1", "2PK"]
        assert page.takes[1].is_pickup is True
        assert page.slates == ["21/1"], "the slate must be recovered, not discarded"

    def test_a_recovered_slate_is_not_duplicated(self):
        extractor = GeminiScriptLiningExtractor(api_key=None)
        page = extractor.validate_and_normalize(
            '{"scene": "64A", "slates": ["21/1"], "takes": ['
            '{"take_id": "21/1:1", "camera_rolls": []},'
            '{"take_id": "21/1:2", "camera_rolls": []}]}'
        )
        assert page.slates == ["21/1"]

    def test_extraction_prompt_carries_the_domain_rules(self):
        """
        The facts a general model cannot infer from the picture: these pages are
        filed per scene across days, so out-of-day rolls belong; take notation
        carries meaning that normalising would destroy; guessing is worse than
        omitting.
        """
        from backend.app.agents.multimodal import EXTRACTION_PROMPT

        lowered = EXTRACTION_PROMPT.lower()
        assert "leading zero" in lowered
        assert "circled" in lowered
        assert "never invent" in lowered
        for notation in ("3*", "2PK", "FALSE", "WT 01"):
            assert notation in EXTRACTION_PROMPT

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
            "department": "script",
            "doc_type": "script_editor_log",
            "entity_type": "take",
            "payload": {"slate": "27/7", "take_id": "3", "is_starred": False},
        })

        discrepancies = self.mcp.query_production_discrepancies(production_id="PROD_01", shoot_day="31")
        kinds = [d["discrepancy_type"] for d in discrepancies]
        assert "CIRCLED_TAKE_MISMATCH" in kinds

        # The day also reports itself as awaiting offload, because takes were
        # logged on it and no offload report has arrived. Asserted rather than
        # tolerated: a day nobody has offloaded used to render as a clean day.
        assert "AWAITING_OFFLOAD" in kinds
        assert len([k for k in kinds if k == "AWAITING_OFFLOAD"]) == 1, "one per day, not one per take"

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
