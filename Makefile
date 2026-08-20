SHELL := /usr/bin/env bash
.DEFAULT_GOAL := validate

.PHONY: validate test format plan-development plan-staging plan-production
validate: validate-production-contract test
	python3 scripts/verify-provider-locks.py
	./scripts/validate-live-tree.py
	./scripts/validate-dependency-order.py
	terragrunt hcl fmt --check --diff

test:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'

format:
	terragrunt hcl fmt

plan-development:
	./scripts/validate-account.py --runtime
	TG_STRICT_MODE=true terragrunt run --all --working-dir 2-environments/development plan

plan-staging:
	./scripts/validate-account.py --runtime
	TG_STRICT_MODE=true terragrunt run --all --working-dir 2-environments/staging plan

plan-production:
	./scripts/validate-account.py --runtime
	TG_STRICT_MODE=true terragrunt run --all --working-dir 1-org plan
	TG_STRICT_MODE=true terragrunt run --all --working-dir 2-environments/production plan

.PHONY: validate-production-contract
validate-production-contract:
	python3 scripts/validate-production-contract.py
