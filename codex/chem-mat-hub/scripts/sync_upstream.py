"""Explicit, guarded upstream refresh; preserves the Codex runtime overlay."""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'references' / 'upstream.json'
ENGINE = ROOT / 'scripts' / 'unified_chem_mat_hub.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def check():
    if not MANIFEST.is_file():
        return {'status': 'manifest_missing'}
    baseline = json.loads(MANIFEST.read_text(encoding='utf-8'))
    upstream = Path(os.getenv('CHEM_MAT_HUB_UPSTREAM', baseline['upstream_path']))
    return {'status': 'checked', 'upstream_path': str(upstream),
            'upstream_available': upstream.is_file(),
            'upstream_changed': digest(upstream) != baseline['upstream_sha256'],
            'local_engine_changed': digest(ENGINE) != baseline['managed_engine_sha256']}


def adapt(text):
    text = text.replace('import urllib3\n', '').replace('urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)\n', '')
    old = 'load_dotenv()\nload_dotenv(os.path.expanduser("~/.env"))'
    if old not in text:
        raise ValueError('Upstream environment-loader changed; review required before refresh')
    text = text.replace(old, '''# Process environment wins; optional explicit file then existing user setup.
if os.environ.get("CHEM_MAT_HUB_ENV_FILE"):
    load_dotenv(os.environ["CHEM_MAT_HUB_ENV_FILE"], override=False)
load_dotenv(os.path.expanduser("~/.env"), override=False)''')
    text = text.replace('Antigravity-ResearchHub/1.0', 'Codex-ChemMatHub/1.0').replace(', verify=False', '')
    text = text.replace('http://export.arxiv.org', 'https://export.arxiv.org')
    # A refresh must not restore an upstream developer's hardcoded contact.
    text = re.sub(r' \(mailto:[^)]*\)', '', text)
    text = re.sub(
        r'        r = requests\.get\(f"https://api\.unpaywall\.org/v2/\{clean_doi\}\?email=[^"]+", timeout=4\)',
        '        contact = os.environ.get("CHEM_MAT_HUB_UNPAYWALL_EMAIL")\n'
        '        if not contact:\n            return None\n'
        '        r = requests.get(f"https://api.unpaywall.org/v2/{clean_doi}", params={"email": contact}, timeout=4)',
        text,
    )

    marker = '        kappa_S_cm = float(conductivity_mS_cm) * 1e-3'
    if marker not in text:
        raise ValueError('Upstream Walden interface changed; review required before refresh')
    text = text.replace(marker, '''        values = [conductivity_mS_cm, viscosity_mPa_s, temperature_K]
        if (density_g_cm3 is None) != (molar_mass is None):
            raise ValueError("Supply density and molar mass together.")
        values += [v for v in (density_g_cm3, molar_mass) if v is not None]
        if any(not math.isfinite(float(v)) or float(v) <= 0 for v in values):
            raise ValueError("All supplied Walden inputs must be finite and positive.")
''' + marker)
    text = text.replace('            "walden_metrics": {', '''            "interpretation": "Relative Walden index assumes log10(Lambda) = log10(1/eta_P), intercept 0. This is not a measured free-ion fraction or a validated KCl calibration. Density/MW conversion assumes a neat liquid; use electrolyte concentration for mixtures and ionogels.",
            "walden_metrics": {''')
    text = text.replace('"Structured abstract indexed; full publication text accessible via DOI / publisher portal."', '"Abstract unavailable from this source; full text not yet verified."')
    text = text.replace('"Structured abstract indexed; full publication text accessible via DOI."', '"Abstract unavailable from this source; full text not yet verified."')
    ast.parse(text)
    return text


def refresh():
    status = check()
    if status.get('status') != 'checked' or not status['upstream_available']:
        return {'status': 'blocked', 'reason': 'Upstream or manifest unavailable', 'checks': status}
    if status['local_engine_changed']:
        return {'status': 'blocked', 'reason': 'Local engine modified; refusing to overwrite', 'checks': status}
    if not status['upstream_changed']:
        return {'status': 'unchanged', 'checks': status}
    source = Path(status['upstream_path'])
    candidate = ENGINE.with_name('_upstream_candidate.py')
    try:
        content = adapt(source.read_text(encoding='utf-8'))
        candidate.write_text(content, encoding='utf-8')
        test = "import importlib.util,sys; s=importlib.util.spec_from_file_location('candidate',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); r=m.calculate_walden_ionicity(9.1,32,1.52,391.31); assert abs(r['walden_metrics']['molar_conductivity_Lambda_S_cm2_mol']-2.3427)<0.0001; assert m.calculate_walden_ionicity(-1,32,1.52,391.31)['status']=='error'; assert m.query_polymer_specs('zylon')['status']=='success'"
        verification = subprocess.run([sys.executable, '-c', test, str(candidate)], capture_output=True, timeout=30)
        if verification.returncode:
            return {'status': 'blocked', 'reason': 'Candidate failed local invariant checks; installed engine preserved'}
        # Ensure every current public callable signature still exists in the candidate.
        def signatures(text):
            return {n.name: ast.dump(n.args) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
        old, new = signatures(ENGINE.read_text(encoding='utf-8')), signatures(content)
        if any(new.get(name) != signature for name, signature in old.items()):
            return {'status': 'blocked', 'reason': 'Upstream callable interface changed; installed engine preserved'}
        backup = ENGINE.with_suffix('.py.bak')
        backup.write_bytes(ENGINE.read_bytes())
        candidate.replace(ENGINE)
        baseline = json.loads(MANIFEST.read_text(encoding='utf-8'))
        baseline['upstream_sha256'] = digest(source)
        baseline['managed_engine_sha256'] = digest(ENGINE)
        MANIFEST.write_text(json.dumps(baseline, indent=2), encoding='utf-8')
        return {'status': 'updated', 'backup': str(backup), 'message': 'Codex overlay preserved; restart invocation to load refreshed engine'}
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return {'status': 'blocked', 'reason': type(exc).__name__ + ': ' + str(exc)}
    finally:
        if candidate.is_file():
            candidate.unlink()
