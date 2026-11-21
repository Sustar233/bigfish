"""Preserve current image service and its existing fixes; add a GIF-specific path."""
import ast


def once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError('unexpected_gif_patch_anchor: ' + anchor[:60])
    return source.replace(anchor, replacement, 1)


def patch_service(source):
    source = once(source, 'import base64\n', 'import base64\nfrom gif_output import wants_gif, storyboard_prompt, encode_storyboard, validate_gif, deliver_gif\n')
    source = once(source, "    raise ValueError('invalid_image_type')", "    if raw.startswith((b'GIF87a', b'GIF89a')):\n        validate_gif(raw)\n        return 'gif'\n    raise ValueError('invalid_image_type')")
    anchor = "                if job['kind'] == 'edit'"
    # Live versions also accept attached reference images for a new generation.
    lines = source.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.startswith(anchor) and line.rstrip().endswith(':')]
    if len(matches) != 1:
        raise ValueError('unexpected_generation_dispatch')
    i = matches[0]
    lines.insert(i, "                animated = wants_gif(job['prompt'])\n                render_prompt = storyboard_prompt(job['prompt']) if animated else job['prompt']\n")
    source = ''.join(lines)
    if "self.generator(job['prompt']," not in source:
        raise ValueError('generator_anchor_missing')
    source = source.replace("self.generator(job['prompt'],", 'self.generator(render_prompt,')
    source = once(source, '                suffix = image_bytes(raw)\n',
        '                if animated:\n                    raw = encode_storyboard(raw)\n                suffix = image_bytes(raw)\n')
    anchor = "            result = self.request(job['bot'], 'send_private_msg', {'user_id': int(OWNER),\n                'message': [{'type': 'image', 'data': {'file': 'base64://' + base64.b64encode(raw).decode()}}]})\n            if result.get('message_id') is None:\n                raise RuntimeError('missing_receipt')\n            self.mark(job['id'], 'sent', message_id=str(result['message_id']))\n            log('image_sent', job=job['id'], bot=job['bot'], message_id=result['message_id'])"
    replacement = """            if raw.startswith((b'GIF87a', b'GIF89a')):
                result = deliver_gif(self.request, job['bot'], OWNER, job['id'], raw)
                receipt = result.get('file_id') or result.get('message_id')
            else:
                result = self.request(job['bot'], 'send_private_msg', {'user_id': int(OWNER),
                    'message': [{'type': 'image', 'data': {'file': 'base64://' + base64.b64encode(raw).decode()}}]})
                receipt = result.get('message_id')
            if receipt is None:
                raise RuntimeError('missing_receipt')
            self.mark(job['id'], 'sent', message_id=str(receipt))
            log('image_sent', job=job['id'], bot=job['bot'], message_id=receipt)"""
    source = once(source, anchor, replacement)
    ast.parse(source)
    return source
