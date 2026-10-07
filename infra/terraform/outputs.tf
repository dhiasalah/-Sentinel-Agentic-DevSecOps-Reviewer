output "availability_domains" {
  value = data.oci_identity_availability_domains.ads.availability_domains[*].name
}
