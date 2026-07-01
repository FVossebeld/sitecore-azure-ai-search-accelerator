@description('Name of the Azure AI Search service.')
param name string

@description('Location for the search service.')
param location string = resourceGroup().location

@description('Resource tags.')
param tags object = {}

@description('Search SKU. Basic or higher is required for the semantic ranker.')
param sku string = 'basic'

@description('Semantic ranker plan: free or standard.')
param semanticSearch string = 'free'

@description('Principal id granted data-plane access. Empty skips role assignments.')
param principalId string = ''

@description('Principal type for role assignments.')
param principalType string = 'User'

// Built-in role definition ids.
var searchIndexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var searchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    semanticSearch: semanticSearch
    // Allow both Azure AD (RBAC) and API keys. The tooling uses Azure AD by default.
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

resource indexDataRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, searchIndexDataContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributor)
    principalId: principalId
    principalType: principalType
  }
}

resource serviceContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, searchServiceContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributor)
    principalId: principalId
    principalType: principalType
  }
}

output name string = search.name
output endpoint string = 'https://${search.name}.search.windows.net'
