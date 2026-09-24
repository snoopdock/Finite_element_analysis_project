from processing.capability_contract import CapabilityContract
from processing.contract_validator import validate_contracts


def test_valid_dependency_chain():
    contracts = [
        CapabilityContract(
            name="quality",
            provides=("quality",),
            depends_on=(),
        ),
        CapabilityContract(
            name="feedback",
            provides=("feedback",),
            depends_on=("quality",),
        ),
    ]

    assert validate_contracts(contracts) == []


def test_missing_dependency_is_detected():
    contracts = [
        CapabilityContract(
            name="constraints",
            provides=("constraints",),
            depends_on=("feedback",),
        )
    ]

    assert validate_contracts(contracts) == [
        ("constraints", "feedback")
    ]


def test_validation_is_deterministic():
    contracts = [
        CapabilityContract(
            name="a",
            provides=("a",),
            depends_on=(),
        )
    ]

    assert validate_contracts(contracts) == validate_contracts(contracts)
