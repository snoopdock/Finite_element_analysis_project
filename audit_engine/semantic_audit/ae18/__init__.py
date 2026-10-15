"""AE-18 controlled reference effectiveness benchmark, not operational authority."""
from .evaluate import evaluate_corpus, classify
from .publication import publish_evaluation, verify_evaluation
__all__=('evaluate_corpus','classify','publish_evaluation','verify_evaluation')
