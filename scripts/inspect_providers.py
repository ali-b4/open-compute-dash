"""Review provider selection offline without sending requests or loading secrets."""

import argparse
import json
from pathlib import Path

if __package__:
    from .provider_registry import build_provider_plan, load_registry
else:
    from provider_registry import build_provider_plan, load_registry


def format_text(plan):
    lines = ['Provider registry — offline review']
    if plan['synthetic']:
        lines.append('SYNTHETIC TEST REGISTRY — invented test configuration, not a real provider run')
    lines.append(f"Selected: {plan['provider_count']} provider(s)")
    for provider in plan['providers']:
        access = provider['evidence']['access']
        access_label = ('unverified' if access['value'] is None else
                        f"{'available' if access['value'] else 'unavailable'} ({access['status'].replace('_', ' ')})")
        capabilities = [item for key, item in provider['evidence'].items() if key != 'access']
        capability_label = 'unverified' if all(item['value'] is None for item in capabilities) else 'see --json'
        price_label = 'historical, unverified' if provider['pricing']['status'] == 'historical_unverified' else 'unverified'
        lines.extend([
            f"\n- {provider['provider_id']} — {provider['display_name']} [{provider['status']}]",
            f"  Model: {provider['model_id']}",
            f'  Access: {access_label}; capabilities: {capability_label}; prices: {price_label}',
        ])
    if plan['excluded_providers']:
        lines.append('\nExcluded from this selection:')
        lines.extend(
            f"- {provider['provider_id']} — {provider['display_name']} [{provider['status']}]"
            for provider in plan['excluded_providers']
        )
    lines.extend([
        '\nSecret variable names for a future approved run: ' + (', '.join(plan['required_secret_variables']) or 'None'),
        'Configuration does not verify account access, supported capabilities, or current prices.',
        'No requests were sent and no secret values were loaded or checked.',
        'Use --json for the full offline selection plan.',
    ])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, help='Registry JSON file; defaults to the project registry')
    parser.add_argument('--providers', nargs='+', metavar='ID', help='Select provider IDs; defaults to all enabled providers')
    parser.add_argument('--json', action='store_true', help='Print the full safe offline selection plan as JSON')
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.registry)
        plan = build_provider_plan(registry, selected=args.providers)
        output = json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) if args.json else format_text(plan)
    except (OSError, UnicodeError):
        parser.error('Cannot read the registry. Provide a readable UTF-8 JSON file with --registry PATH.')
    except (json.JSONDecodeError, RecursionError):
        parser.error('Invalid registry JSON. Check the file syntax or use the default project registry.')
    except ValueError as error:
        parser.error(f'{error} Check the registry or --providers selection.')
    print(output)


if __name__ == '__main__':
    main()
