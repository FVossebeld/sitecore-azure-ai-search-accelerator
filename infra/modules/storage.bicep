@description('Name of the storage account (3-24 lowercase alphanumeric).')
param name string

@description('Location for the storage account.')
param location string = resourceGroup().location

@description('Resource tags.')
param tags object = {}

@description('Blob container that holds exported content.')
param containerName string = 'content'

@description('Principal id granted blob data access. Empty skips role assignments.')
param principalId string = ''

@description('Principal type for role assignments.')
param principalType string = 'User'

// Storage Blob Data Contributor.
var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

resource blobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(storage.id, principalId, blobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: principalId
    principalType: principalType
  }
}

output name string = storage.name
output blobEndpoint string = storage.properties.primaryEndpoints.blob
output containerName string = containerName
