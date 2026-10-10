variable "subscription_id" {
  description = "Your Azure for Students subscription ID (from az account show)"
  type        = string
}

variable "location" {
  description = "Azure region that passed the availability checks"
  type        = string
  default     = "northcentralus"
}

variable "ssh_allowed_cidr" {
  description = "Only this address may open SSH (port 22). Your public IP + /32"
  type        = string
}
