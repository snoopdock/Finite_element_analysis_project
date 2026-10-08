from enum import Enum


class AnalysisType(Enum):
    TRAVERSAL = 'traversal'
    DEPENDENCY = 'dependency'
    PATH = 'path'
    CENTRALITY = 'centrality'
