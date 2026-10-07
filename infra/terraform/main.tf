provider "oci" {
  region              = var.region
  config_file_profile = "DEFAULT"
}

# Read-only question: "which data centres (availability domains) does my account have here?"
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}
