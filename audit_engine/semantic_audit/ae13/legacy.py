"""D1 verified compatibility ADAPTER: historical extractor → bounded observations.

A legacy symbol classification remains an observation and never becomes a
verified finding. The API is additive and does not invoke the write-capable
historical runner. Source content is checked before and after extraction.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat

from audit_engine.semantic_audit.extractors.ast_extractor import ASTExtractor
from audit_engine.semantic_audit.analyzers.symbol_classifier import SymbolClassifier
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from .identity import digest
from .admission import validate_graph

MAX_FILES = 2500
MAX_BYTES = 2_000_000
EXCLUDE = frozenset({'.git', '.venv', 'venv','__pycache__','.pytest_cache','.tox'})
SCHEMA='ae13/legacy_observation_adapter/v1'


def _file(root: Path, relative: str):
    p=PurePosixPath(relative)
    if not relative or p.is_absolute() or '\\' in relative or any(t in ('','.', '..') for t in relative.split('/')) or not relative.endswith('.py'):
        raise ValueError('Unsafe source path')
    path=root
    for piece in p.parts:
        path=path/piece
        if path.is_symlink():
            raise ValueError('Symlinked source component')
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Source must be a regular file')
    return path


def _paths(root):
    out=[]
    for parent,dirs,files in os.walk(root,followlinks=False):
        # Source omissions through hidden symlink directories cannot be clean.
        if any((Path(parent)/d).is_symlink() for d in dirs if d not in EXCLUDE):
            raise ValueError('Symlinked source directory requires explicit exclusion')
        dirs[:]=sorted(d for d in dirs if d not in EXCLUDE)
        for name in sorted(files):
            if name.endswith('.py'):
                out.append((Path(parent)/name).relative_to(root).as_posix())
            if len(out)>MAX_FILES:
                raise ValueError('Exceeded source-file count budget')
    return out


def adapt_legacy(source_root: Path | str, *, selected_paths: tuple[str,...] | None=None) -> dict:
    root=Path(source_root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Source root must be a real directory')
    selected=tuple(selected_paths) if selected_paths is not None else tuple(_paths(root))
    if not selected:
        raise ValueError('Empty Python source selection')
    if len(selected)>MAX_FILES or len(set(selected))!=len(selected):
        raise ValueError('Repeated or excessive source selection')
    graph=SemanticGraph()
    extractor=ASTExtractor()
    classifier=SymbolClassifier()
    records=[]; issues=[]; sources=[]
    for rel in sorted(selected):
        path=_file(root,rel)
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size>MAX_BYTES:
                raise ValueError('Unsafe source type or size')
            with os.fdopen(fd,'rb',closefd=False) as stream:
                raw=stream.read(MAX_BYTES+1)
            after=os.fstat(fd)
            if len(raw)>MAX_BYTES or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                raise ValueError('Source changed or exceeded budget during admission')
        finally:
            os.close(fd)
        source_hash=hashlib.sha256(raw).hexdigest()
        # The legacy extractor only handles UTF-8; do not erase that limitation.
        try:
            raw.decode('utf-8')
            imports,calls=extractor.extract(path)
        except (UnicodeError, SyntaxError) as exc:
            issues.append({'path':rel,'kind':'legacy_parse_unsupported','type':type(exc).__name__})
            sources.append({'path':rel,'sha256':source_hash,'status':'unparsed'})
            continue
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=source_hash:
            raise ValueError('Source replaced during legacy extraction')
        sources.append({'path':rel,'sha256':source_hash,'status':'parsed'})
        srcid='source:'+digest([rel,source_hash])
        graph.add_node(SemanticNode(srcid,'SourceArtifact',metadata={'path':rel,'sha256':source_hash}))
        seen={}
        for kind,rows in (('import',imports),('call',calls)):
            for item in rows:
                if kind=='import':
                    spelling=item.module
                    symbols=list(item.imported_symbols)
                    classes=[classifier.classify(item,s) for s in (symbols or [''])]
                    classifications=[{'classification':c.classification,'reason':c.reason,'symbol':c.symbol} for c in classes]
                    # Legacy cannot retain relative-level semantics or resolve runtime imports.
                    uncertainty=['module_resolution_not_performed']
                    if not spelling:
                        uncertainty.append('empty_module_or_relative_import_level_lost')
                    elif symbols:
                        uncertainty.append('import_from_relative_level_not_preserved')
                    payload={'module_spelling':spelling,'imported_symbols':symbols,
                             'classifications':classifications}
                else:
                    payload={'symbol_spelling':item.symbol,'usage_type':item.usage_type}
                    uncertainty=['callee_unresolved','receiver_or_scope_not_preserved']
                key=(kind,item.line,digest(payload))
                idx=seen.get(key,0);seen[key]=idx+1
                occurrence_id='legacy-occ:'+digest([rel,source_hash,kind,item.line,idx,payload])
                rec={'id':occurrence_id,'kind':kind,'path':rel,'line':item.line,
                     'source_sha256':source_hash,'payload':payload,'uncertainty':uncertainty,
                     'epistemic_status':'observed','verification_status':'not_verified'}
                records.append(rec)
                graph.add_node(SemanticNode(occurrence_id,'LegacyObservation',metadata={'path':rel,'line':item.line}))
                graph.add_edge(SemanticEdge(srcid,occurrence_id,'HAS_SOURCE_OBSERVATION',metadata={'ae13_occurrence_id':occurrence_id}))
    admitted=validate_graph(graph)
    output={'schema':SCHEMA,'source_root_policy':'explicit_regular_utf8_python_files',
            'sources':sources,'observations':records,'issues':issues,'graph':graph.to_dict(),
            'graph_admission':admitted,
            'assurance_status':'incomplete' if issues else 'source_bound_observations_only',
            'findings':[], 'compatibility':{'legacy_classifier':'preserved_as_observations',
                                           'promoted_verified_findings':0}}
    output['report_sha256']=digest(output)
    return output


def validate_legacy_report(report, source_root):
    if report.get('schema')!=SCHEMA or report.get('report_sha256')!=digest({k:v for k,v in report.items() if k!='report_sha256'}):
        raise ValueError('Legacy adapter report digest mismatch')
    # Replay is authoritative, not self-certification of an arbitrarily rehashed report.
    replay=adapt_legacy(source_root,selected_paths=tuple(r['path'] for r in report['sources']))
    if report!=replay:
        raise ValueError('Legacy adapter report differs from independent replay')
    return True
