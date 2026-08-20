#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
"""Validate the stable account.hcl contract and its runtime values."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'account.hcl'
REQUIRED={
 'GCP_ORG_ID':r'^[0-9]+$',
 'BILLING_ACCOUNT':r'^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$',
 'BOOTSTRAP_SEED_PROJECT_ID':r'^[a-z][a-z0-9-]{4,28}[a-z0-9]$',
 'BOOTSTRAP_CICD_PROJECT_ID':r'^[a-z][a-z0-9-]{4,28}[a-z0-9]$',
 'BOOTSTRAP_CICD_PROJECT_NUMBER':r'^[0-9]+$',
 'GITHUB_WIF_POOL_NAME':r'^projects/[0-9]+/locations/global/workloadIdentityPools/[a-z0-9-]+$',
 'BUILDKITE_WIF_POOL_NAME':r'^projects/[0-9]+/locations/global/workloadIdentityPools/buildkite$',
 'TFSTATE_BUCKET_DEVELOPMENT':r'^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$',
 'TFSTATE_BUCKET_STAGING':r'^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$',
 'TFSTATE_BUCKET_PRODUCTION':r'^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$',
 'SA_TF_LIVE_PLAN':r'^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$',
 'SA_TF_LIVE_APPLY_FOUNDATION':r'^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$',
 'SA_TF_LIVE_APPLY_DEVELOPMENT':r'^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$',
 'SA_TF_LIVE_APPLY_STAGING':r'^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$',
 'SA_TF_LIVE_APPLY_PRODUCTION':r'^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$',
}
OPTIONAL={
 'RESOURCE_PREFIX':'mc','PRIMARY_REGION':'us-central1','STATE_LOCATION':'US',
 'DOMAIN':'mindclade.com','MONOREPO_ORG':'Mindclade',
}

def source_errors()->list[str]:
 text=SOURCE.read_text(encoding='utf-8')
 errors=[]
 if 'REPLACE' in text or '000000000000' in text or 'XXXXXX-XXXXXX-XXXXXX' in text:
  errors.append('account.hcl contains committed placeholder identifiers')
 for name in (*REQUIRED,*OPTIONAL):
  if f'get_env("{name}"' not in text: errors.append(f'account.hcl does not consume {name}')
 if re.search(r'(?m)^\s*(?:org_id|billing_account|seed_project_id|cicd_project_id)\s*=\s*"',text):
  errors.append('account.hcl hard-codes an organization or project identifier')
 return errors

def runtime_values()->tuple[dict[str,str],list[str]]:
 values={name:os.environ.get(name,'') for name in REQUIRED}
 values.update({name:os.environ.get(name,default) for name,default in OPTIONAL.items()})
 errors=[]
 for name,pat in REQUIRED.items():
  if not re.fullmatch(pat,values[name]): errors.append(f'invalid or missing runtime account field: {name}')
 if not re.fullmatch(r'^[a-z][a-z0-9]{1,3}$',values['RESOURCE_PREFIX']): errors.append('invalid RESOURCE_PREFIX')
 if not re.fullmatch(r'^[a-z]+-[a-z0-9]+[0-9]$',values['PRIMARY_REGION']): errors.append('invalid PRIMARY_REGION')
 if not re.fullmatch(r'^[A-Za-z0-9.-]+$',values['DOMAIN']): errors.append('invalid DOMAIN')
 if not re.fullmatch(r'^[A-Za-z0-9_.-]+$',values['MONOREPO_ORG']): errors.append('invalid MONOREPO_ORG')
 return dict(sorted(values.items())),errors

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--runtime',action='store_true'); ap.add_argument('--json',action='store_true'); args=ap.parse_args()
 errors=source_errors(); values={}
 if args.runtime:
  values,runtime=runtime_values(); errors.extend(runtime)
 if errors:
  for e in sorted(set(errors)): print(f'ERROR: {e}',file=sys.stderr)
  return 1
 if args.json:
  if not args.runtime: print('ERROR: --json requires --runtime',file=sys.stderr); return 2
  print(json.dumps(values,sort_keys=True,separators=(',',':')))
 else:
  print('account contract source and runtime values passed' if args.runtime else 'account contract source passed')
 return 0
if __name__=='__main__': raise SystemExit(main())
