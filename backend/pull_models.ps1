$models = @(
  "qwen2.5-coder",
  "mistral",
  "llama3",
  "phi3"
)

foreach ($model in $models) {
  Write-Host "Pulling $model..."
  ollama pull $model
}
