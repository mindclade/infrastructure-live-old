# State boundaries

Each `terragrunt.hcl` is an independent state unit. Organization/shared/production units use
the `infrastructure-live-production` bucket; development and staging use their own buckets.
State objects are never committed. Plans are short-lived CI artifacts and are treated as
sensitive. Cross-environment dependencies are prohibited.
