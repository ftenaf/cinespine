"""
TDD Test Suite for Document Preview and Scene/Card Location Explorer.

Evidence:
- references/domain/documents.md
- references/domain/handoffs.md ('Editorial card location lookup & source document verification')
"""
import pytest
from backend.app.spine.writer import SpineWriter
from backend.app.reconciliation.engine import ReconciliationEngine


class TestDocumentPreviewAndCardLocator:
    def setup_method(self):
        self.spine = SpineWriter()
        self.reconciler = ReconciliationEngine()

    def test_store_and_retrieve_source_document(self):
        doc_id = self.spine.store_document(
            production_id="DEMO_PRODUCTION",
            shoot_day="31",
            filename="260728_Report.csv",
            doc_type="sound_ale",
            department="sound",
            content="SOUND REPORT\nDate: 28/07/26\n27-7T01.WAV,27-7,01",
        )
        assert doc_id is not None

        docs = self.spine.list_documents(production_id="DEMO_PRODUCTION", shoot_day="31")
        assert len(docs) == 1
        assert docs[0]["filename"] == "260728_Report.csv"

        doc = self.spine.get_document(doc_id)
        assert doc is not None
        assert "SOUND REPORT" in doc["content"]

    def test_take_aggregates_physical_cards_and_source_refs(self):
        # 1. Camera event from ZoeLog
        self.spine.append_event({
            "event_id": "evt-cam-1",
            "production_id": "DEMO_PRODUCTION",
            "shoot_day": "31",
            "axis": "belief",
            "department": "camera",
            "doc_type": "camera_csv",
            "entity_type": "take",
            "payload": {
                "slate": "27/7",
                "take_id": "1",
                "camera_roll": "A120",
                "clip_name": "A120_C001",
                "source_doc_name": "DemoProduction-2026-7-28_CAM_A.pdf",
            },
        })
        # 2. Sound event
        self.spine.append_event({
            "event_id": "evt-snd-1",
            "production_id": "DEMO_PRODUCTION",
            "shoot_day": "31",
            "axis": "belief",
            "department": "sound",
            "doc_type": "sound_ale",
            "entity_type": "take",
            "payload": {
                "slate": "27/7",
                "take_id": "1",
                "sound_roll": "SR01",
                "source_doc_name": "260728_Report.csv",
            },
        })
        # 3. DIT Silverstack volume event
        self.spine.append_event({
            "event_id": "evt-dit-1",
            "production_id": "DEMO_PRODUCTION",
            "shoot_day": "31",
            "axis": "existence",
            "department": "dit",
            "doc_type": "silverstack_xml",
            "entity_type": "media_file",
            "payload": {
                "file_name": "A120_C001_260728.MOV",
                "camera_roll": "A120",
                "volume_name": "MAG_A_120",
                "checksum": "1b742d797173f0d4",
                "source_doc_name": "Volume-664_SD.xml",
            },
        })

        events = self.spine.get_events("DEMO_PRODUCTION", "31")
        assert len(events) == 3
