SHELL := /usr/bin/env bash
.DEFAULT_GOAL := validate
MONOREPO ?= ../mindclade-internal-monorepo
GITOPS ?= ../gitops
CANDIDATE_MODULE_VERSION ?= v0.4.0
CANDIDATE_MODULE_REF ?=

.PHONY: validate validate-integration validate-source-integration validate-release-candidate validate-module-interfaces validate-module-candidate validate-module-worktree-candidate validate-capacity-contract validate-capacity-candidate validate-workload-identity-contract validate-workload-identity-candidate validate-gitops-integration validate-argocd-image-exceptions validate-infracost-workflow validate-dns validate-dns-source validate-dns-portfolio validate-dns-governance test-dns validate-security-txt validate-repository-home test format plan-development plan-staging plan-production
validate: validate-production-contract validate-repository-home validate-argocd-image-exceptions validate-infracost-workflow validate-dns-source validate-security-txt test
	python3 scripts/verify-provider-locks.py
	./scripts/validate-live-tree.py
	./scripts/validate-dependency-order.py
	terragrunt hcl fmt --check --diff

validate-integration: validate validate-module-interfaces validate-capacity-contract validate-workload-identity-contract

validate-source-integration: validate validate-module-candidate

validate-release-candidate: validate validate-module-candidate

validate-module-interfaces:
	python3 scripts/validate-module-interfaces.py --monorepo "$(MONOREPO)"

validate-module-candidate:
	@test -n "$(CANDIDATE_MODULE_REF)" || (echo "CANDIDATE_MODULE_REF must be an exact 40-character commit SHA" >&2; exit 2)
	python3 scripts/validate-module-release-candidate.py --monorepo "$(MONOREPO)" --candidate-version "$(CANDIDATE_MODULE_VERSION)" --candidate-ref "$(CANDIDATE_MODULE_REF)"

validate-module-worktree-candidate:
	python3 scripts/validate-module-interfaces.py --monorepo "$(MONOREPO)" --candidate-version "$(CANDIDATE_MODULE_VERSION)"

validate-capacity-contract:
	python3 scripts/validate-capacity-contract.py --monorepo "$(MONOREPO)"

validate-capacity-candidate:
	python3 scripts/validate-capacity-contract.py --monorepo "$(MONOREPO)" --candidate-version "$(CANDIDATE_MODULE_VERSION)"

validate-workload-identity-contract:
	python3 scripts/validate-workload-identity-contract.py --monorepo "$(MONOREPO)"

validate-workload-identity-candidate:
	python3 scripts/validate-workload-identity-contract.py --monorepo "$(MONOREPO)" --candidate-version "$(CANDIDATE_MODULE_VERSION)"

validate-argocd-image-exceptions:
	python3 scripts/validate-argocd-image-exceptions.py

validate-infracost-workflow:
	python3 scripts/validate_infracost_workflow.py

validate-gitops-integration:
	python3 scripts/validate-argocd-image-exceptions.py --gitops "$(GITOPS)"

test:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'

validate-dns:
	$(MAKE) validate-dns-source
	$(MAKE) test-dns

validate-dns-source:
	python3 scripts/generate_dns_domains.py --check
	python3 scripts/validate_dns_portfolio.py
	python3 scripts/validate_dns_governance.py

validate-dns-portfolio:
	python3 scripts/validate_dns_portfolio.py

validate-dns-governance:
	python3 scripts/validate_dns_governance.py

test-dns:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_dns_automation tests.test_dns_phase1

validate-security-txt:
	python3 scripts/validate_security_txt.py

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
