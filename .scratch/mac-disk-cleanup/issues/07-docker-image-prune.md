# Docker image prune (Tier C)

Type: task
Status: resolved
Blocked by: 05

## Question

Prune old Docker images; keep warehouse-prod / mdm-prod.

## Answer

After Colima delete+recreate at 20 GiB, Docker has **zero images**. No prune needed.

To restore only what you need later (example):

```bash
# ECR login first if required
docker pull 690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images:warehouse-prod
docker pull 690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images:mdm-prod
```

Do not re-pull the full historical operator/sha tag set — that is what filled the old 80 GiB disk.
