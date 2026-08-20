# Azure infrastructure

This folder defines the small Azure demo environment as Bicep.
The template creates Azure OpenAI, Azure AI Search Basic, Blob Storage, Log Analytics, and Application Insights in an existing resource group.
Running `build` or `what-if` does not create resources.

## Safety and cost choices

- Azure OpenAI, Storage, and monitoring default to `eastus2`.
- Azure AI Search defaults to `centralindia` because East US 2 rejected new Basic capacity during the 2026-08-21 MVP deployment.
- Azure AI Search uses the paid Basic tier with one replica and one partition.
- Azure OpenAI uses the S0 account tier and GlobalStandard model deployments.
- Model versions are pinned with automatic upgrades disabled so baseline and improved evaluations remain reproducible.
- Log Analytics retains data for 30 days and has a 1 GB daily ingestion cap.
- Storage allows no anonymous blob access, requires TLS 1.2, and disables shared-key authentication.
- Azure AI Search and Azure OpenAI disable API-key authentication.
- Public endpoints remain enabled because the demo application runs on the developer machine.
- No keys, tokens, or connection strings are emitted as deployment outputs.

Azure services charge while they exist.
Review current Azure pricing before deployment and delete the demo resource group when finished.
The template contains a required `paidResourcesAcknowledgement` gate so an omitted parameter cannot accidentally create the paid stack.
Azure budgets send alerts but do not stop spending, so the resource-group deletion procedure remains the hard stop.

## 1. Validate locally

From the repository root, run:

```powershell
az bicep build --file .\infra\main.bicep
```

This verifies the Bicep syntax and produces `infra/main.json`.
The generated JSON is ignored by Git.

## 2. Choose names

Use a short lowercase environment name containing only letters and numbers.

```powershell
$resourceGroup = "rg-analytos-ai-demo"
$environmentName = "analytosdemo"
$location = "eastus2"
$searchLocation = "centralindia"
$operatorObjectId = az ad signed-in-user show --query id --output tsv
```

The template derives deterministic globally unique service names from the environment name, subscription, and resource group.
`operatorObjectId` receives only the data-plane roles required to index documents and call the deployed models.
The default principal type is `User`.
For a managed identity, pass its object ID and `operatorPrincipalType=ServicePrincipal`.

## 3. Run subscription and region preflight

Confirm the intended subscription before creating anything.

```powershell
az account show --query "{name:name,id:id,state:state,isDefault:isDefault}" --output table
az provider show --namespace Microsoft.CognitiveServices --query registrationState --output tsv
az provider show --namespace Microsoft.Search --query registrationState --output tsv
az provider show --namespace Microsoft.Storage --query registrationState --output tsv
az provider show --namespace Microsoft.Insights --query registrationState --output tsv
az provider show --namespace Microsoft.OperationalInsights --query registrationState --output tsv
az cognitiveservices model list --location $location --query "[?name=='gpt-4.1-mini' || name=='text-embedding-3-small'].[name,version,kind]" --output table
```

Every provider must report `Registered` and both pinned model versions must be available before deployment.
If a provider reports `NotRegistered`, register only that required provider and wait for `Registered` before retrying.
If either model or quota is unavailable in East US 2, stop and select the next validated region rather than changing the model or SKU silently.
The deployment must not proceed until the Azure Portal cost estimate for Search Basic, Log Analytics, Storage, and expected model tokens has been reviewed and explicitly approved.

## 4. Create only the resource group

```powershell
az group create --name $resourceGroup --location $location
```

This creates an empty container for the demo resources.
Confirm that the group contains no unrelated resources.

```powershell
az resource list --resource-group $resourceGroup --output table
```

## 5. Preview without deploying

```powershell
az deployment group what-if `
  --resource-group $resourceGroup `
  --template-file .\infra\main.bicep `
  --parameters environmentName=$environmentName location=$location searchLocation=$searchLocation `
  operatorPrincipalId=$operatorObjectId `
  paidResourcesAcknowledgement=I_UNDERSTAND_THIS_CREATES_PAID_RESOURCES
```

Read the entire preview before proceeding.
Confirm that it contains one resource of each expected service and no unrelated resources.

## 6. Deploy only after approval

This command creates paid resources and is intentionally not run automatically.

```powershell
az deployment group create `
  --name "analytos-ai-demo" `
  --resource-group $resourceGroup `
  --template-file .\infra\main.bicep `
  --confirm-with-what-if `
  --parameters environmentName=$environmentName location=$location searchLocation=$searchLocation `
  operatorPrincipalId=$operatorObjectId `
  paidResourcesAcknowledgement=I_UNDERSTAND_THIS_CREATES_PAID_RESOURCES
```

The deployment prints only resource names and endpoints.
It never prints account keys or connection strings.

If role-assignment creation is denied, the signed-in account needs Owner or User Access Administrator on the resource group.
Do not bypass this by enabling API keys.
Role assignments can take several minutes to propagate, so retry a failed data-plane smoke test before changing permissions.
If deployment fails partway through, inspect the deployment operations and remove the dedicated resource group before retrying from a clean state.
ARM resource-group deployments are incremental and do not automatically roll back resources created before a failure.

## 7. Inspect sanitized outputs

```powershell
az deployment group show `
  --name "analytos-ai-demo" `
  --resource-group $resourceGroup `
  --query properties.outputs
```

Copy endpoint values into a local `.env` file only.
Never commit `.env` or credentials.

## 8. Delete the demo when finished

First verify the exact group and every resource it contains.

```powershell
az group show --name $resourceGroup --query "{name:name,id:id}" --output table
az resource list --resource-group $resourceGroup --query "[].{name:name,type:type}" --output table
```

Delete only if the list contains assignment resources and nothing else.
The command keeps Azure's confirmation prompt intentionally.

```powershell
az group delete --name $resourceGroup
```

This permanently removes the entire demo resource group and stops its charges.
