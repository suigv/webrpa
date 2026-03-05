from engine.runner import Runner


def test_scrape_clone_chain_success():
    scrape = Runner().run({"task": "blogger_scrape", "source_key": "k1", "username": "u1", "display_name": "U1"})
    clone = Runner().run({"task": "profile_clone", "source_key": "k1"})
    assert scrape["status"] == "success"
    assert clone["status"] == "success"


def test_profile_clone_missing_source_data():
    clone = Runner().run({"task": "profile_clone", "source_key": "missing_k"})
    assert clone["status"] == "failed"
    assert "missing_source_data" in clone.get("message", "")
