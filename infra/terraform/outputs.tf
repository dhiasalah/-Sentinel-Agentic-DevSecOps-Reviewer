output "availability_domains" {
  value = data.oci_identity_availability_domains.ads.availability_domains[*].name
}
output "subnet_id" {
  value = oci_core_subnet.public.id
}
output "server_public_ip" {
  value = oci_core_instance.server.public_ip
}
