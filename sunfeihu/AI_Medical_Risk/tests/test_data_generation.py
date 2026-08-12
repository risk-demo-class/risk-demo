from scripts.gen_business_data import build_dataset, dataset_fingerprint


def test_default_dataset_sizes():
    data = build_dataset()
    assert {key: len(value) for key, value in data.items()} == {
        "hospitals": 5,
        "doctors": 20,
        "patients": 200,
        "devices": 200,
        "registrations": 500,
        "prescriptions": 500,
        "items": 1000,
        "claims": 500,
    }


def test_same_seed_is_reproducible_and_other_seed_differs():
    first = dataset_fingerprint(build_dataset(42))
    second = dataset_fingerprint(build_dataset(42))
    other = dataset_fingerprint(build_dataset(43))
    assert first == second
    assert first != other


def test_all_sensitive_identifiers_are_hashes():
    data = build_dataset()
    for patient in data["patients"]:
        for field in ("id_card_hash", "insurance_card_hash", "phone_hash"):
            value = patient[field]
            assert len(value) == 64
            int(value, 16)


def test_high_risk_patterns_are_present():
    data = build_dataset()
    patient_one_claim_hospitals = {
        row["hospital_id"] for row in data["claims"][:3]
        if row["patient_id"] == "PAT000001"
    }
    assert len(patient_one_claim_hospitals) == 3
    assert sum(row["license_status"] == "异常" for row in data["doctors"]) == 1
    shared = [row["device_id_hash"] for row in data["devices"][:6]]
    assert len(set(shared)) == 1
