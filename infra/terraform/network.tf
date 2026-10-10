# One box for everything Sentinel creates. Deleting it deletes everything inside.
resource "azurerm_resource_group" "sentinel" {
  name     = "sentinel-rg"
  location = var.location
}
# The private network (the estate)
resource "azurerm_virtual_network" "sentinel" {
  name                = "sentinel-vnet"
  location            = azurerm_resource_group.sentinel.location
  resource_group_name = azurerm_resource_group.sentinel.name
  address_space       = ["10.0.0.0/16"]
}

# One slice of it where the server will live (the street)
resource "azurerm_subnet" "public" {
  name                 = "sentinel-public-subnet"
  resource_group_name  = azurerm_resource_group.sentinel.name
  virtual_network_name = azurerm_virtual_network.sentinel.name
  address_prefixes     = ["10.0.1.0/24"]
}

# The firewall (the guard). Azure already denies all other inbound traffic by default.
resource "azurerm_network_security_group" "public" {
  name                = "sentinel-public-nsg"
  location            = azurerm_resource_group.sentinel.location
  resource_group_name = azurerm_resource_group.sentinel.name

  # Coming IN: SSH only from your own IP
  security_rule {
    name                       = "ssh-from-my-ip"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = var.ssh_allowed_cidr
    source_port_range          = "*"
    destination_address_prefix = "*"
    destination_port_range     = "22"
  }

  # Coming IN: web traffic from anyone
  security_rule {
    name                       = "http-https-from-anyone"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = "Internet"
    source_port_range          = "*"
    destination_address_prefix = "*"
    destination_port_ranges    = ["80", "443"]
  }
}
# Put the guard on the street: every server in this subnet gets these rules
resource "azurerm_subnet_network_security_group_association" "public" {
  subnet_id                 = azurerm_subnet.public.id
  network_security_group_id = azurerm_network_security_group.public.id
}
