output "subscription_name" {
  value = data.azurerm_subscription.current.display_name
}

output "subnet_id" {
  value = azurerm_subnet.public.id
}

output "server_public_ip" {
  value = azurerm_public_ip.sentinel.ip_address
}
