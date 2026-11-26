"""Line-oriented workflow YAML observations; not a YAML parser."""
import re
_PATTERN = re.compile(r"^(?P<indent> *)(?P<key>name|on|jobs|steps|uses|run|with|if|needs|permissions|env|strategy|matrix)\s*:\s*(?P<value>.*)$")
class WorkflowLexicalExtractor:
    def extract_source(self, source, file_path):
        text = source.decode("utf-8", errors="strict")
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            match = _PATTERN.match(line)
            if match:
                rows.append({"file":file_path,"line":number,"indent":len(match.group("indent")),"key":match.group("key"),"value":match.group("value").split(" #",1)[0].rstrip()})
        return rows
