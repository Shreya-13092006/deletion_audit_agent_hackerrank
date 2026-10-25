"""Evidence-card store: lossless persistence, fingerprint invalidation, fail-safe rebuild, lookups."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import agent_fixtures as af

from audit import config
from audit.agent.cards import fingerprint, load_or_build
from audit.parsers import load_evidence


class CardStoreTests(unittest.TestCase):
    def test_rehydrated_cards_equal_fresh_parse(self):
        cards, *_ = af.env()
        again = load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json", af.CARDS_TMP)
        fresh = load_evidence(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json")
        self.assertEqual(again.source, "cache")
        self.assertEqual(again.store.observations, fresh.observations)
        self.assertEqual(again.store.covers, fresh.covers)
        self.assertEqual(again.store.links, fresh.links)
        self.assertEqual(again.meta["cards"], len(fresh.observations))

    def test_file_is_deterministic(self):
        tmp = Path(tempfile.mkdtemp()) / "c.json"
        load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json", tmp)
        first = tmp.read_bytes()
        load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json", tmp, rebuild=True)
        self.assertEqual(first, tmp.read_bytes())

    def test_fingerprint_changes_with_screenshot_facts(self):
        tmpdir = Path(tempfile.mkdtemp())
        img = tmpdir / "image_facts.json"
        shutil.copy(config.CACHE_DIR / "image_facts.json", img)
        before = fingerprint(config.DATASET_DIR, img)
        img.write_text(img.read_text(encoding="utf-8") + " ", encoding="utf-8")
        self.assertNotEqual(before, fingerprint(config.DATASET_DIR, img))

    def test_corrupt_or_stale_file_is_rebuilt(self):
        tmp = Path(tempfile.mkdtemp()) / "c.json"
        tmp.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json", tmp).source,
                         "rebuilt")
        payload = json.loads(tmp.read_text(encoding="utf-8"))
        payload["meta"]["fingerprint"] = "0" * 64
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json", tmp).source,
                         "rebuilt")

    def test_index_lookups(self):
        cards, *_ = af.env()
        hits = cards.cards_for_identifier("user_26")
        self.assertTrue(hits and all("user_26" in c["users"] for c in hits))
        self.assertTrue(all(c["resource_id"] == "account_994" for c in cards.cards_for_resource("account_994")))
        self.assertTrue(all(c["evidence_id"] == "evidence_05" for c in cards.cards_for_evidence("evidence_05")))


    def test_conflicting_readings_stay_separate_cards_with_provenance(self):
        from audit.agent.cards import build_payload, observation_of
        from audit.parsers import EvidenceStore
        from helpers import obs
        a = obs("account_9", "ABSENT", "2026-09-01T00:00:00Z", "evidence_a", source="sql:primary", replica="primary")
        b = obs("account_9", "PRESENT", "2026-09-01T00:00:00Z", "evidence_a", source="sql:replica", replica="read_replica",
                phones={"+1 555 0100"})
        payload = build_payload(EvidenceStore(manifest={}, observations=[a, b]), "fp")
        cards = [payload["cards"][i] for i in payload["index"]["resource"]["account_9"]]
        self.assertEqual([(c["state"], c["source"], c["replica"]) for c in cards],
                         [("ABSENT", "sql:primary", "primary"), ("PRESENT", "sql:replica", "read_replica")])
        self.assertEqual([observation_of(c) for c in cards], [a, b])        # lossless, incl. phones


if __name__ == "__main__":
    unittest.main()
