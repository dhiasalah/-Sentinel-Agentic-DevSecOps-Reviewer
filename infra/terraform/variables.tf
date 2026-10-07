variable "region" {
  description = "Oracle region where everything lives"
  type        = string
  default     = "eu-paris-1"
}

variable "tenancy_ocid" {
  description = "Your Oracle account ID (the 'tenancy' line in ~/.oci/config)"
  type        = string
}

variable "compartment_ocid" {
  description = "The 'sentinel' compartment: every Sentinel resource lives here"
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "Only this address may open SSH (port 22). Your public IP + /32"
  type        = string
}
variable "ssh_public_key_path" {
  description = "Public half of your SSH key; it becomes the server's lock"
  type        = string
  default     = "~/.ssh/sentinel_oracle.pub"
}
