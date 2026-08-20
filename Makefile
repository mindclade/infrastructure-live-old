SHELL := /usr/bin/env bash
.DEFAULT_GOAL := validate
MONOREPO ?= ../mindclade-internal-monorepo
GITOPS ?= ../gitops

.PHONY: validate validate-integration validate-module-interfaces validate-gitops-integration validate-argocd-image-exceptions validate-dns-portfolio validate-repository-home test format plan-development plan-staging plan-production
validate: validate-production-contract validate-repository-home validate-argocd-image-exceptions validate-dns-portfolio test
	python3 scripts/verify-provider-locks.py
	./scripts/validate-live-tree.py
	./scripts/validate-dependency-order.py
	terragrunt hcl fmt --check --diff

validate-integration: validate validate-module-interfaces

validate-module-interfaces:
	python3 scripts/validate-module-interfaces.py --monorepo "$(MONOREPO)"

validate-argocd-image-exceptions:
	python3 scripts/validate-argocd-image-exceptions.py

validate-gitops-integration:
	python3 scripts/validate-argocd-image-exceptions.py --gitops "$(GITOPS)"

test:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'

validate-dns-portfolio:
	python3 scripts/validate_dns_portfolio.py

validate-repository-home:
	python3 scripts/validate-repository-home.py --root .

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
