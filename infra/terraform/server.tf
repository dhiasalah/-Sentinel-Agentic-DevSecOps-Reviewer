# The server's address on the internet. Static = same address after every restart.
resource "azurerm_public_ip" "sentinel" {
  name                = "sentinel-ip"
  location            = azurerm_resource_group.sentinel.location
  resource_group_name = azurerm_resource_group.sentinel.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# Plugs the server into your street and gives it the address above
resource "azurerm_network_interface" "sentinel" {
  name                = "sentinel-nic"
  location            = azurerm_resource_group.sentinel.location
  resource_group_name = azurerm_resource_group.sentinel.name

  ip_configuration {
    name                          = "main"
    subnet_id                     = azurerm_subnet.public.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.sentinel.id
  }
}

# The computer itself: 2 CPUs, 4 GB, Ubuntu 24.04, key-only login
resource "azurerm_linux_virtual_machine" "sentinel" {
  name                  = "sentinel-vm"
  computer_name         = "sentinel"
  location              = azurerm_resource_group.sentinel.location
  resource_group_name   = azurerm_resource_group.sentinel.name
  size                  = "Standard_B2als_v2"
  network_interface_ids = [azurerm_network_interface.sentinel.id]

  admin_username                  = "azureuser"
  disable_password_authentication = true

  admin_ssh_key {
    username   = "azureuser"
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# Switch the server off every night so the $100 student credit lasts
resource "azurerm_dev_test_global_vm_shutdown_schedule" "sentinel" {
  virtual_machine_id    = azurerm_linux_virtual_machine.sentinel.id
  location              = azurerm_resource_group.sentinel.location
  enabled               = true
  daily_recurrence_time = "2300"
  timezone              = "Romance Standard Time"

  notification_settings {
    enabled = false
  }
}
