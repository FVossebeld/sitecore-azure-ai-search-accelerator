targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used to generate a short unique hash for resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@description('Object id of the user or service principal that runs the tooling. Used for RBAC data-plane access. azd populates this from AZURE_PRINCIPAL_ID.')
param principalId string = ''

@allowed([
  'User'
  'ServicePrincipal'
])
@description('Principal type for the role assignments.')
param principalType string = 'User'

@description('Azure AI Search SKU. Basic or higher is required for the semantic ranker.')
@allowed([
  'basic'
  'standard'
  'standard2'
])
param searchSku string = 'basic'

@description('Semantic ranker plan. free gives a monthly quota at no cost, standard is billed per query.')
@allowed([
  'free'
  'standard'
])
param semanticSearch string = 'free'

@description('Enable the optional vector/hybrid module. When true, an Azure OpenAI account with an embedding deployment is provisioned.')
param enableVector bool = false

@description('Embedding model deployed when enableVector is true.')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding model version.')
param embeddingModelVersion string = '1'

var abbrs = {
  search: 'srch-'
  storage: 'st'
  openai: 'oai-'
  resourceGroup: 'rg-'
}
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
}

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: '${abbrs.resourceGroup}${environmentName}'
  location: location
  tags: tags
}

module search 'modules/search.bicep' = {
  name: 'search'
  scope: rg
  params: {
    name: '${abbrs.search}${resourceToken}'
    location: location
    tags: tags
    sku: searchSku
    semanticSearch: semanticSearch
    principalId: principalId
    principalType: principalType
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: '${abbrs.storage}${resourceToken}'
    location: location
    tags: tags
    principalId: principalId
    principalType: principalType
  }
}

module openai 'modules/openai.bicep' = if (enableVector) {
  name: 'openai'
  scope: rg
  params: {
    name: '${abbrs.openai}${resourceToken}'
    location: location
    tags: tags
    embeddingModelName: embeddingModelName
    embeddingModelVersion: embeddingModelVersion
    principalId: principalId
    principalType: principalType
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name

output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_SEARCH_SERVICE_NAME string = search.outputs.name

output AZURE_STORAGE_ACCOUNT string = storage.outputs.name
output AZURE_STORAGE_BLOB_ENDPOINT string = storage.outputs.blobEndpoint
output AZURE_STORAGE_CONTAINER string = storage.outputs.containerName

output ENABLE_VECTOR bool = enableVector
output AZURE_OPENAI_ENDPOINT string = enableVector ? openai!.outputs.endpoint : ''
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = enableVector ? openai!.outputs.embeddingDeployment : ''
