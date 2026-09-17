{{- define "hip.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hip.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "hip.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hip.labels" -}}
app.kubernetes.io/name: {{ include "hip.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "hip.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}

{{- define "hip.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "hip.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Shared env for the app + mllp containers. DATABASE_URL and the app secrets come
from the referenced Secret(s); non-secret config is inline.
*/}}
{{- define "hip.env" -}}
- name: HIP_LOG_JSON
  value: {{ .Values.config.logJson | quote }}
- name: HIP_RATE_LIMIT
  value: {{ .Values.config.rateLimit | quote }}
- name: HIP_RATE_WINDOW_SECONDS
  value: {{ .Values.config.rateWindowSeconds | quote }}
- name: HIP_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.database.existingSecret | default (printf "%s-db" (include "hip.fullname" .)) }}
      key: database-url
- name: HIP_ENCRYPTION_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.existingSecret | default (printf "%s-secrets" (include "hip.fullname" .)) }}
      key: encryption-key
- name: HIP_BLIND_INDEX_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.existingSecret | default (printf "%s-secrets" (include "hip.fullname" .)) }}
      key: blind-index-key
- name: HIP_JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.existingSecret | default (printf "%s-secrets" (include "hip.fullname" .)) }}
      key: jwt-secret
{{- end -}}
