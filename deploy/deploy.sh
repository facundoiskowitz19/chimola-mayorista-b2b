#!/usr/bin/env bash
# Deploy a Cloud Run desde source (Cloud Build + Artifact Registry).
#
#   ./deploy/deploy.sh dev    → mayorista-b2b-dev  en chimola-deteccion
#   ./deploy/deploy.sh prod   → mayorista-b2b      en chimola-490015
#
# Requiere haber corrido antes ./deploy/setup_infra.sh <env>.
set -euo pipefail

ENV="${1:-dev}"
case "$ENV" in
  dev)
    PROJECT=chimola-deteccion; SERVICE=mayorista-b2b-dev; SA=sa-mayorista-dev@chimola-deteccion.iam.gserviceaccount.com
    BUCKET_PEDIDOS=chimola-mayorista-pedidos-dev
    # DEV: todos los mails van a una casilla de prueba
    EMAIL_VARS="EMAIL_OVERRIDE_TO=${EMAIL_OVERRIDE_TO:-},PEDIDOS_EMAIL_TO=${PEDIDOS_EMAIL_TO:-fiskowitz@lautin.com.ar}"
    MAX_INSTANCES=1   # >1 rompe descargas/subidas: la afinidad de sesión de Cloud Run es best-effort y Streamlit necesita que TODO llegue a la misma instancia ;;
  prod)
    PROJECT=chimola-490015; SERVICE=mayorista-b2b; SA=sa-mayorista@chimola-490015.iam.gserviceaccount.com
    BUCKET_PEDIDOS=chimola-mayorista-pedidos
    # PROD: definir PEDIDOS_EMAIL_TO con Chimola (ej: pedidos@lautin.com.ar)
    EMAIL_VARS="EMAIL_OVERRIDE_TO=,PEDIDOS_EMAIL_TO=${PEDIDOS_EMAIL_TO:?Definí PEDIDOS_EMAIL_TO para PROD}"
    MAX_INSTANCES=5 ;;
  *) echo "env debe ser dev|prod"; exit 1 ;;
esac
REGION=us-central1

cd "$(dirname "$0")/.."
echo "==> Deploy $SERVICE en $PROJECT ($REGION)"
gcloud run deploy "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --source=. \
  --service-account="$SA" \
  --allow-unauthenticated \
  --session-affinity \
  --memory=1Gi --cpu=1 --concurrency=40 --timeout=300 \
  --min-instances=0 --max-instances="$MAX_INSTANCES" \
  --set-env-vars="APP_ENV=${ENV},GCP_PROJECT=${PROJECT},BQ_PROJECT=${PROJECT},FIRESTORE_PROJECT=${PROJECT},BUCKET_PEDIDOS=${BUCKET_PEDIDOS},SMTP_SECRET_PROJECT=chimola-490015,${EMAIL_VARS}" \
  --set-secrets="JWT_KEY=mayorista-jwt-key:latest"

URL=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format="value(status.url)")
echo "==> Listo: $URL"
