# Contributing to Lit-Discovery

We welcome contributions to expand academic search coverage, citation analytics, and synthesis capabilities!

## Development Setup
```bash
git clone https://github.com/rehan/lit-discovery.git
cd lit-discovery
pip install -e .[dev]
pytest tests/
```

## Pull Request Guidelines
- Follow PEP 8 standards.
- Ensure any new academic API clients have timeout protection and error fallback.
- Include unit tests in `tests/` for new features.
