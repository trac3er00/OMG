# /OMG:instant

One-command product generation. Generates scaffold + code structure from a natural language prompt.

## Usage

npx omg instant "<prompt>"

## Examples

- npx omg instant "랜딩페이지 만들어줘"
- npx omg instant "make a REST API"
- npx omg instant "쇼핑몰 만들어줘"

## Behavior

1. Classifies intent (7 product types: saas, landing, ecommerce, api, bot, admin, cli)
2. Loads domain pack template
3. Generates scaffold in current directory
4. Reports ProofScore of generated output

## Options

- --dir <path>: Output directory (default: current)
- --yes: Skip confirmation for non-empty directories

## Governance

Runs with Silent Safety mode - dangerous operations blocked, safe ops auto-approved.
