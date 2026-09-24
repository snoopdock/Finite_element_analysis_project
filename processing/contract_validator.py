from .capability_contract import CapabilityContract


def validate_contracts(contracts):
    names = {contract.name for contract in contracts}

    missing = []

    for contract in contracts:
        for dependency in contract.depends_on:
            if dependency not in names:
                missing.append((contract.name, dependency))

    return missing
