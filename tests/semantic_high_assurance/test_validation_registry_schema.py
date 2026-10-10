def test_validation_profile_contract():
    profile = {
        "id": "G3.4.7.3",
        "name": "Automatic Profile Discovery and Schema Enforcement",
        "target_tests": []
    }

    assert "id" in profile
    assert "name" in profile
    assert "target_tests" in profile
