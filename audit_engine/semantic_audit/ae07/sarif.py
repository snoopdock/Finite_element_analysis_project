"""Deterministic SARIF 2.1.0 interchange of *verified* AE-07 findings only.

SARIF is a reporting format, not proof of analyzer correctness or compliance.
"""
from __future__ import annotations

from audit_engine.semantic_audit.ae01.publication import canonical, sha


def render_sarif(portfolio: dict) -> dict:
    if portfolio.get('schema') != 'ae07/assurance_portfolio/v1':
        raise ValueError('Expected AE-07 verified-portfolio schema')
    # Only truth-bearing verified finding tasks become SARIF results. Incomplete
    # and remediation tasks are properties, not incorrectly labeled violations.
    findings = [x for x in portfolio['review_tasks'] if x['kind'] == 'verified_finding']
    rules = sorted({x['rule_id'] for x in findings})
    results = []
    for row in sorted(findings, key=lambda r: r['id']):
        result = {'ruleId': row['rule_id'], 'level': 'error',
                  'message': {'text': 'Source-bound architecture policy violation; verified within declared audit scope.'},
                  'partialFingerprints': {'ae07FindingIdentity': row['id'],
                                          'sourceSHA256': row['source_sha256']},
                  'properties': {'findingId': row['finding_id'],
                                 'currentGeneration': row['current_generation_id'],
                                 'occurrenceId': row['occurrence_id']}}
        region = {'startLine': max(1, int(row['line'])),
                  'startColumn': max(1, int(row['column']) + 1)}
        result['locations'] = [{'physicalLocation': {
            'artifactLocation': {'uri': row['source_file']},
            'region': region}}]
        results.append(result)
    return {'version': '2.1.0', '$schema': 'https://json.schemastore.org/sarif-2.1.0.json',
            'runs': [{'tool': {'driver': {'name': 'AE-07 Verified Assurance Portfolio',
                                        'semanticVersion': '1.0.0',
                                        'rules': [{'id': rule} for rule in rules]}},
                      'results': results,
                      'properties': {'portfolioSHA256': portfolio['portfolio_sha256'],
                                     'gate': portfolio['gate']['status'],
                                     'releaseAuthorized': False,
                                     'comparableScope': portfolio['scope']['comparable_current_source_and_policy'],
                                     'verifiedFindingCount': len(results)}}]}
