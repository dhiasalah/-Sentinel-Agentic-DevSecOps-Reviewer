provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

# Read-only question: "what is this subscription called?"
data "azurerm_subscription" "current" {}
