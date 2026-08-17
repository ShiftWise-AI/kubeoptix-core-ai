{{- define "kubeoptix-core-ai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kubeoptix-core-ai.fullname" -}}
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

{{- define "kubeoptix-core-ai.namespace" -}}
{{- default .Release.Namespace .Values.namespace.name }}
{{- end }}

{{- define "kubeoptix-core-ai.labels" -}}
helm.sh/chart: {{ include "kubeoptix-core-ai.name" . }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "kubeoptix-core-ai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: api
app.kubernetes.io/part-of: kubeoptix-core-ai
{{- end }}

{{- define "kubeoptix-core-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubeoptix-core-ai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "kubeoptix-core-ai.imageStreamName" -}}
{{- .Values.image.repository | splitList "/" | last }}
{{- end }}

{{- define "kubeoptix-core-ai.image" -}}
{{- if .Values.image.useBuildOutput }}
{{- printf "image-registry.openshift-image-registry.svc:5000/%s/%s:%s" (include "kubeoptix-core-ai.namespace" .) (include "kubeoptix-core-ai.imageStreamName" .) .Values.image.tag }}
{{- else }}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag }}
{{- end }}
{{- end }}

{{- define "kubeoptix-core-ai.replicas" -}}
{{- if .Values.scalePolicy.enabled }}
{{- .Values.scalePolicy.maxReplicas }}
{{- else }}
{{- default 1 .Values.replicas }}
{{- end }}
{{- end }}

{{- define "kubeoptix-core-ai.headlessServiceName" -}}
{{- default (include "kubeoptix-core-ai.fullname" .) .Values.service.headless.name }}
{{- end }}

{{- define "kubeoptix-core-ai.apiServiceName" -}}
{{- default (printf "%s-api" (include "kubeoptix-core-ai.fullname" .)) .Values.service.api.name }}
{{- end }}
