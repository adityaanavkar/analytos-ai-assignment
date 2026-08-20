targetScope = 'resourceGroup'

@description('Short lowercase name used to generate deterministic resource names.')
@minLength(3)
@maxLength(20)
param environmentName string

@description('Azure region validated for the selected Azure OpenAI models.')
param location string = 'eastus2'

@description('Azure AI Search region with current Basic-tier capacity for the MVP.')
param searchLocation string = 'centralindia'

@description('Object ID of the developer or managed identity receiving least-privilege data-plane roles. Leave empty to skip role assignments.')
param operatorPrincipalId string = ''

@description('Microsoft Entra principal type for operatorPrincipalId.')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param operatorPrincipalType string = 'User'

@description('Required acknowledgement that this template creates paid resources.')
@allowed([
  'I_UNDERSTAND_THIS_CREATES_PAID_RESOURCES'
])
param paidResourcesAcknowledgement string

@description('Resource tags applied consistently to every supported resource.')
param tags object = {
  application: 'analytos-ai-assignment'
  environment: 'demo'
  managedBy: 'bicep'
}

var normalizedEnvironmentName = toLower(replace(environmentName, '-', ''))
var uniqueSuffix = take(uniqueString(subscription().id, resourceGroup().id, normalizedEnvironmentName), 7)
var nameStem = take('${normalizedEnvironmentName}${uniqueSuffix}', 20)

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: take('st${nameStem}', 24)
    location: location
    containerName: 'knowledge-base'
    operatorPrincipalId: operatorPrincipalId
    operatorPrincipalType: operatorPrincipalType
    tags: tags
  }
}

module search 'modules/search.bicep' = {
  name: 'search'
  params: {
    name: take('srch-${nameStem}', 60)
    location: searchLocation
    operatorPrincipalId: operatorPrincipalId
    operatorPrincipalType: operatorPrincipalType
    tags: tags
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    workspaceName: take('log-${nameStem}', 63)
    applicationInsightsName: take('appi-${nameStem}', 255)
    location: location
    tags: tags
  }
}

module openAi 'modules/openai.bicep' = {
  name: 'openai'
  params: {
    name: take('aoai-${nameStem}', 64)
    location: location
    operatorPrincipalId: operatorPrincipalId
    operatorPrincipalType: operatorPrincipalType
    chatDeploymentName: 'gpt-4-1-mini'
    embeddingDeploymentName: 'text-embedding-3-small'
    tags: tags
  }
}

@description('Sanitized service locations. No secret values are returned.')
output services object = {
  paidResourcesApproved: paidResourcesAcknowledgement == 'I_UNDERSTAND_THIS_CREATES_PAID_RESOURCES'
  storage: {
    accountName: storage.outputs.accountName
    blobEndpoint: storage.outputs.blobEndpoint
    containerName: storage.outputs.containerName
  }
  search: {
    serviceName: search.outputs.serviceName
    endpoint: search.outputs.endpoint
  }
  openAi: {
    accountName: openAi.outputs.accountName
    endpoint: openAi.outputs.endpoint
    chatDeploymentName: openAi.outputs.chatDeploymentName
    embeddingDeploymentName: openAi.outputs.embeddingDeploymentName
  }
  monitoring: {
    workspaceName: monitoring.outputs.workspaceName
    applicationInsightsName: monitoring.outputs.applicationInsightsName
  }
}
