variable "region" {
  description = "Oracle region where everything lives"
  type        = string
  default     = "eu-paris-1"
}

variable "tenancy_ocid" {
  description = "Your Oracle account ID (the 'tenancy' line in ~/.oci/config)"
  type        = string
}
