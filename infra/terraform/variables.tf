variable "subscription_id" {
  description = "Your Azure for Students subscription ID (from az account show)"
  type        = string
}

variable "location" {
  description = "Azure region that passed the availability checks"
  type        = string
  default     = "northcentralus"
}
