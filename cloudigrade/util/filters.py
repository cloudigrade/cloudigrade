"""Custom Jinja2 filters for use in generated documentation."""
import json
import textwrap

from six.moves.http_client import responses


def rst_codeblock(text, code=None):
    """
    Construct a ReStructured Text code block containing the given text.

    Additionally, replace the standard "testserver" with an actual localhost
    address that a reader can simply copy, paste, and use.
    """
    if code:
        prefix = f'.. code:: {code}'
    else:
        prefix = '::'
    output = f'{prefix}\n\n{textwrap.indent(text, "    ", lambda line: True)}'
    output = output.replace(' http://testserver/', ' localhost:8080/').replace(
        'testserver/', 'localhost:8080/'
    )
    return output


def stringify_http_response(response):
    """Construct a (simulated) raw text HTTP response for the given object."""
    try:
        status_text = response.status_text
    except AttributeError:
        status_text = responses.get(response.status_code, '')
    lines = [f'HTTP/1.1 {response.status_code} {status_text}']
    headers = sorted(response.items(), key=lambda x: x[0])
    lines.extend(f'{key}: {value}' for (key, value) in headers)
    fulltext = '\n'.join(lines)
    try:
        body = response.json() if response.content else None
        body = (
            json.dumps(body, indent=4, sort_keys=True)
            if body is not None
            else None
        )
    except ValueError:
        body = (
            response.content.decode('utf-8')
            if response.content
            else None
        )
    if body is not None:
        fulltext = f'{fulltext}\n\n{body}'
    return fulltext


def httpied_command(wsgi_request, version=1):
    """Construct an `httpie` command line string for the given request."""
    verb = wsgi_request.method.lower()
    url = wsgi_request.build_absolute_uri()

    if verb == 'get':
        cli_text = ' '.join(['http', url.split('?')[0]])
    else:
        cli_text = ' '.join(['http', verb, url])
    if version == 2:
        cli_text += ' "X-RH-IDENTITY:${HTTP_X_RH_IDENTITY}"'
    else:
        if getattr(wsgi_request, 'user', None):
            cli_text += ' "${AUTH}"'

    linewrap = ' \\\n    '
    for key, value in wsgi_request.GET.items():
        cli_text += f'{linewrap}{key}=="{value}"'
    for key, value in wsgi_request.POST.items():
        cli_text += f'{linewrap}{key}="{value}"'

    return cli_text
