# Infrastructure

Local development infrastructure is defined entirely in `docker-compose.yml` at the
repository root. This directory is reserved for deployment-environment infrastructure
(reverse proxy configuration, IaC) added as the platform moves toward the cloud
deployment target described in the architecture docs -- not needed to run the
project locally.

- `nginx/` -- reverse proxy configuration placeholder for a future non-containerized
  or edge deployment.
