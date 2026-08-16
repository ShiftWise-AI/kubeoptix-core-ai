{{- define "kubeoptix-core-ai-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kubeoptix-core-ai-api.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "kubeoptix-core-ai-api.labels" -}}
helm.sh/chart: {{ include "kubeoptix-core-ai-api.name" . }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "kubeoptix-core-ai-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: api
app.kubernetes.io/part-of: kubeoptix-core-ai
{{- end }}

{{- define "kubeoptix-core-ai-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubeoptix-core-ai-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
