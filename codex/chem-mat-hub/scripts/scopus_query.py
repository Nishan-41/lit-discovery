"""Compile natural-language searches without exposing chemistry punctuation as syntax."""
import re


def expression(value, *, simplified=False):
    value = str(value).translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))
    # Existing upstream adapter adds this wrapper; callers supply plain search text.
    if value.startswith('TITLE-ABS-KEY(') and value.endswith(')'):
        value=value[len('TITLE-ABS-KEY('):-1]
    terms=re.findall(r'"([^"\n]+)"|(\S+)',value)
    parts=[]
    for quoted,token in terms:
        token=quoted or token
        if simplified:
            parts.extend(re.findall(r'[A-Za-z0-9]+',token))
        elif re.fullmatch('[A-Za-z0-9]+',token) and token.upper() not in ('AND','OR','NOT'):
            parts.append(token)
        else:
            parts.append('"'+token.replace('"','').replace('\\','')+'"')
    if simplified:
        parts=[('"'+p+'"') if p.upper() in ('AND','OR','NOT') else p for p in parts]
    if not parts:raise ValueError('Scopus query must contain search terms')
    return 'TITLE-ABS-KEY('+' AND '.join(parts)+')'


def safe_error_code(response):
    """Never store arbitrary server messages: they can echo credentials or URLs."""
    try:
        payload=response.json()
        error=payload.get('service-error',{}).get('status',{})
        code=error.get('statusCode') or payload.get('error-response',{}).get('error-code')
        if isinstance(code,str) and re.fullmatch('[A-Z_]{1,64}',code):return code
    except (ValueError,TypeError,AttributeError):pass
    return None
