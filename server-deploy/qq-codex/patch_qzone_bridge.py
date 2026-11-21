"""Patch only the explicit private command path; retain existing live features."""
import ast
import re


def patch_source(source):
    if 'from qzone_commands import qzone_command' in source:
        raise ValueError('qzone hook already present; inspect before changing')
    anchor = 'from qq_data import Data, approved_persona\n'
    if source.count(anchor) != 1:
        raise ValueError('unexpected import layout')
    source = source.replace(anchor, anchor + 'from qzone_commands import qzone_command\n', 1)
    hook = ('        qzone_reply = qzone_command(text, self.request, self.config, self.store.data.root)\n'
            '        if qzone_reply is not None:\n'
            '            return qzone_reply, None\n')
    source, count = re.subn(r'(?m)^(    def command\(self, text, key[^\n]*\):\n)',
                            lambda m: m[1] + hook, source)
    if count != 1:
        raise ValueError('unexpected command layout')
    anchor = r'\n/清空：新话题'
    if source.count(anchor) != 1:
        raise ValueError('unexpected help layout')
    source = source.replace(anchor, r'\n/空间点赞：赞你最新可见的说说\n/空间状态' + anchor, 1)
    ast.parse(source)
    return source
