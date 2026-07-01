// Optional module. Deployed only when enableVector is true.
@description('Name of the Azure OpenAI account.')
param name string

@description('Location for the account.')
param location string = resourceGroup().location

@description('Resource tags.')
param tags object = {}

@description('Embedding model name.')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding model version.')
param embeddingModelVersion string = '1'

@description('Deployment name used by the tooling.')
param embeddingDeploymentName string = 'text-embedding-3-small'

@description('Provisioned capacity (thousands of tokens per minute).')
param embeddingCapacity int = 50

@description('Principal id granted OpenAI data access. Empty skips role assignments.')
param principalId string = ''

@description('Principal type for role assignments.')
param principalType string = 'User'

// Cognitive Services OpenAI User.
var openAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource embedding 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: embeddingDeploymentName
  sku: {
    name: 'Standard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
  }
}

resource openAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(account.id, principalId, openAiUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUser)
    principalId: principalId
    principalType: principalType
  }
}

output name string = account.name
output endpoint string = account.properties.endpoint
output embeddingDeployment string = embedding.name
