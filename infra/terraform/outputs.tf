output "subscription_name" {
  value = data.azurerm_subscription.current.display_name
}

output "subnet_id" {
  value = azurerm_subnet.public.id
}
