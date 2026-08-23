#!/usr/bin/env bash
# Setup de infra para mayorista-b2b. Idempotente (se puede re-correr).
#
# Uso:
#   ./deploy/setup_infra.sh dev     # chimola-deteccion
#   ./deploy/setup_infra.sh prod    # chimola-490015
#
# Crea: SA + grants (BQ readonly, fotos viewer, bucket pedidos, Firestore,
# Secret Manager, signBlob para signed URLs), bucket de pedidos, Firestore
# Native, secret JWT. El secret SMTP se REUSA del pipeline hermano
# (`email-smtp-credentials` en chimola-490015): solo se le da accessor a la SA.
set -euo pipefail

ENV="${1:-dev}"
case "$ENV" in
  dev)  PROJECT=chimola-deteccion; SA_NAME=sa-mayorista-dev; BUCKET_PEDIDOS=chimola-mayorista-pedidos-dev ;;
  prod) PROJECT=chimola-490015;    SA_NAME=sa-mayorista;     BUCKET_PEDIDOS=chimola-mayorista-pedidos ;;
  *) echo "env debe ser dev|prod"; exit 1 ;;
esac

REGION=us-central1
SMTP_SECRET_PROJECT=chimola-490015      # el secret SMTP vive en PROD siempre
SMTP_SECRET_NAME=email-smtp-credentials
BUCKET_FOTOS=ecommerce-b2b-imagenes     # bucket de fotos (vive en PROD)
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

log() { echo; echo "==> $*"; }

log "APIs ($PROJECT)"
gcloud services enable run.googleapis.com firestore.googleapis.com secretmanager.googleapis.com \
  bigquery.googleapis.com storage.googleapis.com iamcredentials.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com --project="$PROJECT" --quiet

log "Service account $SA"
gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA_NAME" --display-name="Mayorista B2B ($ENV)" --project="$PROJECT"

log "BigQuery: jobUser a nivel proyecto + dataViewer por dataset"
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
  --role=roles/bigquery.jobUser --condition=None --quiet >/dev/null
# to_dataframe() usa la BigQuery Storage API → necesita bigquery.readsessions.create
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
  --role=roles/bigquery.readSessionUser --condition=None --quiet >/dev/null
# `bq add-iam-policy-binding` requiere allowlisting → usamos la API (access entries = READER).
PY=./venv/bin/python; [ -x "$PY" ] || PY=python3
SA="$SA" PROJECT="$PROJECT" "$PY" - <<'EOF'
import os
from google.cloud import bigquery
from google.cloud.bigquery import AccessEntry
sa, project = os.environ["SA"], os.environ["PROJECT"]
client = bigquery.Client(project=project)
for ds_id in ["franquicias_marts", "franquicias_dwh", "franquicias_raw", "central_raw"]:
    ds = client.get_dataset(f"{project}.{ds_id}")
    entries = list(ds.access_entries)
    if any(e.entity_id == sa for e in entries):
        print(f"   {ds_id}: ya tenía READER"); continue
    entries.append(AccessEntry(role="READER", entity_type="userByEmail", entity_id=sa))
    ds.access_entries = entries
    client.update_dataset(ds, ["access_entries"])
    print(f"   {ds_id}: READER otorgado")
EOF

log "Fotos: objectViewer en gs://$BUCKET_FOTOS"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_FOTOS" --member="serviceAccount:$SA" \
  --role=roles/storage.objectViewer >/dev/null

log "Bucket de pedidos gs://$BUCKET_PEDIDOS"
gcloud storage buckets describe "gs://$BUCKET_PEDIDOS" >/dev/null 2>&1 \
  || gcloud storage buckets create "gs://$BUCKET_PEDIDOS" --project="$PROJECT" --location="$REGION" \
       --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_PEDIDOS" --member="serviceAccount:$SA" \
  --role=roles/storage.objectAdmin >/dev/null

log "Firestore Native (default) en $REGION"
gcloud firestore databases describe --database="(default)" --project="$PROJECT" >/dev/null 2>&1 \
  || gcloud firestore databases create --database="(default)" --location="$REGION" --type=firestore-native --project="$PROJECT"
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
  --role=roles/datastore.user --condition=None --quiet >/dev/null
# Índice compuesto para "mis pedidos" (where cliente_cod == X order by confirmed_at desc)
if ! gcloud firestore indexes composite list --project="$PROJECT" --format="value(name)" 2>/dev/null \
     | xargs -I{} gcloud firestore indexes composite describe {} --project="$PROJECT" --format=json 2>/dev/null \
     | grep -q '"fieldPath": "confirmed_at"'; then
  gcloud firestore indexes composite create --collection-group=pedidos --query-scope=COLLECTION \
    --field-config=field-path=cliente_cod,order=ascending \
    --field-config=field-path=confirmed_at,order=descending --project="$PROJECT" --async || true
fi

log "Signed URLs: la SA se firma a sí misma (signBlob)"
gcloud iam service-accounts add-iam-policy-binding "$SA" --member="serviceAccount:$SA" \
  --role=roles/iam.serviceAccountTokenCreator --project="$PROJECT" --quiet >/dev/null

log "Secret JWT (mayorista-jwt-key)"
if ! gcloud secrets describe mayorista-jwt-key --project="$PROJECT" >/dev/null 2>&1; then
  python3 -c "import secrets; print(secrets.token_urlsafe(48), end='')" \
    | gcloud secrets create mayorista-jwt-key --data-file=- --project="$PROJECT" --replication-policy=automatic
fi
gcloud secrets add-iam-policy-binding mayorista-jwt-key --member="serviceAccount:$SA" \
  --role=roles/secretmanager.secretAccessor --project="$PROJECT" >/dev/null

log "Secret SMTP: accessor a $SMTP_SECRET_PROJECT/$SMTP_SECRET_NAME"
gcloud secrets add-iam-policy-binding "$SMTP_SECRET_NAME" --member="serviceAccount:$SA" \
  --role=roles/secretmanager.secretAccessor --project="$SMTP_SECRET_PROJECT" >/dev/null

log "Listo. SA=$SA  bucket_pedidos=gs://$BUCKET_PEDIDOS"
