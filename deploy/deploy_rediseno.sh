#!/usr/bin/env bash
# Deploy del sitio nuevo (API FastAPI + web Next.js) a Cloud Run.
#
#   ./deploy/deploy_rediseno.sh dev            → api + web en chimola-deteccion
#   ./deploy/deploy_rediseno.sh dev api        → solo la API
#   ./deploy/deploy_rediseno.sh dev web        → solo la web (usa la URL de la API ya deployada)
#   ./deploy/deploy_rediseno.sh prod           → chimola-490015 (recién cuando DEV esté validado)
#
# Requiere ./deploy/setup_infra.sh <env> hecho (SA, grants, bucket, secrets): la API
# usa la MISMA SA que el Streamlit. Las imágenes van a Artifact Registry
# `cloud-run-source-deploy` (lo crea `gcloud run deploy --source`; acá se crea si falta).
set -euo pipefail

ENV="${1:-dev}"
QUE="${2:-all}"
case "$ENV" in
  dev)
    PROJECT=chimola-deteccion; SA=sa-mayorista-dev@chimola-deteccion.iam.gserviceaccount.com
    BUCKET_PEDIDOS=chimola-mayorista-pedidos-dev
    PEDIDOS_EMAIL_TO="${PEDIDOS_EMAIL_TO:-fiskowitz@lautin.com.ar}"
    ADMIN_URL="${ADMIN_URL:-https://mayorista-b2b-dev-vhnuyigzqa-uc.a.run.app}" ;;
  prod)
    PROJECT=chimola-490015; SA=sa-mayorista@chimola-490015.iam.gserviceaccount.com
    BUCKET_PEDIDOS=chimola-mayorista-pedidos
    PEDIDOS_EMAIL_TO="${PEDIDOS_EMAIL_TO:?Definí PEDIDOS_EMAIL_TO para PROD}"
    ADMIN_URL="${ADMIN_URL:?Definí ADMIN_URL (URL del Streamlit admin PROD)}" ;;
  *) echo "env debe ser dev|prod"; exit 1 ;;
esac
REGION=us-central1
API_SERVICE="mayorista-api-$ENV"
WEB_SERVICE="mayorista-web-$ENV"
REPO="$REGION-docker.pkg.dev/$PROJECT/cloud-run-source-deploy"
TAG="$(date +%Y%m%d-%H%M%S)"
# Versión del lanzamiento = último tag git (vX.Y.Z[-rc.N]); con commits encima queda "v1.0.0-rc.1-3-gabc123".
APP_VERSION="$(git describe --tags --always --dirty 2>/dev/null || echo desconocida)"
if [[ "$ENV" == "prod" && ! "$APP_VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "PROD solo se deploya desde un tag de versión exacto (vX.Y.Z); HEAD es '$APP_VERSION'. Taggeá primero." >&2
  exit 1
fi

cd "$(dirname "$0")/.."
log() { printf '\n==> %s\n' "$*"; }
log "Versión: $APP_VERSION  (env: $ENV)"

gcloud artifacts repositories describe cloud-run-source-deploy --project="$PROJECT" --location="$REGION" >/dev/null 2>&1 \
  || gcloud artifacts repositories create cloud-run-source-deploy --project="$PROJECT" --location="$REGION" \
       --repository-format=docker --description="Cloud Run source deploys"

if [[ "$QUE" == "all" || "$QUE" == "api" ]]; then
  IMG="$REPO/mayorista-api:$TAG"
  log "Build API → $IMG (contexto = root del repo)"
  gcloud builds submit --project="$PROJECT" --config=api/cloudbuild.yaml --substitutions="_IMAGE=$IMG" .
  log "Deploy $API_SERVICE"
  gcloud run deploy "$API_SERVICE" \
    --project="$PROJECT" --region="$REGION" --image="$IMG" \
    --service-account="$SA" --allow-unauthenticated \
    --memory=1Gi --cpu=1 --concurrency=40 --timeout=120 \
    --min-instances=0 --max-instances=3 \
    --set-env-vars="APP_ENV=${ENV},APP_VERSION=${APP_VERSION},GCP_PROJECT=${PROJECT},BQ_PROJECT=${PROJECT},FIRESTORE_PROJECT=${PROJECT},BUCKET_PEDIDOS=${BUCKET_PEDIDOS},SMTP_SECRET_PROJECT=chimola-490015,PEDIDOS_EMAIL_TO=${PEDIDOS_EMAIL_TO},EMAIL_OVERRIDE_TO=,CORS_ORIGINS=" \
    --set-secrets="JWT_KEY=mayorista-jwt-key:latest"
fi

API_URL=$(gcloud run services describe "$API_SERVICE" --project="$PROJECT" --region="$REGION" --format="value(status.url)")
log "API: $API_URL"

if [[ "$QUE" == "all" || "$QUE" == "web" ]]; then
  IMG="$REPO/mayorista-web:$TAG"
  log "Build web → $IMG"
  gcloud builds submit --project="$PROJECT" --config=web/cloudbuild.yaml \
    --substitutions="_IMAGE=$IMG,_APP_ENV=$ENV,_ADMIN_URL=$ADMIN_URL,_APP_VERSION=$APP_VERSION" web
  log "Deploy $WEB_SERVICE"
  gcloud run deploy "$WEB_SERVICE" \
    --project="$PROJECT" --region="$REGION" --image="$IMG" \
    --service-account="$SA" --allow-unauthenticated \
    --memory=512Mi --cpu=1 --concurrency=80 --timeout=60 \
    --min-instances=0 --max-instances=3 \
    --set-env-vars="API_URL=${API_URL},NEXT_PUBLIC_APP_ENV=${ENV},NEXT_PUBLIC_APP_VERSION=${APP_VERSION}"
fi

WEB_URL=$(gcloud run services describe "$WEB_SERVICE" --project="$PROJECT" --region="$REGION" --format="value(status.url)" 2>/dev/null || true)
log "Listo.  web: ${WEB_URL:-"(no deployada)"}   api: $API_URL"
